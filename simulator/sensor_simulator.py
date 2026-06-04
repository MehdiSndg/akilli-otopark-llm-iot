"""
sensor_simulator.py — Park yeri doluluk sensörlerinin simülasyonu (gün-içi eğri).

Gerçek donanım yerine: her park yerinin "sensörü" doluluk durumunu üretir ve her
değişikliği MQTT'ye yayınlar (sensör -> broker -> tüketici). Gerçekçi IoT
topolojisi için:
  - Doluluk        : otopark/spots/<bölüm>/<id>   (retained, QoS 1)
  - Sağlık/telemetri: otopark/health/<id>          (batarya, sinyal, çevrimiçi)
  - Ağ geçidi LWT  : otopark/gateway/status        (süreç çökerse broker "offline" der)

UÇ (EDGE) ZEKÂ: ham sensör okuması doğrudan yayınlanmaz. Sensör düğümü, veriyi
merkeze göndermeden ÖNCE yerel bir karar verir (debounce): kısa süreli geçişleri
(önünden geçen yaya/araç) gerçek park etmeden ayırır. Yalnızca birkaç tur kararlı
kalan değişiklik "gerçek" sayılıp yayınlanır; tek-tur sıçramalar gürültü olarak
edge'de filtrelenir (EDGE_STATS ile sayılır). Bu, "zekâ merkeze değil nesneye
taşınır" temasının somut örneğidir.

Doluluk GÜNÜN SAATİNE göre değişir: gece düşük, sabah dolar, öğle/akşam zirve.
Birkaç sensör bilinçli olarak "zayıf pil"dir; pilleri hızlı tükenir ve sonunda
çevrimdışı olur (anomali panelinin gerçek içerikle dolması için).

Çalıştırma:
    python -m simulator.sensor_simulator      # tek başına, Ctrl+C ile dur
"""

import json
import math
import random
import time

import paho.mqtt.client as mqtt

import config
from algorithm.graph import build_parking
from backend import database, log

logger = log.get(__name__)

# Simülasyon başlangıcı ve saat ofseti (08:00'da başlasın — sabah dolma yayında)
_START = time.time()
_OFFSET_HOURS = 8.0

# Web arayüzünün okuduğu canlı durum (saat + yoğunluk etiketi)
SIM_STATE = {"hour": _OFFSET_HOURS, "busy": "Orta", "target": 0.0}

# Edge (uç) filtreleme istatistiği — UI'da "filtrelenen gürültü" olarak gösterilir.
# filtered : edge'de elenen geçici/pass-by sinyal sayısı (merkeze hiç gitmedi)
# confirmed: edge'in "gerçek" sayıp yayınladığı doluluk değişimi sayısı
EDGE_STATS = {"filtered": 0, "confirmed": 0}


def sim_hour():
    """0..24 arası simüle saat (şu an)."""
    elapsed = time.time() - _START
    return (_OFFSET_HOURS + elapsed / config.DAY_LENGTH_SEC * 24.0) % 24.0


def sim_hour_at(ts):
    """Belirli bir gerçek-zaman damgası (ts) için simüle saat (0..24).

    Analitik zaman grafiğinin x eksenine 'saat dilimi' koymak için kullanılır."""
    return (_OFFSET_HOURS + (ts - _START) / config.DAY_LENGTH_SEC * 24.0) % 24.0


# ---------------------------------------------------------------------------
# Gerçekçi park tercihi (doluluk dağılımı)
# ---------------------------------------------------------------------------
# Sürücüler rastgele park etmez: AVM yaya kapısına yakın yerler daha çok tercih
# edilir. Bu nedenle doluluk doldurulurken yerler, kapıya yakınlığa göre AĞIRLIKLI
# (ama YUMUŞAK -> yığılma yok) seçilir. Sonuç: ön taraf daha yoğun, arka daha seyrek,
# yumuşak bir gradyan. Doldurma HIZI değişmez (ek araç/devir yok); yalnız HANGİ yerin
# seçildiği değişir. Isı haritası (kullanım sıklığı) artık bu GERÇEK davranışı yansıtır.
_DESIR = None


def _build_desirability():
    """spot_id -> tercih ağırlığı (kapıya yakın = yüksek). Yumuşak gradyan."""
    from algorithm.graph import EXITS
    spots, graph = build_parking()
    doors = [graph.position(n) for n in EXITS]
    dist = {s.id: min(((s.x - dx) ** 2 + (s.y - dy) ** 2) ** 0.5 for dx, dy in doors)
            for s in spots}
    dmin, dmax = min(dist.values()), max(dist.values())
    scale = max(1.0, (dmax - dmin) / 2.0)         # en uzak ~e^-2 ≈ 0.14 ağırlık (yumuşak)
    return {sid: math.exp(-(d - dmin) / scale) for sid, d in dist.items()}


def _desir():
    global _DESIR
    if _DESIR is None:
        _DESIR = _build_desirability()
    return _DESIR


def _weighted_pick(pool, k):
    """Tercihe göre ağırlıklı, tekrarsız k seçim (Efraimidis-Spirakis ağırlıklı örnekleme).

    Kapıya yakın yerler daha sık seçilir, ama uzaklar da seçilebilir (yumuşak) ->
    gerçekçi doluluk, yığılma yok."""
    if k <= 0:
        return []
    if k >= len(pool):
        return list(pool)
    w = _desir()
    return sorted(pool, key=lambda s: random.random() ** (1.0 / max(w.get(s, 1e-9), 1e-9)),
                  reverse=True)[:k]


def occupancy_target(hour):
    """Saate göre hedef doluluk oranı (0..1). Gece düşük, öğle/akşam zirve."""
    morning = 0.45 * math.exp(-((hour - 10) ** 2) / 7)
    midday = 0.78 * math.exp(-((hour - 13.5) ** 2) / 9)
    evening = 0.92 * math.exp(-((hour - 19) ** 2) / 7)
    val = 0.06 + max(morning, midday, evening)
    return max(0.04, min(0.95, val))


def busy_label(target):
    if target >= 0.68:
        return "Yüksek"
    if target >= 0.40:
        return "Orta"
    return "Düşük"


def _initial_state():
    """Başlangıç doluluğu: o anki saatin hedef oranına göre, kapıya yakınlığa göre dağıt."""
    spots, _ = build_parking()
    ids = [s.id for s in spots]
    k = int(occupancy_target(sim_hour()) * len(ids))
    occupied = set(_weighted_pick(ids, k))        # kapıya yakın yerler daha dolu (gerçekçi)
    return {sid: (sid in occupied) for sid in ids}


# ---------------------------------------------------------------------------
# Uç (edge) gürültü filtresi — sensör düğümünde yerel debounce kararı
# ---------------------------------------------------------------------------
class EdgeFilter:
    """Sensör düğümünde yerel gürültü filtreleme (debounce).

    Ham okuma confirmed'dan farklıysa hemen yayınlanmaz; DEBOUNCE_TICKS tur
    boyunca aynı yönde KARARLI kalırsa "gerçek" sayılıp confirmed güncellenir.
    Kararlılığa ulaşmadan eski haline dönen okumalar = geçici geçiş (pass-by) =
    gürültü; merkeze hiç yayınlanmaz, yalnızca sayılır."""

    def __init__(self, initial, debounce_ticks):
        self.confirmed = dict(initial)        # yayınlanmış/onaylı durum
        self.debounce = max(1, debounce_ticks)
        self.cand = {}                        # sid -> [aday_değer, streak]

    def feed(self, sid, raw):
        """Ham okumayı işle. Yayınlanacak yeni onaylı değer varsa onu, yoksa None döndür."""
        if raw == self.confirmed[sid]:
            # Aday bir değişiklik vardı ama geri döndü -> geçici geçiş, filtrele
            if sid in self.cand:
                del self.cand[sid]
                EDGE_STATS["filtered"] += 1
            return None
        c = self.cand.get(sid)
        if c and c[0] == raw:
            c[1] += 1
        else:
            self.cand[sid] = c = [raw, 1]
        if c[1] >= self.debounce:             # yeterince kararlı -> gerçek değişim
            self.confirmed[sid] = raw
            del self.cand[sid]
            EDGE_STATS["confirmed"] += 1
            return raw
        return None


def _tick(raw, spot_ids, efilter, publish):
    """Bir adım: ham doluluğu hedefe yaklaştır, gürültü bindir, edge'de filtrele."""
    hour = sim_hour()
    target = occupancy_target(hour)
    SIM_STATE.update(hour=hour, target=target, busy=busy_label(target))

    # 1) Gerçek değişiklikler -> ham duruma uygula (doldurma kapıya yakınlığa göre
    #    AĞIRLIKLI; boşalma rastgele). Doldurma HIZI değişmez (ek araç/devir yok).
    target_count = int(target * len(spot_ids))
    current = sum(1 for v in raw.values() if v)
    diff = target_count - current
    n = min(abs(diff), 6)
    if diff > 0:
        empties = [s for s in spot_ids if not raw[s]]
        for sid in _weighted_pick(empties, min(n, len(empties))):
            raw[sid] = True
    elif diff < 0:
        occupied = [s for s in spot_ids if raw[s]]
        for sid in random.sample(occupied, min(n, len(occupied))):
            raw[sid] = False
    else:
        # hedefteyiz: hafif dalgalanma (1 flip). Boşalma rastgele, dolma tercihli.
        sid = random.choice(spot_ids)
        if raw[sid]:
            raw[sid] = False
        else:
            pick = _weighted_pick([s for s in spot_ids if not raw[s]], 1)
            raw[pick[0] if pick else sid] = True

    # 2) Geçici gürültü (pass-by): yalnız BU turun okumasına kısa "dolu" sıçraması
    reading = dict(raw)
    if random.random() < config.EDGE_NOISE_PROB:
        cands = [s for s in spot_ids
                 if not raw[s] and not efilter.confirmed[s] and s not in efilter.cand]
        for sid in random.sample(cands, min(config.EDGE_NOISE_MAX, len(cands))):
            reading[sid] = True              # sensör önünden geçiş -> kısa süreli sinyal

    # 3) Edge filtre: yalnızca kararlı (gerçek) değişiklikler merkeze yayınlanır
    for sid in spot_ids:
        confirmed = efilter.feed(sid, reading[sid])
        if confirmed is not None:
            publish(sid, confirmed)


# ---------------------------------------------------------------------------
# Sensör sağlığı (telemetri) simülasyonu
# ---------------------------------------------------------------------------
def _init_health(spot_ids):
    """Her sensör için batarya/sinyal durumu. Birkaçı 'zayıf pil' (hızlı tükenir).

    Zayıf sensörler düşük pille başlar -> anomali paneli demonun ilk saniyelerinden
    itibaren gerçek içerikle dolu olur (biri düşük pil, biri yakında çevrimdışı)."""
    n_weak = min(config.NUM_WEAK_SENSORS, len(spot_ids))
    weak = set(random.sample(spot_ids, n_weak))
    # Karışık başlangıç pilleri: biri neredeyse bitik (hızlıca çevrimdışı),
    # birkaçı düşük-pil bölgesinde (kalıcı uyarı), biri orta.
    start_batt = [3, 14, 19, 24, 30]
    health = {}
    for sid in spot_ids:
        is_weak = sid in weak
        health[sid] = {
            "battery": float(start_batt.pop(0)) if (is_weak and start_batt) else
                       (round(random.uniform(10, 28), 1) if is_weak else 100.0),
            "rssi": random.randint(-72, -48),
            "online": True,
            "weak": is_weak,
        }
    return health


def _step_health(health):
    """Telemetri turu: pilleri tüket, zayıfları çevrimdışına götür."""
    for sid, h in health.items():
        if not h["online"]:
            continue
        drain = config.WEAK_BATTERY_DRAIN if h["weak"] else config.BATTERY_DRAIN_PER_PUBLISH
        h["battery"] = max(0.0, h["battery"] - drain)
        h["rssi"] = max(-95, min(-40, h["rssi"] + random.randint(-2, 2)))
        if h["battery"] <= 0.0:                  # pil bitti -> sensör çevrimdışı
            h["online"] = False


def _publish_health(client, health):
    """Tüm sensörlerin sağlık telemetrisini yayınla (broker) ya da DB'ye yaz (yedek)."""
    now = time.time()
    for sid, h in health.items():
        payload = {"battery": round(h["battery"], 1), "rssi": h["rssi"],
                   "online": h["online"], "ts": now}
        if client is not None:
            client.publish(config.mqtt_health_topic(sid), json.dumps(payload),
                           qos=1, retain=True)
        else:
            database.set_health(sid, battery=h["battery"], rssi=h["rssi"],
                                online=h["online"], last_seen=now)


def _publish(client, spot_id, occupied):
    """Doluluk değişimini per-spot topic'e retained + QoS1 yayınla."""
    client.publish(config.mqtt_spot_topic(spot_id), json.dumps({
        "spot_id": spot_id, "occupied": bool(occupied), "ts": time.time(),
    }), qos=1, retain=True)


def _record_sample(raw):
    """Toplam doluluk örneği kaydet (analitik zaman grafiği için)."""
    occ = sum(1 for v in raw.values() if v)
    database.add_sample(occ, len(raw))


def _sleep_interruptible(interval, stop_event):
    waited = 0.0
    while waited < interval and not (stop_event and stop_event.is_set()):
        time.sleep(0.1)
        waited += 0.1


def _loop(raw, spot_ids, efilter, health, stop_event, interval, occ_pub, health_client):
    """Ortak döngü: doluluk + edge filtre + periyodik sağlık telemetrisi + örnek."""
    tick = 0
    while not (stop_event and stop_event.is_set()):
        _tick(raw, spot_ids, efilter, occ_pub)
        if tick % config.SAMPLE_EVERY == 0:
            _record_sample(raw)
        if tick % config.HEALTH_PUBLISH_EVERY == 0:
            _step_health(health)
            _publish_health(health_client, health)
        tick += 1
        _sleep_interruptible(interval, stop_event)


def _run_brokerless(raw, spot_ids, efilter, health, stop_event, interval):
    """Broker yokken yedek: değişiklikleri doğrudan SQLite'a yaz."""
    for sid, occ in raw.items():
        database.set_occupied(sid, occ)
    _publish_health(None, health)
    logger.warning("(brokersız) %d yer + sağlık DB'ye yazıldı", len(raw))
    _loop(raw, spot_ids, efilter, health, stop_event, interval,
          occ_pub=lambda sid, occ: database.set_occupied(sid, occ),
          health_client=None)
    logger.info("(brokersız) durduruldu")


def run_simulator(stop_event=None, interval=None, changes_per_tick=None):
    """Simülatör döngüsü. stop_event verilirse set edilince temiz durur."""
    interval = config.SIM_INTERVAL_SEC if interval is None else interval
    raw = _initial_state()
    spot_ids = list(raw.keys())
    efilter = EdgeFilter(raw, config.EDGE_DEBOUNCE_TICKS)
    health = _init_health(spot_ids)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="otopark-sensor")
    client.reconnect_delay_set(min_delay=1, max_delay=16)   # kopması durumunda yeniden bağlan
    # LWT (Last Will): süreç beklenmedik kapanırsa broker bunu yayınlar
    client.will_set(config.MQTT_TOPIC_GATEWAY,
                    json.dumps({"status": "offline", "ts": time.time()}),
                    qos=1, retain=True)
    try:
        client.connect(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
    except OSError as e:
        logger.warning("Broker'a bağlanılamadı (%s:%s); doluluk doğrudan DB'ye yazılacak. (%s)",
                       config.MQTT_HOST, config.MQTT_PORT, e)
        _run_brokerless(raw, spot_ids, efilter, health, stop_event, interval)
        return
    client.loop_start()

    # Ağ geçidi çevrimiçi (retained) — UI/abone başlayınca son durumu görür
    client.publish(config.MQTT_TOPIC_GATEWAY,
                   json.dumps({"status": "online", "ts": time.time()}), qos=1, retain=True)

    for sid, occ in raw.items():             # başlangıç durumunu yayınla
        _publish(client, sid, occ)
    _publish_health(client, health)
    logger.info("%d yer + sağlık telemetrisi yayınlandı (saat %.1f, yoğunluk %s)",
                len(raw), SIM_STATE['hour'], SIM_STATE['busy'])

    try:
        _loop(raw, spot_ids, efilter, health, stop_event, interval,
              occ_pub=lambda sid, occ: _publish(client, sid, occ),
              health_client=client)
    finally:
        # Temiz kapanış: çevrimiçi -> çevrimdışı bildir (LWT'siz normal kapanışta da)
        client.publish(config.MQTT_TOPIC_GATEWAY,
                       json.dumps({"status": "offline", "ts": time.time()}),
                       qos=1, retain=True)
        client.loop_stop()
        client.disconnect()
        logger.info("durduruldu (edge: %d gürültü filtrelendi, %d gerçek değişim)",
                    EDGE_STATS["filtered"], EDGE_STATS["confirmed"])


if __name__ == "__main__":
    try:
        run_simulator()
    except KeyboardInterrupt:
        logger.info("Ctrl+C ile çıkılıyor")

"""
sensor_simulator.py — Park yeri doluluk sensörlerinin simülasyonu (gün-içi eğri).

Gerçek donanım yerine: her park yerinin "sensörü" doluluk durumunu üretir ve her
değişikliği MQTT'ye yayınlar (sensör -> broker -> tüketici). Gerçekçi IoT
topolojisi için:
  - Doluluk        : otopark/spots/<bölüm>/<id>   (retained, QoS 1)
  - Sağlık/telemetri: otopark/health/<id>          (batarya, sinyal, çevrimiçi)
  - Ağ geçidi LWT  : otopark/gateway/status        (süreç çökerse broker "offline" der)

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
from backend import database

# Simülasyon başlangıcı ve saat ofseti (08:00'da başlasın — sabah dolma yayında)
_START = time.time()
_OFFSET_HOURS = 8.0

# Web arayüzünün okuduğu canlı durum (saat + yoğunluk etiketi)
SIM_STATE = {"hour": _OFFSET_HOURS, "busy": "Orta", "target": 0.0}


def sim_hour():
    """0..24 arası simüle saat."""
    elapsed = time.time() - _START
    return (_OFFSET_HOURS + elapsed / config.DAY_LENGTH_SEC * 24.0) % 24.0


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
    """Başlangıç doluluğu: o anki saatin hedef oranına göre rastgele dağıt."""
    spots, _ = build_parking()
    ids = [s.id for s in spots]
    k = int(occupancy_target(sim_hour()) * len(ids))
    occupied = set(random.sample(ids, k))
    return {sid: (sid in occupied) for sid in ids}


def _tick(state, spot_ids, publish):
    """Bir adım: doluluğu o saatin hedefine doğru yaklaştır, değişiklikleri yayınla."""
    hour = sim_hour()
    target = occupancy_target(hour)
    SIM_STATE.update(hour=hour, target=target, busy=busy_label(target))

    target_count = int(target * len(spot_ids))
    current = sum(1 for v in state.values() if v)
    diff = target_count - current
    n = min(abs(diff), 6)

    if diff > 0:                                  # dolması gerekiyor -> araçlar gelir
        empties = [s for s in spot_ids if not state[s]]
        for sid in random.sample(empties, min(n, len(empties))):
            state[sid] = True
            publish(sid, True)
    elif diff < 0:                                # boşalması gerekiyor -> araçlar gider
        occupied = [s for s in spot_ids if state[s]]
        for sid in random.sample(occupied, min(n, len(occupied))):
            state[sid] = False
            publish(sid, False)
    else:                                         # hedefteyiz -> küçük dalgalanma
        sid = random.choice(spot_ids)
        state[sid] = not state[sid]
        publish(sid, state[sid])


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


def _record_sample(state):
    """Toplam doluluk örneği kaydet (analitik zaman grafiği için)."""
    occ = sum(1 for v in state.values() if v)
    database.add_sample(occ, len(state))


def _sleep_interruptible(interval, stop_event):
    waited = 0.0
    while waited < interval and not (stop_event and stop_event.is_set()):
        time.sleep(0.1)
        waited += 0.1


def _loop(state, spot_ids, health, stop_event, interval, occ_pub, health_client):
    """Ortak döngü: doluluk + periyodik sağlık telemetrisi + periyodik örnek."""
    tick = 0
    while not (stop_event and stop_event.is_set()):
        _tick(state, spot_ids, occ_pub)
        if tick % config.SAMPLE_EVERY == 0:
            _record_sample(state)
        if tick % config.HEALTH_PUBLISH_EVERY == 0:
            _step_health(health)
            _publish_health(health_client, health)
        tick += 1
        _sleep_interruptible(interval, stop_event)


def _run_brokerless(state, spot_ids, health, stop_event, interval):
    """Broker yokken yedek: değişiklikleri doğrudan SQLite'a yaz."""
    for sid, occ in state.items():
        database.set_occupied(sid, occ)
    _publish_health(None, health)
    print(f"[simulator] (brokersız) {len(state)} yer + sağlık DB'ye yazıldı")
    _loop(state, spot_ids, health, stop_event, interval,
          occ_pub=lambda sid, occ: database.set_occupied(sid, occ),
          health_client=None)
    print("[simulator] (brokersız) durduruldu")


def run_simulator(stop_event=None, interval=None, changes_per_tick=None):
    """Simülatör döngüsü. stop_event verilirse set edilince temiz durur."""
    interval = config.SIM_INTERVAL_SEC if interval is None else interval
    state = _initial_state()
    spot_ids = list(state.keys())
    health = _init_health(spot_ids)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="otopark-sensor")
    # LWT (Last Will): süreç beklenmedik kapanırsa broker bunu yayınlar
    client.will_set(config.MQTT_TOPIC_GATEWAY,
                    json.dumps({"status": "offline", "ts": time.time()}),
                    qos=1, retain=True)
    try:
        client.connect(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
    except OSError as e:
        print(f"[simulator] Broker'a bağlanılamadı ({config.MQTT_HOST}:{config.MQTT_PORT}); "
              f"doluluk doğrudan DB'ye yazılacak. ({e})")
        _run_brokerless(state, spot_ids, health, stop_event, interval)
        return
    client.loop_start()

    # Ağ geçidi çevrimiçi (retained) — UI/abone başlayınca son durumu görür
    client.publish(config.MQTT_TOPIC_GATEWAY,
                   json.dumps({"status": "online", "ts": time.time()}), qos=1, retain=True)

    for sid, occ in state.items():           # başlangıç durumunu yayınla
        _publish(client, sid, occ)
    _publish_health(client, health)
    print(f"[simulator] {len(state)} yer + sağlık telemetrisi yayınlandı "
          f"(saat {SIM_STATE['hour']:.1f}, yoğunluk {SIM_STATE['busy']})")

    try:
        _loop(state, spot_ids, health, stop_event, interval,
              occ_pub=lambda sid, occ: _publish(client, sid, occ),
              health_client=client)
    finally:
        # Temiz kapanış: çevrimiçi -> çevrimdışı bildir (LWT'siz normal kapanışta da)
        client.publish(config.MQTT_TOPIC_GATEWAY,
                       json.dumps({"status": "offline", "ts": time.time()}),
                       qos=1, retain=True)
        client.loop_stop()
        client.disconnect()
        print("[simulator] durduruldu")


if __name__ == "__main__":
    try:
        run_simulator()
    except KeyboardInterrupt:
        print("\n[simulator] Ctrl+C ile çıkılıyor")

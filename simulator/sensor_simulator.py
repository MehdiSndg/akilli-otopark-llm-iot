"""
sensor_simulator.py — Park yeri doluluk sensörlerinin simülasyonu (gün-içi eğri).

Gerçek donanım yerine: her park yerinin "sensörü" doluluk durumunu üretir ve her
değişikliği MQTT topic'ine JSON olarak yayınlar (sensör -> broker -> tüketici).

Doluluk artık GÜNÜN SAATİNE göre değişir: gece düşük, sabah dolmaya başlar, öğle
ve akşam zirve yapar. Simüle bir gün, config.DAY_LENGTH_SEC gerçek saniyede geçer.
Mevcut saat/yoğunluk SIM_STATE'te tutulur (web arayüzü bunu gösterir).

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


def _publish(client, spot_id, occupied):
    client.publish(config.MQTT_TOPIC, json.dumps({
        "spot_id": spot_id, "occupied": bool(occupied), "ts": time.time(),
    }), qos=1)


def _sleep_interruptible(interval, stop_event):
    waited = 0.0
    while waited < interval and not (stop_event and stop_event.is_set()):
        time.sleep(0.1)
        waited += 0.1


def _run_brokerless(state, spot_ids, stop_event, interval):
    """Broker yokken yedek: değişiklikleri doğrudan SQLite'a yaz."""
    for sid, occ in state.items():
        database.set_occupied(sid, occ)
    print(f"[simulator] (brokersız) {len(state)} yer DB'ye yazıldı")
    while not (stop_event and stop_event.is_set()):
        _tick(state, spot_ids, lambda sid, occ: database.set_occupied(sid, occ))
        _sleep_interruptible(interval, stop_event)
    print("[simulator] (brokersız) durduruldu")


def run_simulator(stop_event=None, interval=None, changes_per_tick=None):
    """Simülatör döngüsü. stop_event verilirse set edilince temiz durur."""
    interval = config.SIM_INTERVAL_SEC if interval is None else interval
    state = _initial_state()
    spot_ids = list(state.keys())

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="otopark-sensor")
    try:
        client.connect(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
    except OSError as e:
        print(f"[simulator] Broker'a bağlanılamadı ({config.MQTT_HOST}:{config.MQTT_PORT}); "
              f"doluluk doğrudan DB'ye yazılacak. ({e})")
        _run_brokerless(state, spot_ids, stop_event, interval)
        return
    client.loop_start()

    for sid, occ in state.items():           # başlangıç durumunu yayınla
        _publish(client, sid, occ)
    print(f"[simulator] {len(state)} yer için başlangıç durumu yayınlandı "
          f"(saat {SIM_STATE['hour']:.1f}, yoğunluk {SIM_STATE['busy']})")

    try:
        while not (stop_event and stop_event.is_set()):
            _tick(state, spot_ids, lambda sid, occ: _publish(client, sid, occ))
            _sleep_interruptible(interval, stop_event)
    finally:
        client.loop_stop()
        client.disconnect()
        print("[simulator] durduruldu")


if __name__ == "__main__":
    try:
        run_simulator()
    except KeyboardInterrupt:
        print("\n[simulator] Ctrl+C ile çıkılıyor")

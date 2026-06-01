"""
sensor_simulator.py — Park yeri doluluk sensörlerinin simülasyonu.

Gerçek donanım yerine: her park yerinin "sensörü" doluluk durumunu üretir ve
her değişikliği MQTT topic'ine JSON olarak yayınlar. Bu, IoT dersinin özü olan
sensör -> broker -> tüketici akışını gösterir.

Mesaj biçimi (JSON):
    {"spot_id": "A-1", "occupied": true, "ts": 1719000000.0}

Çalıştırma:
    python -m simulator.sensor_simulator      # tek başına, Ctrl+C ile dur
"""

import json
import random
import time

import paho.mqtt.client as mqtt

import config
from algorithm.graph import build_parking


def _initial_state():
    """Başlangıç doluluk durumu: her yer için rastgele dolu/boş."""
    spots, _ = build_parking()
    return {s.id: (random.random() < config.INITIAL_OCCUPANCY_RATE) for s in spots}


def _publish(client, spot_id, occupied):
    payload = json.dumps({
        "spot_id": spot_id,
        "occupied": bool(occupied),
        "ts": time.time(),
    })
    client.publish(config.MQTT_TOPIC, payload, qos=1)


def run_simulator(stop_event=None, interval=None, changes_per_tick=None):
    """Simülatör döngüsü. stop_event verilirse set edilince temiz durur."""
    interval = config.SIM_INTERVAL_SEC if interval is None else interval
    changes = config.SIM_CHANGES_PER_TICK if changes_per_tick is None else changes_per_tick

    state = _initial_state()
    spot_ids = list(state.keys())

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="otopark-sensor")
    client.connect(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
    client.loop_start()

    # Başlangıçta tam durumu yayınla (abone DB'yi senkronlasın)
    for sid, occ in state.items():
        _publish(client, sid, occ)
    print(f"[simulator] {len(state)} yer için başlangıç durumu yayınlandı")

    try:
        while not (stop_event and stop_event.is_set()):
            # Birkaç rastgele yerin durumunu değiştir ve yayınla
            for sid in random.sample(spot_ids, k=min(changes, len(spot_ids))):
                state[sid] = not state[sid]
                _publish(client, sid, state[sid])
                print(f"[simulator] {sid} -> {'DOLU' if state[sid] else 'BOŞ'}")

            # interval kadar bekle ama stop_event'e duyarlı kal
            waited = 0.0
            while waited < interval and not (stop_event and stop_event.is_set()):
                time.sleep(0.1)
                waited += 0.1
    finally:
        client.loop_stop()
        client.disconnect()
        print("[simulator] durduruldu")


if __name__ == "__main__":
    try:
        run_simulator()
    except KeyboardInterrupt:
        print("\n[simulator] Ctrl+C ile çıkılıyor")

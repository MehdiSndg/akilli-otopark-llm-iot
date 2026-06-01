"""
mqtt_client.py — MQTT abonesi (tüketici).

Sensör simülatörünün yayınladığı doluluk mesajlarına abone olur, JSON'u parse
eder ve database üzerinden SQLite'ı günceller. Algoritma ve UI bu güncel veriyi
parking_state üzerinden okur.

Çalıştırma:
    python -m backend.mqtt_client      # tek başına dinler, Ctrl+C ile dur
"""

import json
import time

import paho.mqtt.client as mqtt

import config
from backend import database


def _on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"[mqtt] broker'a bağlanıldı (rc={reason_code}), abone olunuyor: {config.MQTT_TOPIC}")
    client.subscribe(config.MQTT_TOPIC, qos=1)


def _on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        database.set_occupied(data["spot_id"], bool(data["occupied"]))
    except (ValueError, KeyError) as e:
        print(f"[mqtt] geçersiz mesaj atlandı: {e}")


def _make_client():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=config.MQTT_CLIENT_ID)
    client.on_connect = _on_connect
    client.on_message = _on_message
    return client


def start_subscriber(stop_event=None):
    """Aboneyi başlat. stop_event yoksa bloklar (loop_forever); varsa thread dostu."""
    database.init_db()  # tablo + tohum hazır olsun
    client = _make_client()
    try:
        client.connect(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
    except OSError as e:
        print(f"[mqtt] Broker'a bağlanılamadı ({config.MQTT_HOST}:{config.MQTT_PORT}). "
              f"Mosquitto çalışmıyor olabilir; canlı güncelleme devre dışı. ({e})")
        return

    if stop_event is None:
        client.loop_forever()
    else:
        client.loop_start()
        try:
            while not stop_event.is_set():
                time.sleep(0.1)
        finally:
            client.loop_stop()
            client.disconnect()
            print("[mqtt] abone durduruldu")


if __name__ == "__main__":
    try:
        start_subscriber()
    except KeyboardInterrupt:
        print("\n[mqtt] Ctrl+C ile çıkılıyor")

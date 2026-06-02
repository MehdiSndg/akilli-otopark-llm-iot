"""
mqtt_client.py — MQTT abonesi (tüketici).

Sensör simülatörünün yayınladığı mesajlara abone olur ve SQLite'ı günceller.
Topic hiyerarşisine göre yönlendirir:
  - otopark/spots/<bölüm>/<id>  -> doluluk  (database.set_occupied -> olay kaydı)
  - otopark/health/<id>         -> sağlık   (database.set_health)
  - otopark/gateway/status      -> ağ geçidi çevrimiçi/çevrimdışı (LWT)

Algoritma ve UI bu güncel veriyi parking_state üzerinden okur.

Çalıştırma:
    python -m backend.mqtt_client      # tek başına dinler, Ctrl+C ile dur
"""

import json
import time

import paho.mqtt.client as mqtt

import config
from backend import database

# Ağ geçidi (sensör simülatörü) çevrimiçi mi? LWT mesajıyla güncellenir.
GATEWAY_STATE = {"online": False, "ts": 0.0}


def _on_connect(client, userdata, flags, reason_code, properties=None):
    print(f"[mqtt] broker'a bağlanıldı (rc={reason_code}), abone olunuyor: "
          f"{config.MQTT_TOPIC_SPOTS_WILDCARD} + health + gateway")
    client.subscribe(config.MQTT_TOPIC_SPOTS_WILDCARD, qos=1)
    client.subscribe(config.MQTT_TOPIC_HEALTH_WILDCARD, qos=1)
    client.subscribe(config.MQTT_TOPIC_GATEWAY, qos=1)
    client.subscribe(config.MQTT_TOPIC, qos=1)   # geriye dönük (eski tekil topic)


def _on_message(client, userdata, msg):
    topic = msg.topic
    try:
        data = json.loads(msg.payload.decode())
    except ValueError as e:
        print(f"[mqtt] geçersiz JSON atlandı ({topic}): {e}")
        return

    try:
        if topic == config.MQTT_TOPIC_GATEWAY:
            GATEWAY_STATE.update(online=(data.get("status") == "online"),
                                 ts=data.get("ts", time.time()))
        elif topic.startswith(config.MQTT_TOPIC_BASE + "/health/"):
            spot_id = topic.rsplit("/", 1)[-1]
            database.set_health(spot_id,
                                battery=data.get("battery"), rssi=data.get("rssi"),
                                online=data.get("online"), last_seen=data.get("ts"))
        else:   # doluluk (otopark/spots/... ya da eski otopark/spots)
            database.set_occupied(data["spot_id"], bool(data["occupied"]))
    except KeyError as e:
        print(f"[mqtt] eksik alan atlandı ({topic}): {e}")


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

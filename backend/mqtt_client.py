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
from pydantic import ValidationError

import config
from backend import database, log
from backend.schemas import SpotMessage, HealthMessage, GatewayMessage

logger = log.get(__name__)

# Ağ geçidi (sensör simülatörü) çevrimiçi mi? LWT mesajıyla güncellenir.
GATEWAY_STATE = {"online": False, "ts": 0.0}


def _on_connect(client, userdata, flags, reason_code, properties=None):
    logger.info("broker'a bağlanıldı (rc=%s); abone: %s + health + gateway",
                reason_code, config.MQTT_TOPIC_SPOTS_WILDCARD)
    client.subscribe(config.MQTT_TOPIC_SPOTS_WILDCARD, qos=1)
    client.subscribe(config.MQTT_TOPIC_HEALTH_WILDCARD, qos=1)
    client.subscribe(config.MQTT_TOPIC_GATEWAY, qos=1)
    client.subscribe(config.MQTT_TOPIC, qos=1)   # geriye dönük (eski tekil topic)


def _on_disconnect(client, userdata, *args):
    """Bağlantı koparsa logla; paho reconnect_delay_set ile otomatik yeniden bağlanır."""
    logger.warning("broker bağlantısı koptu; yeniden bağlanmaya çalışılıyor...")


def _on_message(client, userdata, msg):
    """Gelen mesajı topic'e göre yönlendir; Pydantic ile DOĞRULA (bozuk veri reddedilir)."""
    topic = msg.topic
    try:
        data = json.loads(msg.payload.decode())
    except ValueError as e:
        logger.warning("geçersiz JSON atlandı (%s): %s", topic, e)
        return

    try:
        if topic == config.MQTT_TOPIC_GATEWAY:
            m = GatewayMessage(**data)
            GATEWAY_STATE.update(online=(m.status == "online"),
                                 ts=m.ts if m.ts is not None else time.time())
        elif topic.startswith(config.MQTT_TOPIC_BASE + "/health/"):
            spot_id = topic.rsplit("/", 1)[-1]
            m = HealthMessage(**data)
            database.set_health(spot_id, battery=m.battery, rssi=m.rssi,
                                online=m.online, last_seen=m.ts)
        else:   # doluluk (otopark/spots/... ya da eski otopark/spots)
            m = SpotMessage(**data)
            database.set_occupied(m.spot_id, m.occupied)
    except ValidationError as e:
        # Şema dışı/bozuk sensör verisi sisteme girmeden burada yakalanır
        logger.warning("şema dışı mesaj reddedildi (%s): %s", topic,
                       e.errors()[0].get("msg") if e.errors() else e)


def _make_client():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=config.MQTT_CLIENT_ID)
    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message = _on_message
    client.reconnect_delay_set(min_delay=1, max_delay=16)   # üstel geri çekilmeyle yeniden dene
    return client


def start_subscriber(stop_event=None, connect_attempts=5):
    """Aboneyi başlat. stop_event yoksa bloklar (loop_forever); varsa thread dostu.

    İlk bağlantı birkaç kez denenir (broker biraz geç açılmış olabilir);
    bağlantı sonradan koparsa paho otomatik yeniden bağlanır (graceful degradation).
    """
    database.init_db()  # tablo + tohum hazır olsun
    client = _make_client()

    connected = False
    for attempt in range(1, connect_attempts + 1):
        try:
            client.connect(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
            connected = True
            break
        except OSError as e:
            logger.warning("broker'a bağlanılamadı (deneme %d/%d, %s:%s): %s",
                           attempt, connect_attempts, config.MQTT_HOST, config.MQTT_PORT, e)
            if stop_event is not None and stop_event.wait(2.0):
                return
            elif stop_event is None:
                time.sleep(2.0)
    if not connected:
        logger.error("broker erişilemedi; canlı MQTT güncellemesi devre dışı "
                     "(simülatör brokersız DB yedeğine düşer).")
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
            logger.info("abone durduruldu")


if __name__ == "__main__":
    try:
        start_subscriber()
    except KeyboardInterrupt:
        logger.info("Ctrl+C ile çıkılıyor")

"""
anomaly.py — IoT güvenilirlik: sensör/durum anomalisi tespiti.

Gerçek bir IoT sisteminde sensörler arızalanır, pilleri biter, ağ kopar. Bu modül
canlı veriden (doluluk + sağlık telemetrisi) üç tür anomaliyi tespit eder:

  - stuck_occupied : sensör çevrimdışı AMA hâlâ "dolu" raporluyor (takılı/arızalı,
                     güncellenemiyor) -> hata
  - sensor_offline : sensör çevrimdışı, yer boş raporlu (pil bitti / telemetri kesildi) -> hata
  - low_battery    : pil eşik altında (yakında çevrimdışı olabilir)               -> uyarı

Tipler AYRIK tutulur (bir sensör tek bir anomaliye sayılır) ve offline sayısıyla
sınırlıdır; bu yüzden panel gürültüye boğulmaz. Kararı etkilemez; yalnızca
operatöre/panel'e bilgi verir (IoT bakım teması).
"""

import time

import config
from backend import database


def detect(now=None):
    """Canlı veriden anomali listesi üretir.

    Döner: {"items": [...], "counts": {"error": n, "warning": m, "total": k}}
    Her item: {type, spot_id, severity, message, value}
    """
    now = now or time.time()
    health = database.get_health()
    last = database.get_last_changes()      # spot_id -> {occupied, last_change}
    items = []

    for sid, h in health.items():
        offline = (not h["online"]) or (now - h["last_seen"] > config.SENSOR_OFFLINE_AFTER_SEC)
        occupied = last.get(sid, {}).get("occupied", False)
        if offline and occupied:
            # Sensör ölü ama DB 'dolu' diyor -> güncellenemiyor, takılı/arızalı
            items.append({
                "type": "stuck_occupied", "spot_id": sid, "severity": "error",
                "value": round(h["battery"], 1),
                "message": f"{sid}: sensör çevrimdışı ama 'dolu' raporluyor — takılı/arızalı sensör",
            })
        elif offline:
            items.append({
                "type": "sensor_offline", "spot_id": sid, "severity": "error",
                "value": round(h["battery"], 1),
                "message": f"{sid}: sensör çevrimdışı (pil %{h['battery']:.0f}) — bakım gerekli",
            })
        elif h["battery"] < config.LOW_BATTERY_THRESHOLD:
            items.append({
                "type": "low_battery", "spot_id": sid, "severity": "warning",
                "value": round(h["battery"], 1),
                "message": f"{sid}: düşük pil (%{h['battery']:.0f}) — sensör yakında durabilir",
            })

    # En kritik önce: hata > uyarı, sonra değere göre
    sev_rank = {"error": 0, "warning": 1}
    items.sort(key=lambda a: (sev_rank.get(a["severity"], 2), a.get("value", 0)))

    errors = sum(1 for a in items if a["severity"] == "error")
    warnings = sum(1 for a in items if a["severity"] == "warning")
    return {"items": items,
            "counts": {"error": errors, "warning": warnings, "total": len(items)}}


def health_summary(now=None):
    """Sensör filosu özeti (panel başlığı için): çevrimiçi/çevrimdışı/düşük pil sayıları."""
    now = now or time.time()
    health = database.get_health()
    total = len(health)
    offline = sum(1 for h in health.values()
                  if (not h["online"]) or (now - h["last_seen"] > config.SENSOR_OFFLINE_AFTER_SEC))
    low = sum(1 for h in health.values()
              if h["online"] and h["battery"] < config.LOW_BATTERY_THRESHOLD)
    avg_batt = round(sum(h["battery"] for h in health.values()) / total, 1) if total else 0
    return {"total": total, "online": total - offline, "offline": offline,
            "low_battery": low, "avg_battery": avg_batt}

"""
analytics.py — Toplanan IoT verisinden analitik üretir (veriyi değere çevir).

Sensör olayları (events) ve periyodik doluluk örnekleri (occupancy_samples)
üzerinden panel için özetler hesaplar:
  - timeseries    : zaman içinde doluluk (çizgi grafik)
  - avg_stay      : ortalama kalış süresi (dolu->boş olay eşleştirme, simüle saat)
  - sections      : bölge (A–E) doluluk oranları (en yoğun bölgeler)
  - heatmap       : park yeri başına kullanım sıklığı (ısı haritası)
"""

import config
from backend import database, parking_state


def _real_to_sim_hours(seconds):
    """Gerçek saniyeyi simüle saate çevir (DAY_LENGTH_SEC = 1 simüle gün = 24 sa)."""
    return seconds / config.DAY_LENGTH_SEC * 24.0


def avg_stay_minutes(events=None):
    """Ortalama kalış süresi (simüle DAKİKA). Her yer için dolu->sonraki boş eşleştir."""
    events = events if events is not None else database.get_events()
    open_ts = {}                       # spot_id -> dolu olduğu an
    durations = []                     # simüle saat cinsinden kalışlar
    for e in events:
        sid, occ, ts = e["spot_id"], e["occupied"], e["ts"]
        if occ:
            open_ts[sid] = ts
        elif sid in open_ts:
            durations.append(_real_to_sim_hours(ts - open_ts.pop(sid)))
    if not durations:
        return 0.0
    return round(sum(durations) / len(durations) * 60.0, 1)


def section_occupancy(spots=None):
    """Bölge (id ön eki: A–E) başına (dolu, toplam, oran). En yoğun bölgeler için."""
    spots = spots if spots is not None else parking_state.get_state()
    agg = {}
    for s in spots:
        sec = s["id"].split("-")[0]
        a = agg.setdefault(sec, {"section": sec, "occupied": 0, "total": 0})
        a["total"] += 1
        if s["occupied"]:
            a["occupied"] += 1
    out = []
    for sec in sorted(agg):
        a = agg[sec]
        a["rate"] = round(a["occupied"] / a["total"], 3) if a["total"] else 0
        out.append(a)
    return out


def heatmap(events=None):
    """Park yeri başına kullanım sıklığı: kaç kez doldu (ısı haritası yoğunluğu)."""
    events = events if events is not None else database.get_events()
    usage = {}
    for e in events:
        if e["occupied"]:
            usage[e["spot_id"]] = usage.get(e["spot_id"], 0) + 1
    return usage


def timeseries(limit=180):
    """Doluluk zaman serisi: [{ts, occupied, total}] (çizgi grafik için)."""
    return database.get_samples(limit)


def summary():
    """Panelin ihtiyacı olan her şeyi tek pakette döndür."""
    spots = parking_state.get_state()
    events = database.get_events()
    return {
        "timeseries": timeseries(),
        "avg_stay_minutes": avg_stay_minutes(events),
        "sections": section_occupancy(spots),
        "heatmap": heatmap(events),
    }

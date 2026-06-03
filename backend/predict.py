"""
predict.py — Tahminleyici (öngörücü) zekâ: kısa-vadeli doluluk tahmini.

Sistem yalnızca ANLIK durumu değil, yakın geleceği de görsün. İki sinyali
harmanlar (ağır ML gerekmez):

  1. Yakın geçmişin EĞİLİMİ — occupancy_samples üzerinde basit doğrusal regresyon
     (hareketli eğim): doluluk şu an artıyor mu azalıyor mu, ne hızla?
  2. Gün-içi ÖRÜNTÜ — sensor_simulator.occupancy_target eğrisi (saatlik doluluk
     profili): "öğlene doğru dolar, gece boşalır" bilgisi.

Tahmin = anlık oran + (eğilim + örüntü) yönünde horizon_min kadar ileri projeksiyon.
"15 dk sonra büyük ihtimalle dolacak, sizi şuraya yönlendireyim" gibi öngörücü
yönlendirmeye zemin olur.
"""

import config
from backend import database, log

logger = log.get(__name__)


def _trend_slope(samples):
    """occupancy_samples'tan doluluk SAYISININ örnek başına eğimini bul (en küçük kareler).

    Döner: (eğim, son_oran). Eğim = örnek başına dolu yer değişimi; son_oran = en
    güncel doluluk oranı (0..1). Yetersiz veri varsa (0.0, mevcut oran)."""
    if len(samples) < 3:
        if samples:
            s = samples[-1]
            return 0.0, (s["occupied"] / s["total"] if s["total"] else 0.0)
        return 0.0, 0.0

    # Son ~12 örneğe bak (kısa-vadeli eğilim; çok eskisi bugünü temsil etmez)
    pts = samples[-12:]
    n = len(pts)
    xs = list(range(n))
    ys = [p["occupied"] for p in pts]
    total = pts[-1]["total"] or 1
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs) or 1.0
    slope = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / denom
    last_ratio = ys[-1] / total
    return slope, last_ratio


def predict(horizon_min=15):
    """horizon_min simüle-dakika sonrası için doluluk tahmini.

    Döner (dict):
        now_ratio        : anlık doluluk oranı (0..1)
        predicted_ratio  : tahmini doluluk oranı (0..1)
        horizon_min      : ufuk (simüle dakika)
        trend            : "rising" | "falling" | "stable"
        predicted_free   : tahmini boş yer sayısı
        total            : toplam yer
        advice           : sürücüye sözel öneri (Türkçe)
    """
    # Geç bağlama: döngüsel import (sensor_simulator -> database) olmasın diye burada
    from simulator import sensor_simulator

    total, occ, _ = database.counts()
    total = total or 1
    samples = database.get_samples(limit=40)
    slope, last_ratio = _trend_slope(samples)
    now_ratio = occ / total

    # 1) Eğilim bileşeni: örnek başına eğimi ufka karşılık gelen örnek sayısıyla ölçekle
    sample_dt = config.SAMPLE_EVERY * config.SIM_INTERVAL_SEC          # örnek arası gerçek sn
    sim_min_per_real_sec = 24 * 60 / config.DAY_LENGTH_SEC             # 1 gerçek sn = kaç simüle dk
    horizon_real_sec = horizon_min / sim_min_per_real_sec
    steps = horizon_real_sec / sample_dt if sample_dt else 0
    trend_delta = (slope * steps) / total                             # oran cinsinden

    # 2) Örüntü bileşeni: saatlik eğrinin ufuk boyunca değişimi
    hour_now = sensor_simulator.sim_hour()
    hour_future = (hour_now + horizon_min / 60.0) % 24.0
    curve_delta = (sensor_simulator.occupancy_target(hour_future)
                   - sensor_simulator.occupancy_target(hour_now))

    # Harmanla (eğilim canlı veriyi, örüntü gün ritmini temsil eder)
    predicted_ratio = now_ratio + 0.6 * trend_delta + 0.4 * curve_delta
    predicted_ratio = max(0.0, min(1.0, predicted_ratio))
    predicted_free = max(0, round(total * (1.0 - predicted_ratio)))

    delta = predicted_ratio - now_ratio
    if delta > 0.03:
        trend = "rising"
    elif delta < -0.03:
        trend = "falling"
    else:
        trend = "stable"

    advice = _advice(trend, predicted_ratio, predicted_free, horizon_min)
    return {"now_ratio": round(now_ratio, 3),
            "predicted_ratio": round(predicted_ratio, 3),
            "horizon_min": horizon_min, "trend": trend,
            "predicted_free": predicted_free, "total": total,
            "advice": advice}


def _advice(trend, pred_ratio, pred_free, horizon_min):
    """Tahmini sürücü diliyle özetle (öngörücü yönlendirme önerisi)."""
    pct = round(pred_ratio * 100)
    if trend == "rising" and pred_ratio > 0.85:
        return (f"Otopark hızla doluyor — ~{horizon_min} dk içinde doluluk %{pct} "
                f"olabilir (yalnızca ~{pred_free} boş yer). Şimdi yer ayırtmanız önerilir.")
    if trend == "rising":
        return (f"Doluluk artışta — ~{horizon_min} dk sonra tahminen %{pct} dolu "
                f"(~{pred_free} boş yer). Yakında gelecekseniz erken davranın.")
    if trend == "falling":
        return (f"Otopark boşalıyor — ~{horizon_min} dk sonra tahminen %{pct} dolu "
                f"(~{pred_free} boş yer). Rahatça yer bulabilirsiniz.")
    return (f"Doluluk şu an dengeli — ~{horizon_min} dk sonra da tahminen %{pct} "
            f"dolu (~{pred_free} boş yer).")

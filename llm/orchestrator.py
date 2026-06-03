"""
orchestrator.py — Doğal dil -> araç çağrısı -> doğal dil cevap (çok-araçlı asistan).

Asistan artık tek-komut çevirici değil; sürücünün niyetine göre üç araçtan birini
çalıştırır:
  - find_best_parking_spot : en uygun boş yeri bul + yönlendir   (allocator)
  - get_parking_stats      : anlık doluluk/boş yer durumu          (database)
  - predict_availability   : yakın gelecek doluluk tahmini         (predict)

Akış (CLAUDE.md Bölüm 6):
  1. Sürücünün serbest metni LLM'e gönderilir (function calling araçlarıyla).
  2. LLM hangi aracı çağıracağına karar verir, parametreleri çıkarır.
  3. İlgili deterministik modül çalıştırılır (kararı algoritma/veri verir).
  4. Sonuç doğal dille açıklanır.
  5. Yapılandırılmış sonuç + doğal dil cevabı döndürülür.

Hata yönetimi (G3.4):
  - LLM yanlış/eksik parametre verirse Pydantic ile makul varsayılana çekilir.
  - LLM/broker erişilemezse anahtar-kelime tabanlı yedeğe + şablon cevaba düşülür.
  - Uygun boş yer yoksa kullanıcıya nazikçe açıklanır.
"""

import re

import config
from algorithm import allocator
from backend import database, log, parking_state, predict, schemas
from llm import tools
from llm.client import get_client, is_quota_error

logger = log.get(__name__)

_KNOWN_TOOLS = {t["name"] for t in tools.TOOLS}


# ---------------------------------------------------------------------------
# Parametre / metin yardımcıları
# ---------------------------------------------------------------------------
def _coerce_int(value):
    """Değeri pozitif tamsayıya çek; geçersizse None."""
    if value is None:
        return None
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _normalize_args(args):
    """LLM'den gelen parametreleri Pydantic ile doğrula ve eksikleri varsayılana çek."""
    return schemas.parse_params(args)


def _extract_duration(text):
    """Metinden kalış süresini (saat) çıkar: \"2 saat\", \"bütün gün\" vb."""
    t = text.lower()
    if any(w in t for w in ("bütün gün", "butun gun", "tüm gün", "tum gun", "tam gün")):
        return 8
    if any(w in t for w in ("yarım gün", "yarim gun")):
        return 4
    m = re.search(r"(\d+)\s*saat", t)
    if m:
        return _coerce_int(m.group(1))
    return None


def _extract_horizon(text):
    """Metinden tahmin ufkunu (dakika) çıkar: \"15 dk\", \"yarım saat\", \"2 saat\"."""
    t = text.lower()
    if any(w in t for w in ("yarım saat", "yarim saat")):
        return 30
    m = re.search(r"(\d+)\s*(dakika|dk|dak)", t)
    if m:
        return _coerce_int(m.group(1))
    m = re.search(r"(\d+)\s*saat", t)
    if m:
        h = _coerce_int(m.group(1))
        return h * 60 if h else None
    return None


def _detect_intent(text):
    """LLM yokken niyeti anahtar-kelimeyle sapta. Belirsizse 'find' (en güvenli)."""
    t = text.lower()
    predict_kw = ("bulur mu", "dolar mı", "dolar mi", "dolacak", "tahmin", "birazdan",
                  "az sonra", "ileride", "sonra yer", "doluyor mu")
    if any(w in t for w in predict_kw):
        return "predict_availability"
    stats_kw = ("kaç boş", "kac bos", "kaç yer", "kac yer", "doluluk", "ne kadar dolu",
                "boş yer var", "bos yer var", "yer var mı", "yer var mi", "kaç araç",
                "dolu mu", "ne kadar boş", "durum ne")
    if any(w in t for w in stats_kw):
        return "get_parking_stats"
    return "find_best_parking_spot"


def _keyword_fallback(user_text):
    """LLM erişilemezse basit anahtar-kelime çıkarımı (find aracı parametreleri)."""
    t = user_text.lower()
    args = {}

    if any(w in t for w in ("engelli", "disabled", "tekerlek")):
        args["vehicle_type"] = "disabled"
    if any(w in t for w in ("elektrik", "şarj", "sarj", "ev ", "elektrikli", "tesla")):
        args["vehicle_type"] = "ev"
        args["needs_charging"] = True

    # "uzak" ifadesi yönü tersine çevirir: çıkışa uzak = girişe yakın (ve tersi)
    far = any(w in t for w in ("uzak", "uzağa", "uzakta"))
    mentions_exit = any(w in t for w in ("çıkış", "cikis", "çıkışa"))
    mentions_entrance = any(w in t for w in ("giriş", "giris", "girişe"))
    if mentions_exit:
        args["preference"] = "nearest_entrance" if far else "nearest_exit"
    elif mentions_entrance:
        args["preference"] = "nearest_exit" if far else "nearest_entrance"

    args["duration_hours"] = _extract_duration(user_text)
    return _normalize_args(args)


# ---------------------------------------------------------------------------
# Açıklama (find aracı için)
# ---------------------------------------------------------------------------
def _fallback_explanation(result, params):
    """LLM açıklaması alınamazsa (ya da LLM_EXPLAIN kapalıysa) şablon Türkçe cevap."""
    if result is None:
        return "Üzgünüm, isteğinize uygun boş bir park yeri bulamadım. Otopark dolu olabilir."
    spot = result["spot"]
    p = params or {}
    tip = {"normal": "normal", "disabled": "engelli",
           "ev_charging": "şarjlı"}.get(spot["type"], spot["type"])
    dur = p.get("duration_hours")
    dist = result.get("distance")
    walk = result.get("walk_to_exit")

    # İstenen özel tip (engelli/şarjlı) o an boş değilse dürüstçe belirt
    want = None
    if p.get("vehicle_type") == "disabled":
        want = "disabled"
    elif p.get("vehicle_type") == "ev" or p.get("needs_charging"):
        want = "ev_charging"
    note = ""
    if want and spot["type"] != want:
        wname = "engelli" if want == "disabled" else "şarjlı"
        note = f"Şu an boş {wname} yer kalmadı, size en uygun {tip} yeri ayarladım. "

    base = f"{note}Sizi {result['spot_id']} numaralı {tip} park yerine yönlendirdim"
    if dur:
        if dur <= config.SHORT_STAY_HINT_HOURS:
            return (f"{base}. Kısa süre (~{dur} saat) kalacağınız için girişe yakın "
                    f"bir yer seçtim; hızlı giriş-çıkış için ideal "
                    f"(girişten ~{dist} birim).")
        if dur >= config.LONG_STAY_HINT_HOURS:
            return (f"{base}. Uzun süre (~{dur} saat) kalacağınız için biraz daha "
                    f"içeride bir yer seçtim; kapı önlerini kısa süreli araçlara "
                    f"bıraktık (girişten ~{dist} birim).")
        return (f"{base}. ~{dur} saatlik kalışınıza göre dengeli bir konum seçtim "
                f"(girişten ~{dist} birim).")
    return (f"{base}. Girişten yaklaşık {dist} birim, çıkışa {walk} birim uzaklıkta.")


# ---------------------------------------------------------------------------
# Araç işleyicileri
# ---------------------------------------------------------------------------
def _handle_find(user_text, args, spots, entrance, client, source, llm_failed, quota_hit):
    """find_best_parking_spot: en uygun yeri bul, açıkla, kararı logla."""
    if source == "llm":
        params = _normalize_args(args)
    else:
        params = _keyword_fallback(user_text)
    # LLM süreyi atlamış olabilir; metinden yedek çıkarımla tamamla
    if params.get("duration_hours") is None:
        params["duration_hours"] = _extract_duration(user_text)

    # Kararı algoritma verir (deterministik)
    result = allocator.find_best_parking_spot(spots=spots, entrance=entrance, **params)

    # Açıklama: LLM başarısızsa/kapalıysa şablon; değilse LLM
    if llm_failed or not config.LLM_EXPLAIN:
        reply = _fallback_explanation(result, params)
        if quota_hit:
            reply = "(LLM günlük kotası doldu, basit modda yanıtlıyorum.) " + reply
    else:
        try:
            reply = client.explain(user_text, result, params)
            if not reply:
                reply = _fallback_explanation(result, params)
        except Exception as e:
            logger.warning("açıklama alınamadı, şablona düşülüyor: %s", e)
            reply = _fallback_explanation(result, params)

    # Karar/oturum logu (yalnız gerçek istekte; testte spots enjekte edilir, atla)
    if spots is None:
        try:
            database.log_assignment(dict(params, entrance=entrance), result, source)
        except Exception as e:
            logger.warning("karar loglanamadı: %s", e)

    return {"reply": reply, "result": result, "params": params, "source": source}


def _handle_stats(args, source, quota_hit):
    """get_parking_stats: anlık doluluk/boş yer durumunu özetle."""
    total, occ, empty = database.counts()
    spots = parking_state.get_state()
    free_ev = sum(1 for s in spots if s["type"] == "ev_charging"
                  and not s["occupied"] and not s.get("reserved"))
    free_dis = sum(1 for s in spots if s["type"] == "disabled"
                   and not s["occupied"] and not s.get("reserved"))
    pct = round(occ / total * 100) if total else 0

    vt = (args or {}).get("vehicle_type")
    if vt == "ev":
        reply = f"Şu an {free_ev} adet boş elektrikli (şarjlı) yer var."
    elif vt == "disabled":
        reply = f"Şu an {free_dis} adet boş engelli yeri var."
    else:
        reply = (f"Otoparkta {total} yerin {occ} tanesi dolu (%{pct}), {empty} yer boş. "
                 f"Bunların {free_ev}'i şarjlı, {free_dis}'i engelli yeri.")
    if quota_hit:
        reply = "(LLM kotası doldu, basit modda.) " + reply
    return {"reply": reply, "result": None,
            "params": {"intent": "stats", "vehicle_type": vt},
            "source": source,
            "stats": {"total": total, "occupied": occ, "empty": empty,
                      "free_ev": free_ev, "free_disabled": free_dis}}


def _handle_predict(args, user_text, source, quota_hit):
    """predict_availability: yakın gelecek doluluk tahmini."""
    horizon = _coerce_int((args or {}).get("horizon_min")) or _extract_horizon(user_text) or 15
    pred = predict.predict(horizon_min=horizon)
    reply = pred["advice"]
    if quota_hit:
        reply = "(LLM kotası doldu, basit modda.) " + reply
    return {"reply": reply, "result": None,
            "params": {"intent": "predict", "horizon_min": horizon},
            "source": source, "prediction": pred}


# ---------------------------------------------------------------------------
# Giriş noktası
# ---------------------------------------------------------------------------
def handle_request(user_text, spots=None, client=None, entrance=None):
    """
    Sürücünün serbest metnini işleyip sonucu döndürür.

    entrance: sürücünün girdiği kapı düğümü (UI'daki giriş seçiminden). Verilirse
    sürüş mesafesi yalnızca bu girişten hesaplanır; None ise en yakın giriş.

    Döner (dict): reply (str), result (allocator sonucu ya da None),
    params (kullanılan parametreler), source ("llm" | "fallback").
    """
    client = client or get_client()
    source = "llm"
    llm_failed = False
    quota_hit = False
    tool_name = "find_best_parking_spot"
    args = {}

    # 1) LLM hangi aracı çağıracağına karar verir (hata olursa keyword yedeği)
    try:
        call = client.extract_tool_call(user_text)
        if call and call.get("name") in _KNOWN_TOOLS:
            tool_name = call["name"]
            args = call.get("args") or {}
        else:
            tool_name = _detect_intent(user_text)
            source = "fallback"
    except Exception as e:
        logger.warning("LLM erişilemedi, yedeğe düşülüyor: %s", e)
        tool_name = _detect_intent(user_text)
        source = "fallback"
        llm_failed = True
        quota_hit = is_quota_error(e)

    # 2) İlgili deterministik araç çalışır
    if tool_name == "get_parking_stats":
        return _handle_stats(args, source, quota_hit)
    if tool_name == "predict_availability":
        return _handle_predict(args, user_text, source, quota_hit)
    return _handle_find(user_text, args, spots, entrance, client,
                        source, llm_failed, quota_hit)

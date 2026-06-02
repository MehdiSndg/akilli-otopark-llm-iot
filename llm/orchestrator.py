"""
orchestrator.py — Doğal dil -> araç çağrısı -> doğal dil cevap.

Akış (CLAUDE.md Bölüm 6):
  1. Sürücünün serbest metni LLM'e gönderilir (function calling araçlarıyla).
  2. LLM parametreleri çıkarıp find_best_parking_spot aracını çağırır.
  3. Bu çağrı algorithm.allocator.find_best_parking_spot'u tetikler.
  4. Sonuç LLM'e geri verilir, LLM doğal dille açıklar.
  5. Hem yapılandırılmış sonuç (Pygame için) hem doğal dil cevabı döndürülür.

Hata yönetimi (G3.4):
  - LLM yanlış/eksik parametre verirse makul varsayılanlara düşülür.
  - Uygun boş yer yoksa kullanıcıya nazikçe açıklanır.
  - LLM/broker erişilemezse anahtar-kelime tabanlı yedeğe ve şablon cevaba düşülür.
"""

import re

import config
from algorithm import allocator
from llm import tools
from llm.client import get_client, is_quota_error


def _coerce_duration(value):
    """Kalış süresini (saat) pozitif tamsayıya çek; geçersizse None."""
    if value is None:
        return None
    try:
        hours = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return hours if hours > 0 else None


def _normalize_args(args):
    """LLM'den gelen parametreleri doğrula ve eksikleri varsayılana çek (G3.4)."""
    args = dict(args or {})
    out = dict(tools.DEFAULTS)

    vt = str(args.get("vehicle_type", "")).lower()
    if vt in tools.VEHICLE_TYPES:
        out["vehicle_type"] = vt

    pref = str(args.get("preference", "")).lower()
    if pref in tools.PREFERENCES:
        out["preference"] = pref

    out["needs_charging"] = bool(args.get("needs_charging", False))
    out["duration_hours"] = _coerce_duration(args.get("duration_hours"))

    # Tutarlılık: elektrikli araç şarj ister sayılır
    if out["vehicle_type"] == "ev":
        out["needs_charging"] = True
    return out


def _extract_duration(text):
    """Metinden kalış süresini (saat) çıkar: \"2 saat\", \"bütün gün\" vb."""
    t = text.lower()
    if any(w in t for w in ("bütün gün", "butun gun", "tüm gün", "tum gun", "tam gün")):
        return 8
    if any(w in t for w in ("yarım gün", "yarim gun")):
        return 4
    m = re.search(r"(\d+)\s*saat", t)
    if m:
        return _coerce_duration(m.group(1))
    return None


def _keyword_fallback(user_text):
    """LLM erişilemezse basit anahtar-kelime çıkarımı (sistem yine de çalışsın)."""
    t = user_text.lower()
    args = dict(tools.DEFAULTS)

    if any(w in t for w in ("engelli", "disabled", "tekerlek")):
        args["vehicle_type"] = "disabled"
    if any(w in t for w in ("elektrik", "şarj", "sarj", "ev ", "elektrikli")):
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


def _fallback_explanation(result, params):
    """LLM açıklaması alınamazsa (ya da LLM_EXPLAIN kapalıysa) şablon Türkçe cevap.

    Maliyet fonksiyonu mantığını sade dille anlatır: kısa kalış girişe yakın,
    uzun kalış daha içeride. Mesafe olarak GİRİŞTEN sürüş mesafesini kullanır
    (kararı veren büyüklük budur) — eskiden hep 'çıkışa uzaklık' deniyordu, bu
    süre-tabanlı yerleştirmede kafa karıştırıcıydı."""
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


def handle_request(user_text, spots=None, client=None, entrance=None):
    """
    Sürücünün serbest metnini işleyip sonucu döndürür.

    entrance: sürücünün fiziksel olarak girdiği kapı düğümü (UI'daki Sol/Sağ
    giriş seçiminden gelir). Verilirse sürüş mesafesi YALNIZCA bu girişten
    hesaplanır; None ise en yakın giriş kullanılır.

    Döner (dict):
        reply    : sürücüye gösterilecek doğal dil cevabı (str)
        result   : allocator sonucu (spot_id, path, distance, ...) ya da None
        params   : kullanılan parametreler (vehicle_type, preference, ...)
        source   : "llm" | "fallback"  (parametreler nereden çıkarıldı)
    """
    client = client or get_client()
    source = "llm"
    llm_failed = False         # extract çağrısı hata verdiyse explain'i boşuna deneme
    quota_hit = False          # 429 ise kullanıcıya nazik not düş

    # 1) Parametreleri çıkar (LLM function calling; hata olursa keyword yedeği)
    try:
        call = client.extract_tool_call(user_text)
        if call and call.get("args"):
            params = _normalize_args(call["args"])
        else:
            # LLM araç çağırmadıysa metinden yedekle çıkar
            params = _keyword_fallback(user_text)
            source = "fallback"
    except Exception as e:
        print(f"[orchestrator] LLM erişilemedi, yedeğe düşülüyor: {e}")
        params = _keyword_fallback(user_text)
        source = "fallback"
        llm_failed = True
        quota_hit = is_quota_error(e)

    # LLM süreyi atlamış olabilir; metinden yedek çıkarımla tamamla
    if params.get("duration_hours") is None:
        params["duration_hours"] = _extract_duration(user_text)

    # 2) Kararı algoritma verir (deterministik)
    result = allocator.find_best_parking_spot(spots=spots, entrance=entrance, **params)

    # 3) Sonucu doğal dille açıkla.
    #    - LLM zaten başarısızsa (ör. kota) ikinci çağrıyı boşuna deneme.
    #    - config.LLM_EXPLAIN kapalıysa kasıtlı olarak tek çağrı modundayız
    #      (kota tasarrufu): zengin şablon açıklamayı kullan.
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
            print(f"[orchestrator] açıklama alınamadı, şablona düşülüyor: {e}")
            reply = _fallback_explanation(result, params)

    return {"reply": reply, "result": result, "params": params, "source": source}

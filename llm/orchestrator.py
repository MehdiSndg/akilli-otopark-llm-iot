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

from algorithm import allocator
from llm import tools
from llm.client import get_client


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

    # Tutarlılık: elektrikli araç şarj ister sayılır
    if out["vehicle_type"] == "ev":
        out["needs_charging"] = True
    return out


def _keyword_fallback(user_text):
    """LLM erişilemezse basit anahtar-kelime çıkarımı (sistem yine de çalışsın)."""
    t = user_text.lower()
    args = dict(tools.DEFAULTS)

    if any(w in t for w in ("engelli", "disabled", "tekerlek")):
        args["vehicle_type"] = "disabled"
    if any(w in t for w in ("elektrik", "şarj", "sarj", "ev ", "elektrikli")):
        args["vehicle_type"] = "ev"
        args["needs_charging"] = True

    if any(w in t for w in ("çıkış", "cikis", "çıkışa")):
        args["preference"] = "nearest_exit"
    elif any(w in t for w in ("giriş", "giris", "girişe")):
        args["preference"] = "nearest_entrance"

    return _normalize_args(args)


def _fallback_explanation(result, params):
    """LLM açıklaması alınamazsa şablon Türkçe cevap (G3.4)."""
    if result is None:
        return "Üzgünüm, isteğinize uygun boş bir park yeri bulamadım. Otopark dolu olabilir."
    spot = result["spot"]
    tip = {"normal": "normal", "disabled": "engelli", "ev_charging": "şarjlı"}.get(spot["type"], spot["type"])
    return (
        f"Sizi {result['spot_id']} numaralı {tip} park yerine yönlendirdim. "
        f"Çıkışa yaklaşık {result['walk_to_exit']} birim uzaklıkta."
    )


def handle_request(user_text, spots=None, client=None):
    """
    Sürücünün serbest metnini işleyip sonucu döndürür.

    Döner (dict):
        reply    : sürücüye gösterilecek doğal dil cevabı (str)
        result   : allocator sonucu (spot_id, path, distance, ...) ya da None
        params   : kullanılan parametreler (vehicle_type, preference, needs_charging)
        source   : "llm" | "fallback"  (parametreler nereden çıkarıldı)
    """
    client = client or get_client()
    source = "llm"

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

    # 2) Kararı algoritma verir (deterministik)
    result = allocator.find_best_parking_spot(spots=spots, **params)

    # 3) Sonucu doğal dille açıkla (LLM; hata olursa şablon)
    try:
        reply = client.explain(user_text, result, params)
        if not reply:
            reply = _fallback_explanation(result, params)
    except Exception as e:
        print(f"[orchestrator] açıklama alınamadı, şablona düşülüyor: {e}")
        reply = _fallback_explanation(result, params)

    return {"reply": reply, "result": result, "params": params, "source": source}

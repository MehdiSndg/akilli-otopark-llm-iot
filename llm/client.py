"""
client.py — LLM sağlayıcı soyutlaması.

Tüm LLM çağrıları bu arayüzün arkasındadır; orchestrator hangi sağlayıcının
kullanıldığını bilmez. Sağlayıcı config.LLM_PROVIDER ile seçilir.

Arayüz (LLMClient):
    extract_tool_call(user_text) -> {"name": ..., "args": {...}} | None
        Function calling ile sürücü metninden parametreleri çıkarır.
    explain(user_text, result, params) -> str
        Algoritmanın bulduğu sonucu doğal dille (Türkçe) açıklar.

Şu an Gemini tam implemente; diğer sağlayıcılar aynı arayüzle kolayca eklenebilir.
"""

import time
from abc import ABC, abstractmethod

import config
from llm import tools


def is_quota_error(exc):
    """Hata günlük kota/oran limiti (429) mı? Bunlarda yeniden denemek anlamsız."""
    msg = str(exc)
    return ("429" in msg or "RESOURCE_EXHAUSTED" in msg
            or "quota" in msg.lower() or "rate limit" in msg.lower())


def _retry_transient(fn, attempts=3, base_delay=1.0):
    """Geçici hatalarda (503 aşırı yük) kısa beklemeyle birkaç kez yeniden dene.

    Kota/oran limiti (429) geçici sayılmaz: beklemenin faydası yok (saatlerce
    sürebilir), hemen yükselt ki çağıran keyword yedeğine düşsün."""
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            msg = str(e)
            transient = "503" in msg or "UNAVAILABLE" in msg or "overloaded" in msg.lower()
            if not transient or i == attempts - 1:
                raise
            last = e
            time.sleep(base_delay * (i + 1))   # 1s, 2s, ...
    raise last


class LLMClient(ABC):
    """Tüm sağlayıcıların uyduğu ortak arayüz."""

    @abstractmethod
    def extract_tool_call(self, user_text):
        ...

    @abstractmethod
    def explain(self, user_text, result, params):
        ...


def _build_explain_prompt(user_text, result, params):
    """Sonucu açıklaması için LLM'e verilecek metni hazırla (sağlayıcıdan bağımsız)."""
    if result is None:
        return (
            f"Sürücü şöyle dedi: \"{user_text}\".\n"
            "Ne yazık ki bu kritere uygun boş park yeri bulunamadı (otopark dolu "
            "olabilir).\n"
            "Sürücüye Türkçe, kısa ve nazik bir şekilde uygun yer bulunamadığını açıkla."
        )
    spot = result["spot"]
    p = params or {}
    dur = p.get("duration_hours")
    pref = p.get("preference")
    exit_d = result.get("dist_to_exit")
    walk = result.get("walk_to_mall", result.get("walk_to_exit"))
    dist = result.get("distance")

    # Tercihe göre TEK ve doğru "manşet mesafe" — LLM'in yanlış kapı iddia etmesini önler
    if pref == "nearest_exit":
        headline = (f"Sürücü ÇIKIŞA yakın istedi. Bu yer otopark araç çıkışına "
                    f"(ÇIKIŞ kapısı) {exit_d} birim. SADECE bunu vurgula.")
    elif pref == "nearest_entrance":
        headline = (f"Sürücü GİRİŞE yakın istedi. Bu yer otopark giriş kapısına "
                    f"{dist} birim. SADECE bunu vurgula. (AVM/çıkış DEME.)")
    elif dur:
        headline = (f"Kalış süresi {dur} saat. Yer maliyet fonksiyonuyla seçildi: kısa "
                    f"kalan kapıya yakın, uzun kalan derine. Girişten {dist} birim.")
    else:
        headline = (f"Belirgin tercih yok. Girişten {dist} birim; AVM yaya kapısına "
                    f"{walk} birim yürüme.")

    return (
        f"Sürücü şöyle dedi: \"{user_text}\".\n"
        f"Seçilen yer: {result['spot_id']} (tip: {spot['type']}).\n"
        f"{headline}\n\n"
        "KURALLAR:\n"
        "- 'Otopark çıkışı' (araçla ayrılınan ÇIKIŞ kapısı) ile 'AVM kapısı' "
        "(yürüyerek mağazaya girilen kapı) AYRI şeylerdir; ASLA karıştırma.\n"
        "- Yalnızca yukarıda VERİLEN mesafeyi kullan; başka yakınlık/mesafe UYDURMA.\n"
        "- Türkçe, tek-iki cümle, sıcak ama abartısız. Park yeri kimliğini belirt."
    )


# ---------------------------------------------------------------------------
# Gemini (Google) — varsayılan sağlayıcı
# ---------------------------------------------------------------------------
class GeminiClient(LLMClient):
    def __init__(self):
        from google import genai           # tembel import (paket yoksa diğerleri çalışsın)
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY boş. .env dosyasına anahtarı gir.")
        self._genai = genai
        self._client = genai.Client(api_key=config.GEMINI_API_KEY)
        self._model = config.LLM_MODEL
        self._tool = self._build_tools()

    def _build_tools(self):
        """Nötr tools.TOOLS tanımlarını tek bir Gemini Tool'una (çok fonksiyon) çevir."""
        from google.genai import types
        type_map = {"string": "STRING", "boolean": "BOOLEAN",
                    "integer": "INTEGER", "number": "NUMBER"}
        decls = []
        for t in tools.TOOLS:
            props = {}
            for name, spec in t["parameters"].items():
                gem_type = type_map.get(spec["type"], "STRING")
                kwargs = {"type": gem_type, "description": spec.get("description", "")}
                if "enum" in spec:
                    kwargs["enum"] = spec["enum"]
                props[name] = types.Schema(**kwargs)
            # Parametresiz araçlarda da geçerli OBJECT şeması ver
            schema = types.Schema(type="OBJECT", properties=props,
                                  required=t.get("required", []))
            decls.append(types.FunctionDeclaration(
                name=t["name"], description=t["description"], parameters=schema))
        return types.Tool(function_declarations=decls)

    def extract_tool_call(self, user_text):
        from google.genai import types
        cfg = types.GenerateContentConfig(
            system_instruction=tools.SYSTEM_PROMPT,
            tools=[self._tool],
            # Aracı biz çalıştıracağız; otomatik çağrıyı kapat
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        resp = _retry_transient(lambda: self._client.models.generate_content(
            model=self._model, contents=user_text, config=cfg,
        ))
        calls = resp.function_calls or []
        if not calls:
            return None
        return {"name": calls[0].name, "args": dict(calls[0].args)}

    def explain(self, user_text, result, params):
        prompt = _build_explain_prompt(user_text, result, params)
        resp = _retry_transient(lambda: self._client.models.generate_content(
            model=self._model, contents=prompt))
        return (resp.text or "").strip()


# ---------------------------------------------------------------------------
# Diğer sağlayıcılar — aynı arayüzle eklenebilir (şimdilik yer tutucu)
# ---------------------------------------------------------------------------
class _NotImplementedClient(LLMClient):
    def __init__(self, name):
        self._name = name

    def _fail(self):
        raise NotImplementedError(
            f"'{self._name}' sağlayıcısı henüz eklenmedi. .env'de LLM_PROVIDER=gemini "
            f"kullan ya da bu sınıfı GeminiClient'i örnek alarak implemente et."
        )

    def extract_tool_call(self, user_text):
        self._fail()

    def explain(self, user_text, result, params):
        self._fail()


_REGISTRY = {
    "gemini": GeminiClient,
}


def get_client(provider=None):
    """config.LLM_PROVIDER'a (ya da verilen provider'a) göre uygun istemciyi döndürür."""
    provider = provider or config.LLM_PROVIDER
    cls = _REGISTRY.get(provider)
    if cls is None:
        return _NotImplementedClient(provider)
    return cls()

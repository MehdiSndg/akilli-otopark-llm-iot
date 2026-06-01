"""
tools.py — Function calling araç tanımı (sağlayıcıdan bağımsız nötr şema).

Burada aracı tek ve nötr bir biçimde tanımlarız; her LLM sağlayıcısı (Gemini,
Anthropic, ...) bu tanımı client.py içinde kendi formatına çevirir. Böylece
sağlayıcı değişse de araç tanımı tek yerde kalır.
"""

# Geçerli enum değerleri (doğrulama ve varsayılanlar için)
VEHICLE_TYPES = ("normal", "disabled", "ev")
PREFERENCES = ("nearest_entrance", "nearest_exit", "any")

# Parametre eksik/hatalı gelirse düşülecek makul varsayılanlar (G3.4)
DEFAULTS = {
    "vehicle_type": "normal",
    "preference": "any",
    "needs_charging": False,
    "duration_hours": None,        # belirtilmezse süreye göre yerleştirme yapılmaz
}

# Aracın nötr tanımı (client.py sağlayıcı formatına çevirir)
TOOL = {
    "name": "find_best_parking_spot",
    "description": (
        "Sürücünün isteğine göre en uygun BOŞ park yerini bulur. "
        "Sürücü doğal dille konuştuğunda bu aracı çağır."
    ),
    "parameters": {
        "vehicle_type": {
            "type": "string",
            "enum": list(VEHICLE_TYPES),
            "description": "Araç tipi: normal araç, engelli (disabled) veya "
                           "elektrikli (ev).",
        },
        "preference": {
            "type": "string",
            "enum": list(PREFERENCES),
            "description": "Sürücü tercihi: girişe yakın (nearest_entrance), "
                           "çıkışa yakın (nearest_exit) veya farketmez (any).",
        },
        "needs_charging": {
            "type": "boolean",
            "description": "Sürücü şarj istiyor mu? Elektrikli araçlarda genelde true.",
        },
        "duration_hours": {
            "type": "integer",
            "description": "Sürücünün tahmini kalış süresi (saat). Sürücü ne kadar "
                           "kalacağını söylerse (ör. \"2 saat\", \"yarım gün\") bunu "
                           "saate çevir; söylemezse bu parametreyi boş bırak.",
        },
    },
    "required": ["vehicle_type", "preference", "needs_charging"],
}

# LLM'e verilecek sistem yönergesi
SYSTEM_PROMPT = (
    "Sen bir akıllı otopark yönlendirme asistanısın. Sürücüler sana doğal dille "
    "nasıl bir park yeri istediklerini söyler. Görevin, isteği anlayıp "
    "find_best_parking_spot aracını uygun parametrelerle çağırmaktır. "
    "Park yerine SEN karar vermezsin; kararı yönlendirme algoritması verir. "
    "Bilgi eksikse makul varsayılanlar kullan: araç tipi belirtilmemişse normal, "
    "tercih belirtilmemişse any, şarj belirtilmemişse false. "
    "Elektrikli/şarj ima ediliyorsa vehicle_type=ev ve needs_charging=true yap. "
    "Sürücü kalış süresini belirtirse (ör. \"2 saat\", \"bütün gün\") duration_hours'ı "
    "saate çevirerek doldur; belirtmezse boş bırak. "
    "Tercih yalnızca yakınlık ifade eder; sürücü bir noktadan UZAK olmak isterse "
    "diğerine yakını seç: \"çıkışa uzak\" -> nearest_entrance, \"girişe uzak\" -> "
    "nearest_exit."
)

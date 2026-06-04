"""
tools.py — Function calling araç tanımı (sağlayıcıdan bağımsız nötr şema).

Burada aracı tek ve nötr bir biçimde tanımlarız; her LLM sağlayıcısı (Gemini,
Anthropic, ...) bu tanımı client.py içinde kendi formatına çevirir. Böylece
sağlayıcı değişse de araç tanımı tek yerde kalır.
"""

# Geçerli enum değerleri (doğrulama ve varsayılanlar için)
VEHICLE_TYPES = ("normal", "disabled", "ev")
# Üç AYRI kapıya yakınlık: otopark araç girişi / araç çıkışı / AVM yaya kapısı.
PREFERENCES = ("nearest_entrance", "nearest_exit", "nearest_mall", "any")

# Parametre eksik/hatalı gelirse düşülecek makul varsayılanlar (G3.4)
DEFAULTS = {
    "vehicle_type": "normal",
    "preference": "any",
    "needs_charging": False,
    "duration_hours": None,        # belirtilmezse süreye göre yerleştirme yapılmaz
}

# --- Araç 1: en uygun park yerini bul (asıl yönlendirme) --------------------
TOOL_FIND = {
    "name": "find_best_parking_spot",
    "description": (
        "Sürücünün isteğine göre en uygun BOŞ park yerini bulur. Sürücü bir yer "
        "ARADIĞINDA (park etmek/yönlendirilmek istediğinde) bu aracı çağır."
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
            "description": "Sürücü hangi KAPIYA yakın istiyor (üçü AYRI yerdir): "
                           "otopark/araç GİRİŞİ (nearest_entrance); otopark/araç "
                           "ÇIKIŞI, hızlı çıkış (nearest_exit); AVM yaya kapısı / "
                           "mağaza girişi / alışveriş merkezine yakın, az yürüme "
                           "(nearest_mall); farketmez (any). DİKKAT: 'AVM girişi' "
                           "otopark girişi DEĞİLDİR -> nearest_mall.",
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
        "spot_id": {
            "type": "string",
            "description": "Sürücü BELİRLİ bir park yeri numarası söylerse (ör. "
                           "\"D-34'e koy\", \"A-7 olsun\", \"C12 istiyorum\") o yer "
                           "kimliğini buraya yaz (ör. \"D-34\"). Söylemezse boş bırak.",
        },
    },
    "required": ["vehicle_type", "preference", "needs_charging"],
}

# --- Araç 2: anlık doluluk sorgula ("kaç boş yer var?") ---------------------
TOOL_STATS = {
    "name": "get_parking_stats",
    "description": (
        "Otoparkın ANLIK doluluk durumunu sorar: kaç yer dolu/boş, engelli ve "
        "elektrikli boş yer var mı. Sürücü yer aramadan yalnızca durum/doluluk "
        "sorduğunda (ör. \"kaç boş yer var?\", \"engelli yer var mı?\") bu aracı çağır."
    ),
    "parameters": {
        "vehicle_type": {
            "type": "string",
            "enum": list(VEHICLE_TYPES),
            "description": "İlgili araç tipi için boş yer sayısı sorulduysa belirt; "
                           "yoksa boş bırak.",
        },
    },
    "required": [],
}

# --- Araç 3: yakın gelecek doluluk tahmini ("yer bulur muyum?") -------------
TOOL_PREDICT = {
    "name": "predict_availability",
    "description": (
        "Yakın gelecekteki doluluğu TAHMİN eder (eğilim + gün-içi örüntü). Sürücü "
        "ileriye dönük sorduğunda (ör. \"birazdan yer bulur muyum?\", \"15 dk sonra "
        "dolar mı?\", \"otopark dolacak mı?\") bu aracı çağır."
    ),
    "parameters": {
        "horizon_min": {
            "type": "integer",
            "description": "Kaç dakika sonrası için tahmin isteniyor (ör. \"yarım "
                           "saat\"=30). Belirtilmezse 15 varsay.",
        },
    },
    "required": [],
}

# Tek nötr araç (geriye dönük) + tüm araçların listesi
TOOL = TOOL_FIND
TOOLS = [TOOL_FIND, TOOL_STATS, TOOL_PREDICT]

# LLM'e verilecek sistem yönergesi
SYSTEM_PROMPT = (
    "Sen bir akıllı otopark yönlendirme ASİSTANISIN — tek komut çevirici değil, "
    "konuşan bir yardımcısın. Sürücünün niyetine göre uygun aracı seç:\n"
    "- Bir yer arıyor/park etmek istiyorsa -> find_best_parking_spot.\n"
    "- Anlık doluluk/boş yer soruyorsa -> get_parking_stats.\n"
    "- Yakın gelecekteki durumu/tahmini soruyorsa -> predict_availability.\n"
    "Park yerine SEN karar vermezsin; kararı yönlendirme algoritması verir. "
    "Bilgi eksikse makul varsayılanlar kullan: araç tipi normal, tercih any, "
    "şarj false. Elektrikli/şarj ima ediliyorsa vehicle_type=ev ve "
    "needs_charging=true yap. Kalış süresi belirtilirse (ör. \"2 saat\", \"bütün "
    "gün\") duration_hours'ı saate çevir; belirtilmezse boş bırak. "
    "Sürücü BELİRLİ bir park yeri söylerse (ör. \"D-34'e koy\", \"A-7 olsun\") "
    "spot_id'yi o yerin kimliğiyle doldur (ör. \"D-34\"). "
    "TERCİH (preference) ÜÇ AYRI KAPIYI ayırt eder:\n"
    "- 'otopark girişi / araç girişi / girişe yakın' -> nearest_entrance\n"
    "- 'otopark çıkışı / araç çıkışı / çıkışa yakın / hızlı çıkmak' -> nearest_exit\n"
    "- 'AVM girişi / AVM kapısı / mağazaya yakın / alışveriş merkezine yakın / "
    "az yürümek / yaya kapısı' -> nearest_mall\n"
    "ÇOK ÖNEMLİ: 'AVM girişi' otopark girişi DEĞİLDİR; nearest_mall kullan. "
    "Tercih yakınlık ifade eder; bir noktadan UZAK isteniyorsa diğerine yakını seç: "
    "\"çıkışa uzak\" -> nearest_entrance, \"girişe uzak\" -> nearest_exit. "
    "Türkçe ya da İngilizce — sürücü hangi dilde yazarsa o dilde anla."
)

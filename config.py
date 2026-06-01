"""
config.py — Projedeki tüm ayarların tek merkezi.

Park yeri sayısı, MQTT bilgileri, LLM sağlayıcı/model adı, Pygame pencere
boyutu gibi sabitler burada tutulur. Kod içine sabit gömme; buradan oku.
Sırlar (API anahtarı) burada DEĞİL, .env dosyasında tutulur.
"""

import os
from dotenv import load_dotenv

# .env varsa ortam değişkenlerine yükle (yoksa sorun değil)
load_dotenv()


# ---------------------------------------------------------------------------
# Otopark düzeni
# ---------------------------------------------------------------------------
NUM_SPOTS = 50                 # Toplam park yeri sayısı (Bölüm 12: başlangıç 50)

# AVM tarzı gerçekçi düzen: çift sıralı park bantları + ızgara yol ağı.
# - N_AISLES yatay araç yolu (aisle); aralarında park bandı.
# - Her bant 2 sıra park yeri içerir (üst sıra üstteki yoldan, alt sıra alttaki
#   yoldan girilir = "çift yüklemeli" / double-loaded aisle).
# - Dikey bağlantı yolları (cross-lane) yatay yolları birbirine bağlar; böylece
#   A* sol/orta/sağ dikey yoldan en kısa rotayı seçebilir.
N_AISLES = 6                   # yatay araç yolu sayısı
BLOCK_W = 6                    # bir bloktaki park sütunu sayısı
N_BLOCKS_X = 4                 # yatayda blok sayısı (bloklar dikey yollarla ayrılır)
SPOTS_PER_ROW = BLOCK_W * N_BLOCKS_X         # toplam park sütunu = 24
ROAD_GAP = 2.2                 # bloklar arası / kenar dikey yol genişliği (geniş, gerçekçi)

N_BANDS = N_AISLES - 1                       # park bandı sayısı (her biri 2 sıra)
NUM_SPOTS = N_BANDS * 2 * SPOTS_PER_ROW      # toplam park yeri = 5*2*24 = 240

# Özel yer sayıları (en üst bandın üst sırasında kümeli; AVM kapısına yakın)
NUM_DISABLED_SPOTS = 6         # Engelli park yeri
NUM_EV_SPOTS = 10              # Elektrikli şarjlı park yeri


# Başlangıç doluluk oranı (DB tohumu ve simülatör başlangıç durumu için)
INITIAL_OCCUPANCY_RATE = 0.55

# Simülatör davranışı
SIM_INTERVAL_SEC = 1.0         # Her tur arası bekleme (saniye)
SIM_CHANGES_PER_TICK = 2       # (geriye dönük) tur başına temel değişim sayısı
DAY_LENGTH_SEC = 240           # Bir simüle günün gerçek saniye süresi (demo: 4 dk/gün)


# ---------------------------------------------------------------------------
# Kalış süresine göre yerleştirme (turnover optimizasyonu)
# ---------------------------------------------------------------------------
# Kısa kalanlar çıkışa/AVM kapısına yakın (hızlı giriş-çıkış, az yürüme), uzun
# kalanlar ortaya (kapı yakınını kısa kalanlara bırak) yerleştirilir. Süre
# verildiğinde allocator önce UYGUN BÖLGEYİ seçer, o bölge içinde en yakın yere
# yönlendirir (sözlüksel skor: bölge birincil, mesafe ikincil). Uygun bölgede
# boş yer yoksa mesafeye göre en iyi yere düşer.
SHORT_STAY_MAX_HOURS = 2       # <= bu saat: kısa kalış -> "çıkış yakını" tercih
LONG_STAY_MIN_HOURS = 4        # >= bu saat: uzun kalış -> "orta" tercih


# ---------------------------------------------------------------------------
# MQTT (sensör -> broker -> backend)
# ---------------------------------------------------------------------------
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_TOPIC = "otopark/spots"       # Sensör durum güncellemelerinin yayınlandığı topic
MQTT_CLIENT_ID = "otopark-backend"


# ---------------------------------------------------------------------------
# Veritabanı
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), "parking.db")


# ---------------------------------------------------------------------------
# LLM sağlayıcısı
# ---------------------------------------------------------------------------
# "gemini" | "anthropic" | "openai" | "ollama"
# Varsayılan: gemini (Google) — ücretsiz katman + function calling desteği.
# Yerel/ücretsiz çalışmak için "ollama" yap ve modeli indir.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")

# Sağlayıcıya göre model adı
LLM_MODEL = os.getenv("LLM_MODEL", {
    "gemini": "gemini-2.5-flash",
    "anthropic": "claude-opus-4-8",
    "openai": "gpt-4o",
    "ollama": "llama3.1",
}.get(LLM_PROVIDER, "gemini-2.5-flash"))

# API anahtarları .env'den gelir (koda gömme!)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")


# ---------------------------------------------------------------------------
# Pygame arayüzü
# ---------------------------------------------------------------------------
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 820
FPS = 60

# Renk paleti (R, G, B) — modern koyu "slate" tema.
# İlke: zemin nötr kalır, renk yalnızca ANLAM taşır (önerilen yer, araç, kapılar).
# Böylece 240 yer kalabalık değil, sakin ve okunur görünür.
COLOR_BG = (18, 20, 27)            # pencere arka planı (derin slate)
COLOR_PANEL = (27, 30, 40)         # sağ panel arka planı
COLOR_CARD = (37, 41, 53)          # panel içi kartlar / sohbet balonu
COLOR_LOT_BG = (33, 37, 47)        # otopark zemini (park adaları / refüj)
COLOR_ASPHALT = (23, 25, 32)       # araç yolları (koyu, sakin asfalt)
COLOR_LANE = (104, 112, 130)       # yol orta şeridi (nötr gri, ince — sarı değil)
COLOR_SLOT = (51, 56, 68)          # boş park yuvası zemini
COLOR_PAINT = (92, 100, 116)       # park şerit çizgileri (yumuşak beyaz)
COLOR_ACCENT = (74, 162, 222)      # tek vurgu rengi (mavi-teal)
COLOR_ACCENT_DIM = (46, 86, 120)   # vurgunun sönük tonu (sohbet balonu vb.)
COLOR_EMPTY = (70, 190, 110)       # (lejant) boş normal yer
COLOR_OCCUPIED = (172, 78, 82)     # (lejant) dolu -> mat kırmızı
COLOR_SUGGESTED = (245, 200, 70)   # önerilen yer -> amber (tek yer olduğu için öne çıkar)
COLOR_DISABLED = (74, 134, 206)    # engelli yer -> mavi
COLOR_EV = (78, 182, 150)          # elektrikli yer -> teal-yeşil
COLOR_ENTRANCE = (88, 190, 122)    # giriş işareti
COLOR_EXIT = (226, 160, 72)        # çıkış (AVM kapısı) işareti
COLOR_CAR = (245, 205, 80)         # yönlendirilen (asıl) araç -> amber
COLOR_TEXT = (228, 232, 240)
COLOR_TEXT_DIM = (138, 146, 164)
COLOR_PATH = (245, 200, 70)        # önerilen rota çizgisi (amber)

# Park etmiş araçlar için MAT/desatüre gövde renkleri (lot sakin okunsun diye
# bilinçli olarak düşük doygunluk; renk dikkati önerilen yerden çalmasın).
CAR_COLORS = [
    (120, 128, 142), (98, 110, 128), (132, 98, 102), (92, 114, 132),
    (146, 150, 160), (106, 112, 124), (114, 102, 124), (98, 126, 118),
    (140, 122, 98), (110, 122, 138),
]

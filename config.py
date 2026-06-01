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
ROAD_GAP = 1.5                 # bloklar arası / kenar dikey yol genişliği (mantıksal birim)

N_BANDS = N_AISLES - 1                       # park bandı sayısı (her biri 2 sıra)
NUM_SPOTS = N_BANDS * 2 * SPOTS_PER_ROW      # toplam park yeri = 5*2*24 = 240

# Özel yer sayıları (en üst bandın üst sırasında kümeli; AVM kapısına yakın)
NUM_DISABLED_SPOTS = 6         # Engelli park yeri
NUM_EV_SPOTS = 10              # Elektrikli şarjlı park yeri


# Başlangıç doluluk oranı (DB tohumu ve simülatör başlangıç durumu için)
INITIAL_OCCUPANCY_RATE = 0.55

# Simülatör davranışı
SIM_INTERVAL_SEC = 3.0         # Her tur arası bekleme (saniye)
SIM_CHANGES_PER_TICK = 2       # Her turda kaç park yerinin durumu değişsin


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

# Renk paleti (R, G, B)
COLOR_BG = (24, 26, 32)            # pencere arka planı
COLOR_PANEL = (38, 41, 51)         # sohbet paneli arka planı
COLOR_LOT_BG = (58, 64, 73)        # otopark zemini (park adaları / refüj)
COLOR_ASPHALT = (33, 35, 41)       # araç yolları (koyu asfalt, belirgin)
COLOR_LANE = (228, 196, 78)        # yol orta şerit çizgisi (sarı kesikli)
COLOR_SLOT = (72, 79, 90)          # boş park yuvası zemini (zeminden açık)
COLOR_PAINT = (216, 220, 228)      # beyaz park şerit çizgileri
COLOR_EMPTY = (70, 200, 100)       # boş normal yer vurgusu -> yeşil
COLOR_OCCUPIED = (200, 65, 65)     # (lejant) dolu -> kırmızı
COLOR_SUGGESTED = (250, 225, 55)   # önerilen yer -> sarı (yanıp söner)
COLOR_DISABLED = (60, 130, 230)    # engelli yer -> mavi
COLOR_EV = (95, 200, 150)          # elektrikli yer -> yeşil-turkuaz
COLOR_ENTRANCE = (90, 205, 120)    # giriş işareti
COLOR_EXIT = (240, 175, 60)        # çıkış (AVM kapısı) işareti
COLOR_CAR = (250, 215, 60)         # yönlendirilen (asıl) araç -> sarı
COLOR_TEXT = (235, 235, 235)
COLOR_TEXT_DIM = (158, 164, 180)
COLOR_PATH = (250, 225, 55)        # önerilen rota çizgisi

# Park etmiş araçlar için çeşitli gövde renkleri (gerçekçi görünüm)
CAR_COLORS = [
    (180, 190, 200), (90, 110, 140), (150, 60, 60), (60, 90, 130),
    (200, 200, 205), (70, 80, 90), (120, 70, 100), (80, 120, 110),
    (160, 120, 70), (110, 130, 150),
]

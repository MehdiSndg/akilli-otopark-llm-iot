# CLAUDE.md — LLM-IoT Entegrasyonu: Algoritma Destekli Akıllı Otopark Yönlendirme Sistemi

Bu dosya, Claude Code'un bu projede nasıl çalışacağını yöneten ana yönerge dosyasıdır.
Her oturumda önce bu dosyayı oku, hangi görevde kaldığımızı `## İlerleme Durumu`
bölümünden kontrol et ve sıradaki göreve devam et.

---

## 1. Proje Özeti

Yapay Zeka ve Veri Mühendisliği bölümünde okuyan 2 öğrencinin "Nesnelerin Yapay
Zekası (IoT)" dersi için yaptığı dönem projesi.

Akıllı bir otopark yönlendirme sistemi geliştiriyoruz. Sürücü doğal dille konuşur
(örn. "elektrikli arabam var, çıkışa yakın bir yer istiyorum"). Bir LLM bu isteği
anlar, **function calling** ile yönlendirme algoritmasını çağırır, algoritma graf
üzerinde en uygun boş park yerini bulur ve sonuç sürücüye hem doğal dille açıklanır
hem de bir Pygame penceresinde görsel olarak gösterilir.

**Teslim:** Çalışan prototip + sunum. Tamamen yazılım (gerçek donanım yok, sensörler
simüle edilir).

### Projenin üç katmanı
- **IoT katmanı:** Park yeri doluluk sensörlerinin simülasyonu + MQTT ile veri yayını.
- **Algoritma katmanı:** Graf üzerinde A* ile en uygun yerin bulunması, araç tipine
  ve sürücü tercihine göre filtreleme, çoklu araç için atama.
- **LLM katmanı:** Doğal dil isteğini function calling ile yapılandırılmış parametreye
  çevirme ve sonucu doğal dille açıklama.

### Demoda gösterilecek senaryo
Bir araç otopark girişine gelir → sürücü doğal dille tercihini yazar → sistem en uygun
yeri bulur → Pygame penceresinde otopark ızgarası, dolu/boş yerler, önerilen yerin
vurgulanması ve aracın o yere ilerlemesi animasyonla gösterilir.

---

## 2. Mimari

```
┌──────────────────────┐     MQTT      ┌─────────────────────────┐
│  Sensör Simülatörü   │ ────────────► │        Backend          │
│  (park yeri durumu)  │   (paho-mqtt) │  - MQTT abonesi         │
└──────────────────────┘               │  - SQLite (doluluk)     │
                                        │  - Algoritma modülü     │
┌──────────────────────┐               │  - LLM modülü           │
│   Pygame Arayüzü     │ ◄───────────► │  (FastAPI opsiyonel)    │
│  - otopark ızgarası  │   fonksiyon   └─────────────────────────┘
│  - sürücü giriş kutusu│   çağrısı /
│  - sohbet/cevap alanı │   REST
└──────────────────────┘
```

Tamamen tek makinede çalışır. MQTT broker olarak yerel **Mosquitto** kullanılır
(IoT dersinin özü olan sensör→broker→tüketici mimarisini göstermek için MQTT
korunur, fonksiyon çağrısıyla atlanmaz).

Backend ile Pygame aynı süreçte de çalışabilir; başlangıçta sade tutmak için backend
mantığını doğrudan modül olarak import etmek yeterli, FastAPI'yi yalnızca zaman kalırsa
bir REST katmanı olarak ekle (opsiyonel, bonus).

---

## 3. Teknoloji Yığını

- **Dil:** Python 3.11+
- **MQTT:** paho-mqtt (istemci) + Mosquitto (yerel broker)
- **Veritabanı:** SQLite (standart kütüphane `sqlite3`)
- **Algoritma:** saf Python (graf + A*); `networkx` yardımcı olabilir ama A*'yı
  öğretici olması için elle de yazabiliriz
- **LLM:** Function calling destekleyen bir sağlayıcı.
  - Birincil seçenek: yerel **Ollama** (Llama 3.1 veya Mistral) — ücretsiz, internet
    gerektirmez, gizlilik dostu, function calling destekler.
  - Alternatif: OpenAI veya Anthropic API (API anahtarı `.env` dosyasında).
  - Hangisi kullanılırsa kullanılsın, LLM çağrısı `llm/` altında tek bir arayüzün
    arkasına soyutlanır; sağlayıcı değişse de geri kalan kod değişmez.
- **Arayüz:** Pygame
- **Test:** pytest
- **Ortam:** `python -m venv venv` ile sanal ortam, bağımlılıklar `requirements.txt`

---

## 4. Klasör Yapısı (hedef)

```
otopark/
├── CLAUDE.md                 # bu dosya
├── README.md                 # kurulum + çalıştırma talimatları
├── requirements.txt
├── .env.example              # API anahtarı vb. için örnek
├── config.py                 # tüm ayarlar (yer sayısı, MQTT host, model adı...)
│
├── simulator/
│   └── sensor_simulator.py   # park yeri durumlarını üretir, MQTT'ye yayınlar
│
├── backend/
│   ├── mqtt_client.py        # MQTT abonesi, gelen veriyi DB'ye yazar
│   ├── database.py           # SQLite şeması ve sorguları
│   └── parking_state.py      # anlık doluluk durumunu sunan katman
│
├── algorithm/
│   ├── graph.py              # otopark grafı (düğümler, kenarlar, mesafeler)
│   ├── astar.py              # A* en kısa yol
│   └── allocator.py          # tercihe göre filtre + en uygun yer seçimi + çoklu atama
│
├── llm/
│   ├── tools.py              # function calling araç tanımları (JSON şema)
│   ├── client.py             # LLM sağlayıcı soyutlaması (ollama/openai/anthropic)
│   └── orchestrator.py       # doğal dil → araç çağrısı → doğal dil cevap
│
├── ui/
│   ├── pygame_app.py         # ana pencere, döngü, çizim
│   ├── widgets.py            # metin giriş kutusu, buton, sohbet alanı
│   └── layout.py             # ızgara yerleşimi, renkler, koordinatlar
│
├── tests/
│   ├── test_astar.py
│   ├── test_allocator.py
│   └── test_orchestrator.py
│
└── main.py                   # her şeyi başlatan giriş noktası
```

---

## 5. Veri Modeli

### Park yeri (ParkingSpot)
- `id`: benzersiz kimlik (örn. "A-12")
- `node_id`: graf üzerindeki düğüm numarası
- `type`: `"normal" | "disabled" | "ev_charging"` (normal / engelli / elektrikli şarjlı)
- `occupied`: boolean
- `x`, `y`: Pygame'de çizim için ekran koordinatları
- `zone`: bölge etiketi (örn. "giriş yakını", "çıkış yakını")

### Graf
- Düğümler: giriş kapısı (başlangıç), koridor kavşakları, park yerleri (hedefler)
- Kenarlar: düğümler arası yürüme/sürüş mesafesi (ağırlık)
- A* sezgisel fonksiyonu: düğümler arası Öklid (düz çizgi) mesafesi

### Sürücü isteği (function calling parametreleri)
- `vehicle_type`: `"normal" | "disabled" | "ev"`
- `preference`: `"nearest_entrance" | "nearest_exit" | "any"` (girişe/çıkışa yakın / farketmez)
- `needs_charging`: boolean

---

## 6. LLM Function Calling Tasarımı

LLM'e tanımlanacak ana araç:

```
find_best_parking_spot(
    vehicle_type: str,      # "normal" | "disabled" | "ev"
    preference: str,        # "nearest_entrance" | "nearest_exit" | "any"
    needs_charging: bool
) -> { spot_id, path, distance, walk_to_exit }
```

Akış (`llm/orchestrator.py`):
1. Sürücünün serbest metni LLM'e gönderilir, araç tanımlarıyla birlikte.
2. LLM doğru parametreleri çıkarıp `find_best_parking_spot` aracını çağırır.
3. Bu çağrı bizim `algorithm/allocator.py` fonksiyonumuzu tetikler; sonuç (yer + yol)
   araç sonucu olarak LLM'e geri verilir.
4. LLM sonucu doğal dille özetler (örn. "Sizi B-12 numaralı şarjlı yere yönlendirdim,
   çıkışa yaklaşık 30 metre.").
5. Hem yapılandırılmış sonuç (Pygame'in çizmesi için) hem doğal dil cevabı döndürülür.

**Önemli:** LLM yalnızca anlama + açıklama yapar; kararı (en uygun yer) deterministik
algoritma verir. Sunumda "LLM'i süs değil, fonksiyonel bir bileşen olarak kullandık,
karar algoritmaya ait" vurgusu yapılacak.

---

## 7. İş Bölümü (2 kişi)

Katmanlara göre bölünür; entegrasyon birlikte yapılır.

- **Kişi A — IoT & Veri:** `simulator/`, `backend/` (MQTT, SQLite, doluluk durumu).
- **Kişi B — Zeka & Arayüz:** `algorithm/`, `llm/`, `ui/`.
- **Birlikte:** `main.py` entegrasyonu, testler, sunum, demo provası.

Her ikisi de tüm katmanları anlamalı (sunumda sorular ikisine de gelir). Kod ortak bir
Git deposunda tutulur, sık commit edilir.

---

## 8. Adım Adım Görevler

Görevleri sırayla yap. Her görevi bitirince `## İlerleme Durumu` bölümünde işaretle,
küçük bir commit at ve sıradakine geç. Bir görev büyükse alt adımlarını ayrı ayrı
tamamla.

### Faz 0 — Kurulum
- [x] **G0.1** Sanal ortam oluştur, `requirements.txt` yaz (pygame, paho-mqtt, pytest;
      LLM sağlayıcısına göre ollama/openai/anthropic), kur.
- [x] **G0.2** Klasör yapısını (Bölüm 4) iskelet olarak oluştur, her modüle boş/temel
      dosya koy.
- [x] **G0.3** `config.py` yaz: park yeri sayısı, tip dağılımı, MQTT host/port/topic,
      LLM model adı/sağlayıcı, Pygame pencere boyutu gibi tüm sabitler burada.
- [x] **G0.4** `.env.example` ve `README.md` taslağı (kurulum + çalıştırma adımları).
- [x] **G0.5** Yerel Mosquitto broker'ın kurulu olduğunu doğrula (talimatı README'ye yaz).

### Faz 1 — IoT katmanı (Kişi A)
- [x] **G1.1** `backend/database.py`: SQLite şeması (park yerleri tablosu), tabloyu
      başlangıç verisiyle dolduran fonksiyon, güncelleme/sorgu fonksiyonları.
- [x] **G1.2** `simulator/sensor_simulator.py`: N park yerinin durumunu üreten döngü.
      Başlangıçta rastgele doluluk; sonra zaman senaryosu (sabah dolar, akşam boşalır).
      Her durum değişikliğini MQTT topic'ine JSON olarak yayınla.
- [x] **G1.3** `backend/mqtt_client.py`: topic'e abone ol, gelen mesajı parse et,
      `database.py` üzerinden DB'yi güncelle.
- [x] **G1.4** `backend/parking_state.py`: o anki tüm doluluk durumunu (liste/dict)
      döndüren sade bir okuma katmanı. Algoritma ve UI bunu kullanacak.
- [x] **G1.5** Manuel test: simülatörü ve mqtt_client'ı ayrı terminalde çalıştır,
      DB'nin güncellendiğini doğrula. Sonucu README'ye not düş.

### Faz 2 — Algoritma katmanı (Kişi B)
- [x] **G2.1** `algorithm/graph.py`: otoparkı graf olarak kur. Düğümler: giriş, çıkış,
      koridor kavşakları, park yerleri. Kenar ağırlıkları = mesafe. Park yeri
      ekran koordinatları graf düğümleriyle eşleşsin (UI ile tutarlı).
- [x] **G2.2** `algorithm/astar.py`: A* algoritması (saf Python). Başlangıç düğümünden
      hedef düğüme en kısa yolu ve toplam mesafeyi döndür. Sezgisel: Öklid mesafesi.
- [x] **G2.3** `algorithm/allocator.py`: `find_best_parking_spot(vehicle_type,
      preference, needs_charging)` fonksiyonu. Adımlar: (a) parking_state'ten boş
      yerleri al, (b) araç tipi/şarj ihtiyacına göre filtrele, (c) tercihe göre
      başlangıç/hedef düğümünü belirle, (d) her aday için A* mesafesini hesapla,
      (e) en küçük mesafeli yeri seç. Sonuç: spot_id, yol (düğüm listesi), mesafe.
- [x] **G2.4** Çoklu araç dengeli atama: Hungarian (Kuhn-Munkres) ile optimal atama —
      aynı anda gelen birden çok araç çakışmadan en uygun yerlere dağıtılır.
- [x] **G2.5** `tests/test_astar.py` ve `tests/test_allocator.py`: bilinen küçük bir
      grafta beklenen sonuçları doğrula.

### Faz 3 — LLM katmanı (Kişi B)
- [x] **G3.1** `llm/tools.py`: `find_best_parking_spot` için function calling JSON
      şemasını tanımla (parametreler, açıklamalar, enum değerleri).
- [x] **G3.2** `llm/client.py`: sağlayıcı soyutlaması. `chat(messages, tools)` arayüzü;
      altında Ollama (varsayılan) veya OpenAI/Anthropic. Sağlayıcı `config.py`'den seçilir.
- [x] **G3.3** `llm/orchestrator.py`: serbest metni al → LLM'e araçlarla gönder →
      LLM araç çağrısı yaparsa `allocator.find_best_parking_spot`'u çalıştır → sonucu
      LLM'e geri ver → doğal dil cevabı al. Hem yapılandırılmış sonucu hem metni döndür.
- [x] **G3.4** Hata yönetimi: LLM yanlış/eksik parametre verirse makul varsayılanlara
      düş; uygun boş yer yoksa kullanıcıya nazikçe açıkla.
- [x] **G3.5** `tests/test_orchestrator.py`: birkaç örnek cümle ("engelli yerim
      lazım", "şarjlı yer çıkışa yakın olsun") doğru parametrelere çözülüyor mu?
      (LLM çağrısı mock'lanabilir.)

### Faz 4 — Pygame arayüzü (Kişi B)
- [x] **G4.1** `ui/layout.py`: otopark ızgarasının ekran yerleşimi, renk paleti
      (boş=yeşil, dolu=kırmızı, önerilen=sarı/yanıp sönen, engelli/ev için ikon/renk),
      koordinat hesapları.
- [x] **G4.2** `ui/widgets.py`: metin giriş kutusu (klavye girişi), gönder butonu,
      sohbet/cevap gösterim alanı. (Pygame'de hazır input yok, elle yaz.)
- [x] **G4.3** `ui/pygame_app.py`: ana döngü. Sol/üst tarafta otopark ızgarası
      (parking_state'ten canlı), alt/sağda sohbet kutusu. Sürücü yazıp gönderince
      orchestrator çağrılır, dönen yer ızgarada vurgulanır.
- [x] **G4.4** Animasyon: önerilen yere giden yol (A* sonucu düğüm listesi) üzerinde
      bir araç ikonunu adım adım hareket ettir.
- [x] **G4.5** Canlı güncelleme: simülatör doluluk değiştirdikçe ızgara renkleri
      güncellensin (DB'yi periyodik oku ya da olay tetikle).

### Faz 5 — Entegrasyon (Birlikte)
- [x] **G5.1** `main.py`: simülatörü (ayrı thread/process), MQTT abonesini ve Pygame
      uygulamasını tek komutla başlat. Kapanışta temiz sonlandır.
- [x] **G5.2** Uçtan uca akışı doğrula: araç gelir → metin → LLM → algoritma → görsel
      yönlendirme. En az 3 farklı senaryo (normal/engelli/elektrikli).
- [x] **G5.3** Hata ve uç durumlar: otopark dolu, geçersiz girdi, LLM/broker erişilemez.
- [ ] **G5.4** README'yi tamamla: mimari şeması, kurulum, çalıştırma, ekran görüntüleri.

### Faz 6 — Sunum & teslim (Birlikte)
- [ ] **G6.1** Sunum içeriği: problem, mimari, IoT/algoritma/LLM katmanlarının rolü,
      "LLM karar vermez, anlar+açıklar; karar algoritmanın" vurgusu, demo, sonuç.
- [ ] **G6.2** Demo provası: 3 senaryoyu sorunsuz gösterecek hazır metinler.
- [ ] **G6.3** Olası soru-cevap hazırlığı (neden A*, neden MQTT, LLM'in sınırları,
      gizlilik, ölçeklenebilirlik).
- [ ] **G6.4** Kod temizliği, yorumlar, son commit, teslim.

---

## 9. Çalıştırma Komutları (doldurulacak)

> Bu bölümü kurulum ilerledikçe gerçek komutlarla güncelle.

```bash
# Sanal ortam
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Mosquitto broker (yerel)
# (kurulum talimatı README'de)

# Tüm sistemi başlat
python main.py

# Testler
pytest
```

---

## 10. Çalışma Kuralları (Claude Code için)

- Her oturum başında bu dosyayı ve `## İlerleme Durumu`'nu oku, kaldığın görevden devam et.
- Bir seferde tek görevi (veya bir görevin alt adımını) tamamla; bitince ilerlemeyi işaretle.
- Yeni dosya açmadan önce ilgili modülün Bölüm 4'teki yerine koy.
- Kodu sade ve yorumlu tut; bunlar öğrenci projesi, okunabilirlik önemli.
- Türkçe değişken/yorum karışımından kaçın: kod İngilizce, açıklayıcı yorumlar Türkçe olabilir.
- LLM sağlayıcısı değişebilir; LLM çağrılarını her zaman `llm/client.py` arkasında tut.
- Sır/anahtarları koda gömme; `.env` kullan, `.env`'i `.gitignore`'a ekle.
- Büyük bir mimari değişiklik gerekiyorsa önce bu dosyadaki ilgili bölümü güncelle.
- Karar verilmesi gereken belirsizlik varsa varsayılan seç, ama yorumda not düş.

---

## 11. İlerleme Durumu

> Tamamlanan görevleri buradan takip et. Format: `[x] G0.1 — kısa not / tarih`

**Faz 0 — Kurulum (tamamlandı, G0.5 hariç)**
- [x] G0.1 — venv + requirements.txt yazıldı, bağımlılıklar kuruldu (2026-06-01).
- [x] G0.2 — Klasör iskeleti + tüm modüllere temel dosyalar kondu (2026-06-01).
- [x] G0.3 — config.py yazıldı (yer sayısı, MQTT, LLM, Pygame ayarları) (2026-06-01).
- [x] G0.4 — .env.example + README taslağı (kurulum/çalıştırma) yazıldı (2026-06-01).
- [x] G0.5 — Mosquitto 2.1.2 winget ile kuruldu, servis çalışıyor (Automatic).
      paho-mqtt ile pub/sub round-trip testi başarılı (2026-06-01).

**Faz 0 tamamen bitti.**

**Faz 1 — IoT katmanı (tamamlandı)**
- [x] G1.1 — backend/database.py: SQLite şeması (spots), yerleşimden tohumlama,
      sorgu/güncelleme fonksiyonları. WAL modu (eşzamanlı okuma/yazma) (2026-06-01).
- [x] G1.2 — simulator/sensor_simulator.py: rastgele doluluk + her değişikliği
      MQTT'ye JSON yayınlar; başlangıç snapshot'ı; stop_event ile temiz durur (2026-06-01).
- [x] G1.3 — backend/mqtt_client.py: topic'e abone, JSON parse, DB güncelle (2026-06-01).
- [x] G1.4 — backend/parking_state.py: get_state / get_empty_spots / summary okuma katmanı (2026-06-01).
- [x] G1.5 — Uçtan uca test geçti: sensör→MQTT→abone→DB akışı doğrulandı (2026-06-01).

**Faz 2 — Algoritma katmanı (tamamlandı)**
- [x] G2.1 — algorithm/graph.py: **gerçekçi AVM düzeni** — çift sıralı park bantları
      (double-loaded aisle) + yatay araç yolları + dikey bağlantı yolları (cross-lane)
      = ızgara yol ağı. Giriş sol-alt, yaya çıkışı/AVM kapısı üst-orta. ParkingSpot +
      Graph (Öklid ağırlıklı). **240 yer**, 386 düğüm (2026-06-01, kapasite revize edildi).
- [x] G2.2 — algorithm/astar.py: saf Python A*, Öklid sezgisel (2026-06-01).
- [x] G2.3 — algorithm/allocator.py: find_best_parking_spot — filtre + A* mesafe +
      tercih (girişe/çıkışa yakın) ile en uygun yeri seçer (2026-06-01).
- [x] G2.4 — algorithm/hungarian.py: saf Python Hungarian (Kuhn-Munkres, O(n^3),
      dikdörtgen destekli) + allocator.allocate_multiple: aynı anda gelen birden
      çok aracı OPTIMAL atar (iki araç asla aynı yere gitmez; toplam mesafeyi en
      küçük yapar). Giriş/çıkış A* mesafeleri önbelleğe alınır (5 araç × 240 yer
      ~247 ms). tests/test_hungarian.py (4) + tests/test_multi_allocator.py (7)
      (2026-06-02).
- [x] G2.5 — tests/test_astar.py (3) + tests/test_allocator.py (5): 9 test geçti (2026-06-01).

**Faz 3 — LLM katmanı (tamamlandı)**
- [x] G3.1 — llm/tools.py: nötr function calling şeması (enum, açıklama) +
      SYSTEM_PROMPT + DEFAULTS (2026-06-01).
- [x] G3.2 — llm/client.py: LLMClient soyutlaması; GeminiClient tam implemente
      (google-genai), geçici 503'lere retry. Diğer sağlayıcılar için genişletme
      noktası hazır (2026-06-01).
- [x] G3.3 — llm/orchestrator.py: handle_request — metin→çıkarım→allocator→açıklama;
      yapılandırılmış sonuç + doğal dil cevabı döndürür (2026-06-01).
- [x] G3.4 — Hata yönetimi: eksik param→varsayılan; LLM erişilemezse keyword yedeği;
      açıklama alınamazsa şablon cevap; uygun yer yoksa nazik mesaj (2026-06-01).
- [x] G3.5 — tests/test_orchestrator.py (6 test, LLM mock'lu): 14 test toplam geçti (2026-06-01).

**Faz 4 — Pygame arayüzü (kod tamamlandı; görsel doğrulama kullanıcıda)**
- [x] G4.1 — ui/layout.py: panel yerleşimi (sol otopark / sağ sohbet), Transform
      (mantıksal→ekran koordinat, oranı koruyarak sığdırma), spot_color renk kuralı (2026-06-01).
- [x] G4.2 — ui/widgets.py: InputBox (Türkçe klavye girişi + imleç), Button,
      ChatLog (word-wrap, kaydırma) (2026-06-01).
- [x] G4.3 — ui/pygame_app.py: ana döngü; yatay+dikey yollar, 240 yer canlı renkli,
      sohbet paneli. Sürücü gönderince orchestrator **ayrı thread'de** çağrılır
      (UI donmaz, "Düşünüyor..." gösterilir) (2026-06-01).
- [x] G4.4 — CarAnimation: A* yolu (düğüm listesi) ekran noktalarına çevrilip araç
      ikonu sabit hızla hedefe ilerler; önerilen yer sarı yanıp söner + rota çizgisi (2026-06-01).
- [x] G4.5 — Canlı güncelleme: parking_state'ten her ~0.5 sn doluluk okunup ızgara
      renkleri tazelenir (simülatör+abone thread'leri pygame_app içinde başlar) (2026-06-01).
- NOT: GUI görsel olarak başsız (SDL dummy) test edildi — çökme yok, animasyon
  hedefe ulaşıyor, çizim fonksiyonları sorunsuz. Gerçek pencereyi kullanıcı
  `python -m ui.pygame_app` ile açıp görecek.
- **Görsel revizyon (kullanıcı geri bildirimi):** İlk sürüm "renkli kareler" gibi
  görünüyordu ve araç hareketi yoktu. Baştan yazıldı (ui/sprites.py eklendi):
  gerçekçi park cepleri (beyaz şerit), dolu yerlerde üstten görünüm araç sprite'ları
  (çeşitli renkler), EV=şimşek / engelli=tekerlekli sandalye ikonları, asfalt yollar
  + sarı kesikli şeritler, **yollarda dolaşan ambient trafik (12 araç)**, yönüne
  dönerek süren yönlendirme aracı. SDL dummy ile PNG render alınıp görsel doğrulandı.
- **Görsel revizyon v2 (kullanıcı geri bildirimi):** (1) Düzen **bloklu** yapıldı —
  park yerleri 4 bloka ayrıldı, dikey yollar blok aralarındaki boşluklarda (artık yer
  yolun üstünde değil). (2) **Çoklu giriş/çıkış**: 2 giriş (alt köşeler) + 2 çıkış
  (üst köşeler); allocator en yakın giriş/çıkışa göre hesaplıyor. (3) Ambient araçlar
  **sürekli** (bittiği yerden devam, ışınlanma yok) ve bazen kapılara gidiyor (giren/
  çıkan trafik). (4) Şerit ofseti (sağdan sürüş) ile karşı yönlü araçlar ayrıldı.
  (5) Araç sprite'ı iyileştirildi (tekerlek/kabin/cam/stop lambası). graph node
  adları ENTRANCE/EXIT -> ENTRANCES/EXITS listesi; graph.geom UI'a yol geometrisi verir.
- **Bayat DB düzeltmesi:** Düzen değişince eski parking.db koordinatları bayatlıyordu
  (her şey sola yığılıyordu). database.init_db artık **düzen imzası** tutuyor; imza
  değişince tabloyu otomatik yeniden tohumluyor.
- **Revizyon v3 (kullanıcı geri bildirimi, 4 madde):**
  (1) Hareket eden ambient araçlar tamamen kaldırıldı (sakin/profesyonel görünüm).
  (2) **Canlı sayılar:** Mosquitto winget ile kuruldu; ayrıca simulator'a **brokersız
  yedek** eklendi (broker yoksa doluluk doğrudan database.set_occupied ile yazılır),
  böylece boş/dolu sayıları her durumda canlı değişir.
  (3) **Giriş seçici:** Kapı seçimi artık makineye bırakılmıyor — sürücü UI'daki
  widgets.Segmented ile **Sol/Sağ giriş** seçer; orchestrator.handle_request(entrance=)
  → allocator yalnızca o girişten A* mesafesi hesaplar.
  (4) **Kalış süresi skoru:** tools.py'ye duration_hours (integer) eklendi; client.py
  integer/number şema eşlemesi; orchestrator hem LLM hem keyword/regex ("2 saat",
  "bütün gün") ile süreyi çıkarır; allocator sözlüksel skor (bölge birincil, mesafe
  ikincil) ile kısa kalış→"çıkış yakını", uzun kalış→"orta" bölgeye yönlendirir
  (config.SHORT_STAY_MAX_HOURS / LONG_STAY_MIN_HOURS). Testler 14→**23**'e çıktı.
- **Sağlamlık düzeltmeleri (kullanıcı hata bildirimi):** (a) Gemini ücretsiz katman
  kotası (günde 20 istek) dolunca 429 alınıyordu; client.is_quota_error + orchestrator
  artık 429'u yeniden denemiyor, ikinci (açıklama) çağrısını atlıyor ve cevaba nazik
  "kota doldu, basit mod" notu ekliyor. (b) "çıkışa uzak"/"girişe uzak" gibi UZAK
  ifadeleri yön tersine çevirir (çıkışa uzak = girişe yakın); hem SYSTEM_PROMPT hem
  keyword yedeği bunu uyguluyor.

**Faz 4-WEB — Web arayüzüne geçiş (kullanıcı kararı; pygame görseli yetersiz bulundu)**
Görselleştirme katmanı web'e taşındı; backend (MQTT/SQLite/A*/Gemini) AYNEN korundu.
- [x] web/server.py — FastAPI: statik sayfa + /api/layout + /api/state + WS /ws (canlı
      doluluk) + POST /api/request (orchestrator). Backend thread'leri (simülatör + MQTT
      abonesi) sunucu açılışında (lifespan) başlar.
- [x] web/static (index.html + style.css + app.js) — Canvas tabanlı gerçekçi AVM otopark
      haritası (modern koyu tema).
- [x] graph.py zenginleştirildi: 3 araç girişi + 2 araç çıkışı + 3 AVM yaya kapısı;
      geom (bölümler, AVM binası, kapı yönleri); bant yüksekliği BAND_UNIT=5.5 + spot.face.
- [x] Görsel: AVM binası + yaya kapıları + zebra geçit, geniş yatay/dikey yollar + sarı
      kesikli şerit + yön okları, beyaz şeritli cepler, dolu yerlerde üstten araç,
      bölüm etiketleri (A–E). (Kenar peyzaj adaları kullanıcı isteğiyle kaldırıldı.)
- [x] **Olay tabanlı trafik:** Hareket eden her araç GERÇEK bir doluluk olayına karşılık
      gelir — yer dolunca araç girişten gelip park eder, boşalınca çıkışa gider
      (dekoratif/rastgele trafik yok). Sağ şeritten sürüş.
- [x] **Trafik modeli (hilesiz):** sürekli araç-takibi (öne mesafeye göre yumuşak
      yavaşlama) + kavşak geçiş önceliği (sabit id kuralı); en küçük id daima ilerler →
      kalıcı kilit (deadlock) matematiksel olarak imkânsız. Araçlar 0.70x.
- [x] **Gün-içi doluluk:** sensor_simulator saate göre doluluk eğrisi üretir (gece boş,
      öğle ~%82 + akşam zirve); bir simüle gün ~4 dk (config.DAY_LENGTH_SEC). SIM_STATE
      saat+yoğunluk tutar; UI'da gösterilir.
- NOT: Tarayıcı görselini Claude göremiyor → yerleşim pygame PNG ile, JS `node --check`
      ile, API uçtan uca canlı test edildi. pygame UI (ui/) hâlâ duruyor ama BİRİNCİL
      arayüz artık web. Çalıştırma: `python -m web.server` → http://127.0.0.1:8000

**Revizyon v4 — Maliyet fonksiyonu + entegrasyon (akademik doküman hizalaması)**
Kullanıcı projeyi akademik bir dönem raporu formatına hizaladı. Veritabanı (SQLite)
ve LLM korundu; web + pygame ikisi de tutuldu. Asıl değişiklik karar çekirdeğinde:
- **Maliyet fonksiyonu:** Bölge-tabanlı sözlüksel skor kaldırıldı; yerine dokümandaki
  sürekli formül kondu: **C_i = |d_i − ALPHA·t|** (d_i = girişten A* sürüş mesafesi,
  t = kalış süresi saat, ALPHA = config.ALPHA_DISTANCE_PER_HOUR = 5.0). En küçük C_i'li
  boş yer atanır → kısa kalan kapıya yakın, uzun kalan derine (sirkülasyon). Süre
  yoksa tercihe göre en yakın. allocator sonucu artık `cost` alanı da döndürür.
  (config'ten SHORT_STAY_MAX_HOURS / LONG_STAY_MIN_HOURS çıkarıldı.)
- **main.py (G5.1):** Artık çalışır — `python main.py` web sunucusunu (uvicorn) başlatır;
  `python main.py --pygame` alternatif masaüstü arayüzü açar. Backend thread'leri web
  lifespan'inde otomatik başlar.
- **app.js düzeltmesi:** Bozuk/ölü renk değeri (`mallTop: "#4a melts"`, geçersiz CSS,
  zaten ezilmiş yinelenen anahtar) temizlendi.
- **README (G5.4):** Web mimarisi + maliyet fonksiyonu + çalıştırma komutlarıyla güncellendi.
- Testler **23→25** (maliyet fonksiyonu: kısa→kapıya yakın, orta→orta, uzun→derin + cost alanı).

**Faz 5 — Entegrasyon (tamamlandı)**
- [x] G5.1 — main.py tek komutla başlatma (web varsayılan; --pygame alternatif). Simülatör +
      MQTT abonesi web lifespan'inde otomatik başlar/temiz kapanır.
- [x] G5.2 — Uçtan uca akış API ile doğrulandı: metin→(Gemini ya da keyword yedeği)→allocator
      maliyet fonksiyonu→görsel yönlendirme (normal/engelli/ev, kalış süresi, giriş senaryoları).
- [x] G5.3 — Hata/uç durumlar: broker kapalı→brokersız yedek; Gemini 429/503→keyword
      yedeği + nazik not; uygun yer yok→nazik mesaj.
- [x] G5.4 — README web mimarisi + maliyet fonksiyonuyla güncellendi (ekran görüntüsü kullanıcıda).

**Revizyon v5 — Kapsamlı canlı test + hata düzeltmeleri (tarayıcıda gerçek deneme)**
Web arayüzü Claude Preview ile gerçek tarayıcıda sürüldü (giriş seç + mesaj gönder),
JS konsolu/animasyon/araç durumu incelendi. Bulunan ve düzeltilen hatalar:
- **Trafik kilitlenmesi (KRİTİK):** Olay-araçları (doluluk değişimlerini gösteren)
  zamanla 40 sınırına dayanıp ~%56'sı `speedFactor=0` ile DONUYORDU (haritada kalıcı
  yığın). Sebep: `applyTraffic`'teki "kavşakta sert dur (f=0)" kuralı zincirleme
  deadlock üretiyordu ("en küçük id hep ilerler" garantisi konvoy takibiyle bozuluyordu).
  Çözüm (app.js): (1) sert kavşak durması kaldırıldı, yalnız aynı-yön yumuşak takip
  (min hız faktörü 0.15) kaldı → konvoyun önü hep ilerler, deadlock matematiksel olarak
  imkânsız; (2) her araca güvenlik ömrü (life>16sn → hedefe tamamla); (3) araç sınırı
  40→16. Doğrulandı: yüksek dolulukta bile donmuş araç 0, sayı ~17, ömür ~9sn.
- **Fallback açıklaması yanıltıcıydı:** Kota dolunca (hep fallback) cevap her zaman
  "çıkışa X birim" diyordu; kısa kalış girişe yakın bir yere atanınca bu kafa
  karıştırıcıydı. Artık SÜRE-FARKINDA: kısa→"girişe yakın, hızlı giriş-çıkış",
  uzun→"daha içeride, kapı önlerini kısa süreli araçlara bıraktık"; GİRİŞTEN sürüş
  mesafesini (kararı veren büyüklük) kullanıyor.
- **Dürüst uyumsuzluk notu:** İstenen engelli/şarjlı yer boş değilse cevap artık
  "Şu an boş engelli/şarjlı yer kalmadı, size en uygun … yeri ayarladım" diyor.
- **Kota optimizasyonu (config.LLM_EXPLAIN):** Her istek normalde 2 LLM çağrısı yapar
  (param çıkarımı + açıklama) → Gemini ücretsiz 20/gün ~10 istekte biter. LLM_EXPLAIN=
  false yapılınca tek çağrı + zengin şablon açıklama → kota 2 kat dayanır. Varsayılan
  true (davranış korundu); demoda .env'de false önerilir.
- NOT: Gemini günlük kotası (20/gün) test sırasında tükendi → LLM yolu kodu doğru ama
  bugün çoğu istek keyword yedeğine düşüyor (kota ertesi gün sıfırlanır).

**Faz 7 — IoT/AIoT genişletmeleri (kullanıcı isteğiyle eklendi, ders kapsamı güçlendirme)**
Proje kapsamını "Nesnelerin Yapay Zekası" dersine daha uygun hale getirmek için
IoT sensing/veri/güvenilirlik katmanı derinleştirildi. Hepsi backend API + canlı
test edildi; canvas görselleri kullanıcıda doğrulanacak.
- [x] DB şema v2: sensor_health / events / occupancy_samples tabloları + spots'a
      reserved & last_change; şema sürümü değişince otomatik drop/recreate.
- [x] MQTT zenginleştirme: per-spot topic hiyerarşisi (otopark/spots/<bölüm>/<id>),
      QoS 1, retained, LWT (otopark/gateway/status — süreç çökerse "offline"),
      sensör sağlık telemetrisi (otopark/health/<id>: batarya/sinyal/çevrimiçi).
      Abone wildcard ile dinleyip topic'e göre yönlendirir. Test: per-spot akış,
      240/240 taze telemetri, gateway online/offline doğrulandı.
- [x] Anomali tespiti (backend/anomaly.py): çevrimdışı sensör, takılı sensör
      (çevrimdışı ama "dolu" raporluyor), düşük pil. Tipler ayrık + offline
      sayısıyla sınırlı (panel gürültüye boğulmaz). Simülatörde 5 zayıf sensör
      karışık başlangıç piliyle demo içeriği üretir. API /api/anomalies.
- [x] Rezervasyon: spots.reserved; allocator rezerveyi dışlar; /api/reserve +
      /api/cancel_reservation; sweeper zaman aşımını/park edilen rezervasyonu
      temizler; araç park edince set_occupied rezervasyonu otomatik kaldırır.
- [x] Analitik (backend/analytics.py): doluluk zaman serisi, ortalama kalış süresi
      (olay eşleme, simüle-dakika), bölge doluluk oranları, spot kullanım sıklığı
      (ısı haritası). API /api/analytics.
- [x] Web UI: IoT sistem durumu satırı (ağ geçidi + sensör filosu + anomali rozeti/
      liste, anomalili yerler haritada işaretli), "Yeri ayırt" rezervasyon butonu
      (rezerve yerler turuncu kesikli + R), Canvas analitik kaplama (zaman çizgisi +
      bölge bar), ısı haritası toggle, sesli giriş (Web Speech API tr-TR).

**Faz 8 — Edge AI + tahmin + çok-araçlı LLM + mühendislik olgunluğu (A+B grubu)**
Kullanıcı öneri listesinden A (dersin kalbi) + B (mühendislik olgunluğu) grupları
seçildi. Hepsi pytest (37 geçer) + canlı API ile uçtan uca doğrulandı.
- [x] **Edge filtering (uç zekâ):** simulator/sensor_simulator.py EdgeFilter — sensör
      düğümü ham okumayı yayınlamadan önce yerel debounce uygular. Kısa süreli
      geçişler (pass-by gürültüsü) EDGE_DEBOUNCE_TICKS tur kararlı kalmazsa elenir;
      yalnız "gerçek" park değişimleri merkeze gider. EDGE_STATS sayacı + UI'da
      "🛡 Edge: N gürültü" pill. Canlı: filtered=8/confirmed=36 doğrulandı.
      Sunum teması: bulut zekâsı (LLM) ↔ uç zekâsı (sensör mantığı).
- [x] **Tahminleyici zekâ (predict):** backend/predict.py — occupancy_samples üzerinde
      en küçük kareler eğilimi + occupancy_target gün-içi örüntüsü harmanı ile kısa
      vadeli doluluk tahmini. /api/predict + UI "🔮 Tahmin" butonu + LLM aracı.
      "15 dk sonra ~%X dolu, ~N boş" öngörücü yönlendirme.
- [x] **LLM çok-araçlılık (konuşan asistan):** tools.py 3 araç (find_best_parking_spot
      + get_parking_stats + predict_availability); client.py çok-fonksiyon Gemini Tool;
      orchestrator niyet-dispatch (LLM tool seçer; yoksa keyword niyet sapması). Çok
      dilli (TR/EN). Canlı: gerçek Gemini "kaç boş yer" → stats, "dolar mı" → predict,
      "elektrikli" → find seçti (source=llm).
- [x] **Karar/oturum log tablosu:** DB şema v3 assignments tablosu (ts, spot, araç,
      tercih, süre, mesafe, maliyet, kaynak, başarı). orchestrator her gerçek atamayı
      loglar (testte spots enjekte edilince atlanır). /api/assignments. Tahmin için
      geçmiş veri + denetim izi.
- [x] **Pydantic doğrulama:** backend/schemas.py — MQTT sensör mesajları (SpotMessage/
      HealthMessage/GatewayMessage, KATI: bozuk veri reddedilir) + LLM parametreleri
      (ParkingParams, YUMUŞAK: geçersiz→varsayılan). mqtt_client ValidationError ile
      şema dışı mesajı reddeder. Canlı: kötü batarya/status reddi doğrulandı.
- [x] **Loglama:** backend/log.py merkezi seviyeli logging (INFO/WARNING/ERROR),
      LOG_LEVEL/LOG_FILE .env. print'ler simulator/mqtt_client/orchestrator/server/
      main'de logger'a çevrildi.
- [x] **Eşzamanlılık + reconnect:** server.py _RES_LOCK (threading.Lock) ile paylaşılan
      rezervasyon sözlüğü race'e karşı korundu; mqtt_client reconnect_delay_set +
      on_disconnect + ilk bağlantı retry döngüsü (graceful degradation); simülatör
      client'ına da reconnect_delay_set.

**Revizyon v6 — Kapı anlamı (AVM↔otopark çıkışı) + EV uyumsuzluk + LLM açıklama (kullanıcı hata bildirimi)**
Kullanıcı tarayıcıda 2 hata bildirdi; tüm sistem web'de yeniden test edildi.
- **Bug: "çıkışa yakın" yanlış kapıyı hedefliyordu.** allocator'da `nearest_exit`
  AVM yaya kapısına (EXITS=MALL) göre hesaplanıyordu; oysa UI'da turuncu "ÇIKIŞ"
  araç çıkışıdır (VEHICLE_EXITS=VEXIT). Düzeltildi: `nearest_exit` artık en yakın
  ARAÇ ÇIKIŞINA (VEXIT) sürüş mesafesini minimize ediyor. Sonuç alanlarına
  `dist_to_exit` (araç çıkışına) ve `walk_to_mall` (AVM kapısına yürüme) eklendi;
  `walk_to_exit` geriye dönük = AVM yürümesi (DB sütunu korundu).
- **Bug: EV isteyince normal yer veriyordu (sessizce).** Boş şarjlı/engelli yer
  yoksa cevap artık LLM modunda da DAİMA "Şu an boş şarjlı/engelli yer kalmadı,
  size en uygun … yeri ayarladım" notuyla başlıyor (_type_mismatch_note _handle_find'de).
- **LLM açıklaması kapıları karıştırıp yanlış mesafe uyduruyordu** (girişe yakın yeri
  "AVM kapısına yakın" diye anlatıyordu). _build_explain_prompt tercihe göre TEK doğru
  "manşet mesafe" verip uydurmayı yasaklayacak şekilde sıkılaştırıldı; artık doğru.
- Fallback/şablon açıklama da kapı-ayrımlı: girişe→giriş kapısı, çıkışa→araç çıkışı,
  varsayılan→giriş + AVM yürümesi ayrı belirtiliyor.
- Tüm web özellikleri tarayıcıda test edildi (çalışıyor): çoklu araç (Hungarian),
  tahmin, analitik paneli, ısı haritası, anomali rozeti+harita işareti, canlı sayılar.
- Testler **37→38** (EV uyumsuzluk notu regresyonu; nearest_exit=VEXIT testleri güncel).

**Faz 6 — Sunum & teslim: henüz başlanmadı.**

**Sıradaki:** Faz 6 (sunum içeriği + demo provası) — artık IoT/AIoT katmanı çok
zengin: MQTT QoS/retain/LWT, sensör telemetrisi, anomali/bakım, rezervasyon,
analitik, sesli giriş + **edge AI (debounce), tahminleyici zekâ, çok-araçlı LLM
asistanı, karar logu, Pydantic doğrulama, logging, kilit/reconnect** anlatılacak.
İsteğe bağlı (C grubu, kullanıcı şimdilik istemedi): senaryo profilleri, GitHub
Actions CI + rozet, Docker/compose. İsteğe bağlı: gerçek ESP32/kamera-CV sensörü.

### Notlar / Kararlar
- Python 3.12.10 kullanılıyor (plan 3.11+ diyordu, uyumlu).
- LLM sağlayıcı varsayılanı **gemini** (model: gemini-2.5-flash) — kullanıcının
  Gemini API key'i var. .env'de GEMINI_API_KEY. NOT: gemini-2.0-flash ücretsiz
  kotası 0 çıktı, bu yüzden gemini-2.5-flash kullanıldı. Anthropic/OpenAI/Ollama
  client.py'de genişletme noktası olarak duruyor (henüz implemente değil).
- Gemini bazen geçici 503 (aşırı yük) döndürüyor; client.py'de retry + orchestrator'da
  keyword yedeği var, sistem LLM çökse de çalışıyor (demo güvencesi).
- Hungarian çoklu atama (G2.4) tamamlandı VE UI'a bağlandı: algorithm/hungarian.py
  + allocator.allocate_multiple + web POST /api/request_multi + "Aynı anda 3 araç"
  butonu (her araca ayrı renkte rota/animasyon, çakışmasız optimal atama).
- **Çıkış tercihi düzeltmesi (kullanıcı bug bildirimi):** Süre verildiğinde
  C=|d-α·t| maliyeti açık yön tercihini (girişe/çıkışa yakın) EZİYORDU; "çıkışa
  yakın" istense bile uzak yer veriyordu. Artık _spot_cost ortak çekirdeği: açık
  yön tercihi BİRİNCİL (o mesafe minimize edilir), |d-α·t| yalnızca tercih
  "farketmez" iken devreye girer. Regresyon testi eklendi (37 test).
- **Kapasite revize edildi (kullanıcı isteği):** Başlangıçtaki 50'lik basit ızgara
  yerine gerçekçi AVM otoparkı seçildi → **240 yer** (5 bant × 2 sıra × 24 sütun),
  6 yatay yol + 4 dikey bağlantı yolu (sütun 0/8/16/23). Tek kat. config.py'de
  parametrik (N_AISLES, SPOTS_PER_ROW, CROSS_LANE_EVERY ile kolayca ölçeklenir).
  Çok katlı düzen reddedildi (Faz 4'ü uzatmamak için). allocator 240 adayı ~54 ms'de
  çözüyor (yeterince hızlı). Spot id şeması: bant harfi + sıra-içi numara (A-1..E-48).
- requirements.txt'e hem anthropic hem openai hem requests kondu ki sağlayıcı
  değişse de kod çalışsın (Ollama requests ile HTTP üzerinden çağrılacak).

---

## 12. Açık Sorular / Yapılacak Kararlar

- LLM sağlayıcısı kesinleşecek: Ollama (yerel, ücretsiz) mı, API mı? Varsayılan: Ollama.
- Park yeri sayısı: ~~başlangıç 50~~ → **240'a çıkarıldı** (gerçekçi AVM düzeni, çözüldü).
- FastAPI REST katmanı eklenecek mi? Varsayılan: hayır (zaman kalırsa bonus).
- ~~Çoklu araç atama (Hungarian) yapılacak mı?~~ → **Yapıldı** (G2.4, algoritma+test).

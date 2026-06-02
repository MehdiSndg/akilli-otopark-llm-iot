# Akıllı Otopark Yönlendirme Sistemi (LLM + IoT)

Sürücü doğal dille konuşur ("elektrikli arabam var, 2 saat kalacağım"), bir
**LLM** isteği anlar ve **function calling** ile yönlendirme algoritmasını çağırır.
Algoritma graf üzerinde **A\*** mesafeleri ve **kalış süresi odaklı bir maliyet
fonksiyonu** ile en uygun boş park yerini bulur; sonuç hem doğal dille açıklanır
hem de **web tabanlı 2D simülasyonda** (FastAPI + Canvas) görsel olarak gösterilir.

> "Nesnelerin Yapay Zekası (IoT)" dersi dönem projesi — Yapay Zeka ve Veri
> Mühendisliği.

## Mimari

```
Sensör Simülatörü ──MQTT/yedek──► Backend (SQLite + doluluk)
                                       │
                                       ├── Algoritma (graf + A* + maliyet fonk.)
                                       └── LLM (doğal dil ↔ function calling)
                                       │
Web Arayüzü (FastAPI + Canvas) ◄── REST/WebSocket ──┘
(alternatif: Pygame masaüstü)
```

Üç katman:
- **IoT:** park yeri sensör simülasyonu + MQTT yayını + SQLite. Broker yoksa
  doluluk doğrudan DB'ye yazılır (brokersız yedek), sayılar yine canlı akar.
- **Algoritma:** graf üzerinde A* mesafeleri; **kalış süresi maliyet fonksiyonu**
  `C_i = |d_i − α·t|` ile yer seçimi (kısa kalan kapıya yakın, uzun kalan derine).
- **LLM:** doğal dili yapılandırılmış parametreye çevirir, sonucu açıklar.
  *(Karar algoritmaya/maliyet fonksiyonuna aittir; LLM yalnızca anlar + açıklar.)*

### Maliyet fonksiyonu (karar çekirdeği)

Her boş park yeri `P_i` için maliyet: `C_i = |d_i − α·t|`
- `d_i`: aracın girdiği kapıdan yere A* sürüş mesafesi
- `t`: tahmini kalış süresi (saat)
- `α`: mesafe-zaman ağırlık katsayısı (`config.ALPHA_DISTANCE_PER_HOUR`)

En küçük `C_i`'li boş yer atanır. Böylece kapı önleri kısa kalanlara ayrılır,
sirkülasyon artar. Süre verilmezse tercihe (girişe/çıkışa yakın) göre en yakın yer.

## Kurulum

### 1. Sanal ortam ve bağımlılıklar

```powershell
python -m venv venv
venv\Scripts\activate          # Windows PowerShell
# source venv/bin/activate     # Linux / macOS
pip install -r requirements.txt
```

### 2. Ortam değişkenleri

`.env.example` dosyasını `.env` olarak kopyala ve doldur:

```powershell
copy .env.example .env         # Windows
# cp .env.example .env         # Linux / macOS
```

LLM sağlayıcısını seç (`LLM_PROVIDER`): `anthropic` (varsayılan, önerilen),
`openai` veya `ollama`. API kullanıyorsan ilgili anahtarı `.env`'e gir.

### 3. Mosquitto MQTT broker (yerel)

IoT katmanı yerel bir MQTT broker'a ihtiyaç duyar.

**Windows:**
1. https://mosquitto.org/download/ adresinden indir ve kur.
2. Kurulum sırasında "Service" olarak kurarsan otomatik çalışır. Kontrol:
   ```powershell
   Get-Service mosquitto
   ```
3. Elle başlatmak için: `net start mosquitto`

**Linux:**
```bash
sudo apt install mosquitto mosquitto-clients
sudo systemctl start mosquitto
```

**macOS:**
```bash
brew install mosquitto
brew services start mosquitto
```

Broker'ın çalıştığını test et (iki terminal):
```bash
mosquitto_sub -t test/konu          # 1. terminal: dinle
mosquitto_pub -t test/konu -m "selam"   # 2. terminal: yayınla
```

### 4. (Opsiyonel) Ollama — yerel/ücretsiz LLM

```bash
# https://ollama.com/download adresinden kur, sonra:
ollama pull llama3.1
```
`.env`'de `LLM_PROVIDER=ollama` yap.

## Çalıştırma

```powershell
python main.py            # web arayüzü -> http://127.0.0.1:8000  (önerilen)
python main.py --pygame   # alternatif Pygame masaüstü arayüzü
```

Web sunucusu açıldığında sensör simülatörü ve MQTT abonesi otomatik başlar;
tarayıcıda `http://127.0.0.1:8000` adresini aç. Sağ panelden giriş kapısını seç
ve doğal dille park isteğini yaz (ör. *"elektrikli arabam var, 8 saat kalacağım"*).

## Testler

```powershell
pytest
```

## Klasör yapısı

```
simulator/   Sensör simülasyonu (MQTT yayını + brokersız yedek)
backend/     MQTT abonesi, SQLite, doluluk durumu
algorithm/   Graf, A*, maliyet fonksiyonu ile en uygun yer seçimi
llm/         Function calling araçları, sağlayıcı soyutlaması, orchestrator
web/         FastAPI sunucu + Canvas 2D simülasyon (birincil arayüz)
ui/          Pygame masaüstü arayüzü (alternatif)
tests/       pytest testleri
config.py    Tüm ayarlar (maliyet fonksiyonu katsayısı ALPHA dahil)
main.py      Giriş noktası
```

## Durum

Geliştirme aşamasında. İlerleme `CLAUDE.md` → "İlerleme Durumu" bölümünde.

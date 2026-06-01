# Akıllı Otopark Yönlendirme Sistemi (LLM + IoT)

Sürücü doğal dille konuşur ("elektrikli arabam var, çıkışa yakın bir yer
istiyorum"), bir **LLM** isteği anlar ve **function calling** ile yönlendirme
algoritmasını çağırır. Algoritma graf üzerinde **A\*** ile en uygun boş park
yerini bulur; sonuç hem doğal dille açıklanır hem de **Pygame** penceresinde
görsel olarak gösterilir.

> "Nesnelerin Yapay Zekası (IoT)" dersi dönem projesi — Yapay Zeka ve Veri
> Mühendisliği.

## Mimari

```
Sensör Simülatörü ──MQTT──► Backend (MQTT abonesi + SQLite)
                                 │
                                 ├── Algoritma (graf + A*)
                                 └── LLM (doğal dil ↔ function calling)
                                 │
Pygame Arayüzü ◄── fonksiyon çağrısı ──┘
```

Üç katman:
- **IoT:** park yeri sensör simülasyonu + MQTT yayını + SQLite.
- **Algoritma:** graf üzerinde A* ile en uygun yer; araç tipi/tercih filtresi.
- **LLM:** doğal dili yapılandırılmış parametreye çevirir, sonucu açıklar.
  *(Karar algoritmaya aittir; LLM yalnızca anlar + açıklar.)*

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
python main.py     # (G5.1'de tamamlanacak)
```

## Testler

```powershell
pytest
```

## Klasör yapısı

```
simulator/   Sensör simülasyonu (MQTT yayını)
backend/     MQTT abonesi, SQLite, doluluk durumu
algorithm/   Graf, A*, en uygun yer seçimi
llm/         Function calling araçları, sağlayıcı soyutlaması, orchestrator
ui/          Pygame arayüzü (ızgara, giriş kutusu, animasyon)
tests/       pytest testleri
config.py    Tüm ayarlar
main.py      Giriş noktası
```

## Durum

Geliştirme aşamasında. İlerleme `CLAUDE.md` → "İlerleme Durumu" bölümünde.

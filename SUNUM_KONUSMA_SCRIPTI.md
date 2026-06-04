# 🎤 Sunum Konuşma Scripti — Akıllı Otopark Yönlendirme Sistemi (LLM + IoT)
**Hazırlayan:** Mehdi Sındağ · Mehmet Ali Topkara — Nesnelerin Yapay Zekâsı (AIoT)
> 5 slaytlık sunum yapısına göre hazırlanmıştır (Kapak · Konu · Problem · Sistem/Akış · Sonuç). Her slayt için ~30–45 sn akıcı, kurallı Türkçe anlatım.

---

## Slayt 1 — Kapak / Açılış  (~25 sn)

> Merhaba, biz Mehdi Sındağ ve Mehmet Ali Topkara. Nesnelerin Yapay Zekâsı dersi için Akıllı Otopark Yönlendirme Sistemi projesini hazırladık. Projemiz; doğal dili, IoT verisini ve algoritmayı tek bir çalışan sistemde birleştiriyor. Sürücü doğal dille konuşur, sistem isteği anlar, en uygun park yerini seçer ve sonucu canlı olarak gösterir. Şimdi projenin konusunu açıklayalım.

🔑 **Terimler:** AIoT = Nesnelerin Yapay Zekâsı; IoT cihazlarının topladığı veriye yapay zekâ ile karar/anlam katmak.

## Slayt 2 — Projenin Konusu  (~40 sn)

> Bu proje, bir otoparkta boş yer bulma sürecini yapay zekâ ile kolaylaştıran bir yönlendirme sistemidir. Sürücü, isteğini doğal dille ifade eder; örneğin “elektrikli arabam var, 2 saat kalacağım” der. Büyük dil modeli, yani LLM, bu cümleyi anlar ve uygun parametrelere çevirir. Ardından algoritma, boş yerler arasından sürücüye en uygun olanı seçer. Sonuç hem yazıyla açıklanır hem de harita üzerinde canlı gösterilir. Sistem tamamen yazılımdır; gerçek donanım yoktur, sensörler simüle edilir, ancak mimari gerçekçidir.

🔑 **Terimler:** LLM = Large Language Model (Büyük Dil Modeli, ör. Gemini): doğal dili anlayan yapay zekâ modeli.

## Slayt 3 — Problem  (~35 sn)

> Büyük otoparklarda boş yer aramak, sürücüler için ciddi bir zaman ve yakıt kaybıdır. Sürücüler boş yer ararken gereksiz yere dolaşır ve bu durum otopark içinde trafik oluşturur. Mevcut sistemlerin çoğu yalnızca ilk boş yeri gösterir; sürücünün ihtiyacını ya da kalış süresini dikkate almaz. Teknik formlarla veya menülerle uğraşmak da kullanıcı için zahmetlidir. Sensörler doluluğu bilir, fakat bu ham veri tek başına anlamlı bir yönlendirmeye dönüşmez. Bu yüzden doğal dili anlayan ve doluluğu akıllıca değerlendiren bir sisteme ihtiyaç vardır.

## Slayt 4 — Geliştirilen Sistem ve Akış Diyagramı  (~45 sn)

> Sistem, gevşek bağlı katmanlardan oluşur ve akış şu sırayla ilerler. Önce sürücü, doğal dille park isteğini yazar. İkinci adımda LLM bu isteği anlar ve doğru fonksiyonu çağırır. Üçüncü adımda algoritma devreye girer; A* ile her boş yere olan mesafeyi hesaplar ve maliyet fonksiyonuyla en uygun yeri seçer. Son adımda web arayüzü, seçilen yeri canlı harita üzerinde ve doğal dille gösterir. Bu akışı alttan IoT katmanı besler: sensörler doluluğu üretir, MQTT ile yayınlar ve backend bunu SQLite veritabanında tutar. En önemli ilkemiz şudur: kararı deterministik algoritma verir, LLM yalnızca anlar ve açıklar. Maliyet fonksiyonumuz C eşittir d eksi alfa çarpı t’nin mutlak değeridir; yani kısa kalan araç kapıya yakın, uzun kalan araç daha derine yerleştirilir.

🔑 **Terimler:** MQTT = hafif IoT mesajlaşma protokolü (Message Queuing Telemetry Transport). A* = sezgisel destekli en kısa yol bulma algoritması. Maliyet fonksiyonu C = | d − α·t |: araç t saat kalacaksa ideal mesafe α·t olsun isteriz; gerçek mesafesi bu ideale en yakın olan boş yer seçilir.

## Slayt 5 — Sonuç, Çıktı ve Tasarım  (~40 sn)

> Sistemi çalışan bir prototip olarak başarıyla geliştirdik. Sürücü, yazdığı isteğe saniyeler içinde uygun bir park yeri önerisi alır. Web arayüzü otoparkı kuşbakışı gösterir; boş ve dolu yerler ile önerilen rota canlı olarak görünür. Kalış süresine göre yerleştirme, kapı önlerini kısa süreli araçlara bırakarak otoparkın sirkülasyonunu artırır. Sistem ayrıca çoklu araç ataması, doluluk tahmini, analitik panel ve anomali tespiti gibi yeteneklere sahiptir. LLM’e erişilemediğinde bile sistem, yedek yöntemle çalışmaya devam eder. Şimdi sizlere sistemi canlı olarak göstermek istiyoruz. Teşekkür ederiz.

---

## 📖 Terimler Sözlüğü

| Terim | Anlam |
|---|---|
| **AIoT** | Artificial Intelligence of Things — IoT verisine yapay zekâ ile karar katmak |
| **IoT** | Internet of Things — Nesnelerin İnterneti; cihazların veri paylaşması |
| **LLM** | Large Language Model — Büyük Dil Modeli (Gemini) |
| **Function calling** | LLM'in metni, parametreli bir fonksiyon çağrısına çevirmesi |
| **MQTT** | Message Queuing Telemetry Transport — hafif IoT mesajlaşma protokolü |
| **A*** | “A-star” — sezgisel destekli en kısa yol bulma algoritması |
| **Maliyet fonk.** | C = | d − α·t | — yeri kalış süresine göre seçen formül |
| **SQLite** | Tek dosyalık, sunucusuz ilişkisel veritabanı |
| **Edge AI** | Uç zekâ — basit kararın merkez yerine cihazın kendisinde verilmesi |
| **Anomali tespiti** | Çevrimdışı/takılı/düşük pilli sensörü yakalayıp bakım uyarısı vermek |

---

## ❓ Olası Sorular

- Neden A*, basit en-yakın değil? Otopark bir yol ağı olduğundan düz çizgi değil gerçek sürüş mesafesi gerekir; A* en kısa rotayı hızlı bulur.
- Neden MQTT? MQTT, gerçek IoT'nin sensör–broker–tüketici mimarisini gösterir; gevşek bağlı, ölçeklenebilir ve canlı çalışır.
- LLM yanlış anlarsa ne olur? Kararı zaten LLM vermez; ayrıca erişim sorununda anahtar-kelime yedeği devreye girer ve sistem çalışmaya devam eder.
- Gerçek sensör yokken bu IoT sayılır mı? Sensörler simüledir; ancak protokol, topoloji ve mimari tamamen gerçekçidir, kolayca gerçek donanıma bağlanabilir.
- Maliyet fonksiyonundaki α nedir? Otoparkın büyüklüğüne göre belirlenen, süreyi mesafeye çeviren bir ağırlık katsayısıdır.

"""
allocator.py — Maliyet fonksiyonu tabanlı en uygun park yeri seçimi.

Ana fonksiyon find_best_parking_spot(...) LLM'in function calling ile çağıracağı
fonksiyondur. Karar tamamen burada (deterministik algoritma) verilir; LLM yalnızca
sürücünün isteğini parametreye çevirir, kararı bu maliyet fonksiyonu verir.

Otoparkta BİRDEN FAZLA giriş ve çıkış vardır:
- Sürüş mesafesi (d_i) = aracın girdiği GİRİŞ'ten park yerine A* mesafesi.
- Çıkışa yürüme       = park yerinden en yakın ÇIKIŞ'a A* mesafesi.

Karar çekirdeği — kalış süresi (t) verildiğinde — sürekli maliyet fonksiyonudur:

    C_i = | d_i - (ALPHA * t) |        (en küçük C_i'li boş yer seçilir)

Yani t saat kalacak araç için ideal park mesafesi ALPHA*t birimdir; bu ideale en
yakın yer atanır -> kısa kalan kapıya yakın, uzun kalan derine gider (sirkülasyon
optimizasyonu). Süre verilmezse maliyet fonksiyonu devre dışıdır; o zaman tercihe
(girişe/çıkışa yakın) göre en yakın yer seçilir.

Adımlar:
  (a) Boş park yerlerini al, (b) araç tipi/şarj ihtiyacına göre filtrele,
  (c) her aday için girişten sürüş (d_i) ve en yakın çıkışa yürüme mesafesini A*
      ile hesapla, (d) maliyet/tercihe göre en uygun yeri seç, (e) sonucu döndür.
"""

import config
from algorithm.graph import build_parking, ENTRANCES, EXITS
from algorithm.astar import a_star
from algorithm.hungarian import hungarian
from backend import parking_state

# Statik yerleşim/graf yalnızca bir kez kurulur (doluluk DB'den gelir).
_SPOTS, _GRAPH = build_parking()

# Çoklu atamada (allocate_multiple) yanlış tipte yere atamayı son çare yapan ceza.
# Mesafe/maliyet birkaç yüzü geçmediğinden bu büyük katsayı, doğru tipte yer
# varken aracı asla yanlış tipe koymamayı garanti eder; hiç uygun tip yoksa
# (mecbur kalınca) yine de bir yer bulunur.
TYPE_PENALTY = 1e6


def _best_drive(node, entrance=None):
    """Girişten park yerine en kısa yol ve mesafe. (path, dist).

    entrance verilirse yalnızca o girişten hesaplanır (sürücünün fiziksel
    girdiği kapı); aksi halde en yakın giriş seçilir."""
    gates = [entrance] if entrance else ENTRANCES
    best_path, best = None, float("inf")
    for gate in gates:
        path, dist = a_star(_GRAPH, gate, node)
        if dist < best:
            best, best_path = dist, path
    return best_path, best


def _ideal_distance(duration_hours):
    """t saat kalış için ideal park mesafesi (ALPHA*t). None = süre verilmedi."""
    if duration_hours is None:
        return None
    return config.ALPHA_DISTANCE_PER_HOUR * duration_hours


def _spot_cost(drive, walk, use_walk, explicit_pref, ideal):
    """Bir aday yerin maliyeti (küçük = iyi). Tek-araç ve çoklu-araç ortak çekirdeği.

    Öncelik kuralı:
      - Açık yön tercihi (girişe/çıkışa yakın) BİRİNCİLDİR: o mesafe doğrudan
        minimize edilir (çıkışa yakın -> yürüme, girişe yakın -> sürüş). Süre
        verilse bile tercih ezilmez (kullanıcı net söylediyse ona uyulur).
      - Tercih "farketmez" + süre verilmişse: sirkülasyon maliyeti |d - ALPHA*t|
        (kısa kalan kapıya yakın, uzun kalan derine) devreye girer.
      - Hiçbiri yoksa: girişten sürüş mesafesi (en yakın yer).
    """
    if explicit_pref:
        return walk if use_walk else drive
    if ideal is not None:
        return abs(drive - ideal)
    return drive


def _best_walk(node):
    """Park yerinden en yakın çıkışa en kısa yürüme mesafesi."""
    best = float("inf")
    for gate in EXITS:
        _, dist = a_star(_GRAPH, node, gate)
        best = min(best, dist)
    return best


def _required_type(vehicle_type, needs_charging):
    """Araç tipi/şarj ihtiyacının gerektirdiği park yeri tipi."""
    if vehicle_type == "ev" or needs_charging:
        return "ev_charging"
    if vehicle_type == "disabled":
        return "disabled"
    return "normal"


def _filter_candidates(empty_spots, vehicle_type, needs_charging):
    req_type = _required_type(vehicle_type, needs_charging)
    candidates = [s for s in empty_spots if s["type"] == req_type]
    if not candidates:
        candidates = list(empty_spots)   # uygun özel yer yoksa herhangi bir boş yer
    return candidates


def find_best_parking_spot(vehicle_type="normal", preference="any",
                           needs_charging=False, duration_hours=None,
                           entrance=None, spots=None):
    """
    Sürücü isteğine en uygun boş park yerini bulur.

    entrance      : sürücünün girdiği kapı düğümü (None = en yakın giriş).
    duration_hours: tahmini kalış süresi (saat). Verilirse karar MALİYET
                    FONKSİYONU ile verilir: C_i = |d_i - ALPHA*t| (en küçük seçilir).

    Skor (küçük = iyi, _spot_cost):
      - Açık yön tercihi (girişe/çıkışa yakın) BİRİNCİL: o mesafe minimize edilir
        (çıkışa yakın -> çıkışa yürüme; girişe yakın -> girişten sürüş). Süre
        verilse bile tercih ezilmez.
      - Tercih "farketmez" + süre verilmişse: maliyet = |sürüş - ALPHA*süre|
        (kısa kalan kapıya yakın, uzun kalan derine — sirkülasyon).
      - Hiçbiri yoksa: girişten en kısa sürüş.
    Döner: {spot_id, path, distance, walk_to_exit, cost, spot} ya da None.
    """
    all_spots = parking_state.get_state() if spots is None else spots
    empty_spots = [s for s in all_spots if not s["occupied"] and not s.get("reserved")]

    candidates = _filter_candidates(empty_spots, vehicle_type, needs_charging)
    if not candidates:
        return None

    use_walk = (preference == "nearest_exit")
    explicit_pref = preference in ("nearest_entrance", "nearest_exit")
    ideal = _ideal_distance(duration_hours)               # ALPHA*t ya da None
    best = None
    best_cost = None

    for s in candidates:
        node = s["node_id"]
        drive_path, drive = _best_drive(node, entrance)   # d_i: girişten sürüş
        walk = _best_walk(node)                           # en yakın çıkışa yürüme
        cost = _spot_cost(drive, walk, use_walk, explicit_pref, ideal)
        if best_cost is None or cost < best_cost:
            best_cost = cost
            best = {
                "spot_id": s["id"],
                "path": drive_path,
                "distance": round(drive, 2),
                "walk_to_exit": round(walk, 2),
                "cost": round(cost, 2),
                "spot": s,
            }

    return best


def _request_cost_row(req, empty, drive_cache, walk_cache):
    """Bir araç isteği için tüm boş yerlere maliyet + yol bilgisini hesapla.

    drive_cache : {(entrance, node) -> (path, dist)} sürüş mesafesi önbelleği.
    walk_cache  : {node -> dist} çıkışa yürüme önbelleği (istekten bağımsız).
    Aynı girişi paylaşan araçlar A*'yı tekrar hesaplamaz.

    Maliyet, tek-araç find_best_parking_spot ile AYNI çekirdeği kullanır:
      - süre verilmişse  : |sürüş_mesafesi - ALPHA*süre|   (ideale yakınlık)
      - süre verilmemişse: tercihe göre temel mesafe (nearest_exit -> yürüme)
    Buna yanlış araç tipine atama için TYPE_PENALTY eklenir (son çare).

    Döner: (costs, info) — costs[j] skaler maliyet, info[j] = (drive_path,
    drive, walk).
    """
    vt = req.get("vehicle_type", "normal")
    pref = req.get("preference", "any")
    needs = req.get("needs_charging", False)
    dur = req.get("duration_hours")
    ent = req.get("entrance")

    req_type = _required_type(vt, needs)
    ideal = _ideal_distance(dur)                            # ALPHA*t ya da None
    use_walk = (pref == "nearest_exit")
    explicit_pref = pref in ("nearest_entrance", "nearest_exit")

    costs, info = [], []
    for s in empty:
        node = s["node_id"]
        key = (ent, node)
        if key not in drive_cache:
            drive_cache[key] = _best_drive(node, ent)       # girişten sürüş
        drive_path, drive = drive_cache[key]
        if node not in walk_cache:
            walk_cache[node] = _best_walk(node)             # en yakın çıkışa yürüme
        walk = walk_cache[node]
        base = _spot_cost(drive, walk, use_walk, explicit_pref, ideal)
        type_miss = 0 if s["type"] == req_type else 1
        costs.append(type_miss * TYPE_PENALTY + base)
        info.append((drive_path, round(drive, 2), round(walk, 2)))
    return costs, info


def allocate_multiple(requests, spots=None):
    """Aynı anda gelen birden çok aracı boş yerlere OPTIMAL (Hungarian) atar.

    Greedy atamadan farkı: iki aracı asla aynı yere göndermez ve aracların
    TOPLAM maliyetini en küçük yapar (bir aracı biraz uzağa yollamak diğerini
    çok daha iyi yere koyuyorsa onu seçer).

    requests : her biri {vehicle_type, preference, needs_charging,
               duration_hours, entrance} içeren dict listesi (eksik alanlar
               find_best_parking_spot varsayılanlarına düşer).
    spots    : None ise canlı doluluk (parking_state) kullanılır.
    Döner    : requests ile AYNI sırada sonuç listesi; her eleman
               {spot_id, path, distance, walk_to_exit, spot} ya da None
               (o araca verilecek boş yer kalmadıysa).
    """
    n = len(requests)
    if n == 0:
        return []

    all_spots = parking_state.get_state() if spots is None else spots
    empty = [s for s in all_spots if not s["occupied"] and not s.get("reserved")]
    if not empty:
        return [None] * n

    # Maliyet matrisi + yol bilgisi (her araç × her boş yer).
    # Önbellekler aynı giriş/çıkış A* hesabını araçlar arasında paylaştırır.
    cost, info = [], []
    drive_cache, walk_cache = {}, {}
    for req in requests:
        c, inf = _request_cost_row(req, empty, drive_cache, walk_cache)
        cost.append(c)
        info.append(inf)

    m = len(empty)
    if n <= m:
        assign = hungarian(cost)                       # araç -> yer
    else:
        # Araç sayısı yerden fazla: devrik çöz, fazla araçlar boşta kalır
        tcost = [[cost[i][j] for i in range(n)] for j in range(m)]
        spot_assign = hungarian(tcost)                 # yer -> araç
        assign = [-1] * n
        for j, i in enumerate(spot_assign):
            if i != -1:
                assign[i] = j

    results = []
    for i in range(n):
        j = assign[i]
        if j == -1:                                    # bu araca yer kalmadı
            results.append(None)
            continue
        s = empty[j]
        drive_path, drive, walk = info[i][j]
        results.append({
            "spot_id": s["id"],
            "path": drive_path,
            "distance": drive,
            "walk_to_exit": walk,
            "spot": s,
        })
    return results

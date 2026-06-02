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
from backend import parking_state

# Statik yerleşim/graf yalnızca bir kez kurulur (doluluk DB'den gelir).
_SPOTS, _GRAPH = build_parking()


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


def _best_walk(node):
    """Park yerinden en yakın çıkışa en kısa yürüme mesafesi."""
    best = float("inf")
    for gate in EXITS:
        _, dist = a_star(_GRAPH, node, gate)
        best = min(best, dist)
    return best


def _filter_candidates(empty_spots, vehicle_type, needs_charging):
    if vehicle_type == "ev" or needs_charging:
        candidates = [s for s in empty_spots if s["type"] == "ev_charging"]
    elif vehicle_type == "disabled":
        candidates = [s for s in empty_spots if s["type"] == "disabled"]
    else:
        candidates = [s for s in empty_spots if s["type"] == "normal"]
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

    Skor (küçük = iyi):
      - Süre verilmişse: maliyet = |sürüş_mesafesi - ALPHA*süre|  (ideale yakınlık).
      - Süre verilmemişse: maliyet = tercihe göre temel mesafe (nearest_exit ->
        çıkışa yürüme; aksi halde girişten sürüş).
    Döner: {spot_id, path, distance, walk_to_exit, cost, spot} ya da None.
    """
    all_spots = parking_state.get_state() if spots is None else spots
    empty_spots = [s for s in all_spots if not s["occupied"]]

    candidates = _filter_candidates(empty_spots, vehicle_type, needs_charging)
    if not candidates:
        return None

    use_walk = (preference == "nearest_exit")
    ideal = _ideal_distance(duration_hours)               # ALPHA*t ya da None
    best = None
    best_cost = None

    for s in candidates:
        node = s["node_id"]
        drive_path, drive = _best_drive(node, entrance)   # d_i: girişten sürüş
        walk = _best_walk(node)                           # en yakın çıkışa yürüme
        if ideal is not None:
            cost = abs(drive - ideal)                     # C_i = |d_i - ALPHA*t|
        else:
            cost = walk if use_walk else drive            # süre yoksa tercihe göre
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

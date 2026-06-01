"""
allocator.py — Tercihe göre filtre + en uygun park yeri seçimi.

Ana fonksiyon find_best_parking_spot(...) LLM'in function calling ile çağıracağı
fonksiyondur. Karar tamamen burada (deterministik algoritma) verilir.

Otoparkta BİRDEN FAZLA giriş ve çıkış vardır:
- Sürüş mesafesi = en yakın GİRİŞ'ten park yerine A* mesafesi.
- Çıkışa yürüme = park yerinden en yakın ÇIKIŞ'a A* mesafesi.

Adımlar:
  (a) Boş park yerlerini al, (b) araç tipi/şarj ihtiyacına göre filtrele,
  (c) her aday için en yakın girişten sürüş ve en yakın çıkışa yürüme mesafesini
      A* ile hesapla, (d) tercihe göre en uygun yeri seç, (e) sonucu döndür.
"""

from algorithm.graph import build_parking, ENTRANCES, EXITS
from algorithm.astar import a_star
from backend import parking_state

# Statik yerleşim/graf yalnızca bir kez kurulur (doluluk DB'den gelir).
_SPOTS, _GRAPH = build_parking()


def _best_drive(node):
    """En yakın girişten park yerine en kısa yol ve mesafe. (path, dist)."""
    best_path, best = None, float("inf")
    for gate in ENTRANCES:
        path, dist = a_star(_GRAPH, gate, node)
        if dist < best:
            best, best_path = dist, path
    return best_path, best


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
                           needs_charging=False, spots=None):
    """
    Sürücü isteğine en uygun boş park yerini bulur.
    Döner: {spot_id, path, distance, walk_to_exit, spot} ya da None.
    """
    all_spots = parking_state.get_state() if spots is None else spots
    empty_spots = [s for s in all_spots if not s["occupied"]]

    candidates = _filter_candidates(empty_spots, vehicle_type, needs_charging)
    if not candidates:
        return None

    use_walk = (preference == "nearest_exit")
    best = None
    best_key = float("inf")

    for s in candidates:
        node = s["node_id"]
        drive_path, drive = _best_drive(node)     # en yakın girişten sürüş
        walk = _best_walk(node)                   # en yakın çıkışa yürüme
        key = walk if use_walk else drive
        if key < best_key:
            best_key = key
            best = {
                "spot_id": s["id"],
                "path": drive_path,
                "distance": round(drive, 2),
                "walk_to_exit": round(walk, 2),
                "spot": s,
            }

    return best

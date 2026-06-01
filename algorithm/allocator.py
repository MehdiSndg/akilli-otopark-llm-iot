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


def _preferred_zone(duration_hours):
    """Kalış süresine göre tercih edilen bölge. None = süre etkisi yok.

    Kısa kalış çıkışa/kapıya yakın (hızlı giriş-çıkış), uzun kalış ortaya
    (kapı trafiğini şişirmesin) yönlendirilir. Aradaki süreler nötr bırakılır."""
    if duration_hours is None:
        return None
    if duration_hours <= config.SHORT_STAY_MAX_HOURS:
        return "çıkış yakını"
    if duration_hours >= config.LONG_STAY_MIN_HOURS:
        return "orta"
    return None


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
    duration_hours: tahmini kalış süresi; verilirse uygun olmayan bölgedeki
                    yerlere config.ZONE_PENALTY eklenerek turnover optimize edilir.

    Skor (sözlüksel, küçük = iyi): (bölge_uymazlığı, temel_mesafe). Süre verilirse
    önce uygun bölge (kısa->çıkış yakını, uzun->orta) seçilir, o bölge içinde en
    yakın yere gidilir; uygun bölgede yer yoksa mesafeye göre en iyiye düşülür.
    Temel mesafe tercihe göre sürüş ya da çıkışa yürümedir.
    Döner: {spot_id, path, distance, walk_to_exit, spot} ya da None.
    """
    all_spots = parking_state.get_state() if spots is None else spots
    empty_spots = [s for s in all_spots if not s["occupied"]]

    candidates = _filter_candidates(empty_spots, vehicle_type, needs_charging)
    if not candidates:
        return None

    use_walk = (preference == "nearest_exit")
    pref_zone = _preferred_zone(duration_hours)
    best = None
    best_key = None

    for s in candidates:
        node = s["node_id"]
        drive_path, drive = _best_drive(node, entrance)   # girişten sürüş
        walk = _best_walk(node)                           # en yakın çıkışa yürüme
        base = walk if use_walk else drive
        zone_miss = 1 if (pref_zone and s["zone"] != pref_zone) else 0
        key = (zone_miss, base)                           # bölge birincil, mesafe ikincil
        if best_key is None or key < best_key:
            best_key = key
            best = {
                "spot_id": s["id"],
                "path": drive_path,
                "distance": round(drive, 2),
                "walk_to_exit": round(walk, 2),
                "spot": s,
            }

    return best

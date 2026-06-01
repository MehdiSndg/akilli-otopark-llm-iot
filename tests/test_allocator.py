"""
test_allocator.py — Yer seçimi (allocator) testleri.

Gerçek otopark yerleşimini kullanır ama doluluğu test içinde belirler
(parking_state/DB'ye bağımlı olmadan). Böylece deterministik kontrol yapılır.
"""

from algorithm.graph import build_parking
from algorithm import allocator


def _spots_with_free(free_ids):
    """Verilen id'ler dışındaki tüm yerleri DOLU işaretleyen spot dict listesi."""
    spots, _ = build_parking()
    return [
        {
            "id": s.id, "node_id": s.node_id, "type": s.type,
            "occupied": s.id not in free_ids,
            "x": s.x, "y": s.y, "zone": s.zone,
        }
        for s in spots
    ]


def test_picks_the_only_free_spot():
    spots = _spots_with_free({"C-12"})       # C-12 normal bir yer
    res = allocator.find_best_parking_spot("normal", "any", False, spots=spots)
    assert res is not None
    assert res["spot_id"] == "C-12"
    assert res["path"][0].startswith("ENTRANCE") and res["path"][-1] == "C-12"
    assert res["distance"] > 0


def test_disabled_vehicle_gets_disabled_spot():
    # Bir engelli (A-3) ve bir normal (C-12) yer boş; engelli araç engelli yere gitmeli
    spots = _spots_with_free({"A-3", "C-12"})
    res = allocator.find_best_parking_spot("disabled", "any", False, spots=spots)
    assert res["spot"]["type"] == "disabled"
    assert res["spot_id"] == "A-3"


def test_ev_vehicle_gets_charging_spot():
    # Bir EV (A-10) ve bir normal (C-12) yer boş; elektrikli araç şarjlı yere gitmeli
    spots = _spots_with_free({"A-10", "C-12"})
    res = allocator.find_best_parking_spot("ev", "any", True, spots=spots)
    assert res["spot"]["type"] == "ev_charging"
    assert res["spot_id"] == "A-10"


def test_no_free_spot_returns_none():
    spots = _spots_with_free(set())          # hepsi dolu
    res = allocator.find_best_parking_spot("normal", "any", False, spots=spots)
    assert res is None


def test_preference_changes_choice():
    # Biri girişe yakın (E-25, alt bant), biri çıkışa yakın (A-20, üst bant) iki boş yer
    spots = _spots_with_free({"E-25", "A-20"})
    near_entrance = allocator.find_best_parking_spot("normal", "nearest_entrance", False, spots=spots)
    near_exit = allocator.find_best_parking_spot("normal", "nearest_exit", False, spots=spots)
    # Tercih değişince seçilen yer de değişmeli
    assert near_entrance["spot_id"] != near_exit["spot_id"]
    assert near_entrance["spot_id"] == "E-25"   # giriş sol-altta
    assert near_exit["spot_id"] == "A-20"       # çıkış üst-ortada

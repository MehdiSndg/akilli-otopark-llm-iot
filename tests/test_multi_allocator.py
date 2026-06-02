"""
test_multi_allocator.py — Çoklu araç (Hungarian) atama testleri.

Gerçek otopark yerleşimini kullanır ama doluluğu test içinde belirler.
allocate_multiple'ın iki aracı asla aynı yere göndermediğini, araç tiplerine
saygı duyduğunu ve toplam mesafeyi optimize ettiğini doğrular.
"""

from algorithm.graph import build_parking, ENTRANCES
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


def test_two_vehicles_get_distinct_spots():
    spots = _spots_with_free({"C-12", "C-13"})
    reqs = [{"vehicle_type": "normal", "entrance": ENTRANCES[0]},
            {"vehicle_type": "normal", "entrance": ENTRANCES[0]}]
    res = allocator.allocate_multiple(reqs, spots=spots)
    assert all(r is not None for r in res)
    assigned = {r["spot_id"] for r in res}
    assert assigned == {"C-12", "C-13"}            # ikisi de farklı yer
    assert res[0]["spot_id"] != res[1]["spot_id"]


def test_no_collision_when_both_prefer_same_spot():
    # E-1 her iki araç için de aynı girişe en yakın; yine de ikisi paylaşamaz.
    spots = _spots_with_free({"E-1", "E-2"})
    reqs = [{"vehicle_type": "normal", "entrance": ENTRANCES[0]},
            {"vehicle_type": "normal", "entrance": ENTRANCES[0]}]
    res = allocator.allocate_multiple(reqs, spots=spots)
    assigned = {r["spot_id"] for r in res}
    assert assigned == {"E-1", "E-2"}


def test_respects_vehicle_types():
    # EV (A-10) + engelli (A-3) + normal (C-12) yer boş; istekler eşleşmeli.
    spots = _spots_with_free({"A-10", "A-3", "C-12"})
    reqs = [{"vehicle_type": "ev", "needs_charging": True},
            {"vehicle_type": "disabled"},
            {"vehicle_type": "normal"}]
    res = allocator.allocate_multiple(reqs, spots=spots)
    assert res[0]["spot"]["type"] == "ev_charging"
    assert res[1]["spot"]["type"] == "disabled"
    assert res[2]["spot"]["type"] == "normal"
    assert len({r["spot_id"] for r in res}) == 3


def test_more_vehicles_than_spots():
    spots = _spots_with_free({"C-12"})             # tek boş yer
    reqs = [{"vehicle_type": "normal", "entrance": ENTRANCES[0]},
            {"vehicle_type": "normal", "entrance": ENTRANCES[0]}]
    res = allocator.allocate_multiple(reqs, spots=spots)
    parked = [r for r in res if r is not None]
    assert len(parked) == 1                        # biri park eder
    assert res.count(None) == 1                    # biri yer bulamaz
    assert parked[0]["spot_id"] == "C-12"


def test_no_free_spots_all_none():
    spots = _spots_with_free(set())
    reqs = [{"vehicle_type": "normal"}, {"vehicle_type": "normal"}]
    res = allocator.allocate_multiple(reqs, spots=spots)
    assert res == [None, None]


def test_empty_requests():
    spots = _spots_with_free({"C-12"})
    assert allocator.allocate_multiple([], spots=spots) == []


def test_optimal_beats_greedy_total_distance():
    # İki giriş, iki yer. Her araç kendi girişine yakın yere gitmeli; toplam
    # mesafe greedy'den küçük ya da eşit olmalı (Hungarian optimal).
    spots = _spots_with_free({"E-1", "E-24"})
    reqs = [{"vehicle_type": "normal", "entrance": ENTRANCES[0]},   # sol giriş
            {"vehicle_type": "normal", "entrance": ENTRANCES[1]}]   # sağ giriş
    res = allocator.allocate_multiple(reqs, spots=spots)
    # Sol girişten gelen sol yere (E-1), sağ girişten gelen sağ yere (E-24)
    assert res[0]["spot_id"] == "E-1"
    assert res[1]["spot_id"] == "E-24"

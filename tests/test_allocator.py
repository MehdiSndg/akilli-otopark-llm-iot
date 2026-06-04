"""
test_allocator.py — Yer seçimi (allocator) testleri.

Gerçek otopark yerleşimini kullanır ama doluluğu test içinde belirler
(parking_state/DB'ye bağımlı olmadan). Böylece deterministik kontrol yapılır.
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
    # E-25 otopark GİRİŞİNE yakın (driveE0~6.6), E-13 araç ÇIKIŞINA (VEXIT) yakın
    # (toVEXIT~12.1). nearest_exit artık AVM kapısını DEĞİL araç çıkışını hedefler.
    spots = _spots_with_free({"E-25", "E-13"})
    near_entrance = allocator.find_best_parking_spot("normal", "nearest_entrance", False, spots=spots)
    near_exit = allocator.find_best_parking_spot("normal", "nearest_exit", False, spots=spots)
    # Tercih değişince seçilen yer de değişmeli
    assert near_entrance["spot_id"] != near_exit["spot_id"]
    assert near_entrance["spot_id"] == "E-25"   # otopark girişine en yakın
    assert near_exit["spot_id"] == "E-13"       # araç çıkışına (VEXIT) en yakın


def test_nearest_mall_minimizes_walk_not_entrance():
    # REGRESYON: "AVM girişine yakın" (nearest_mall) AVM YAYA KAPISINA yürümeyi
    # minimize etmeli; otopark girişine (nearest_entrance) yakınlıkla KARIŞTIRILMAMALI.
    # B-2 AVM kapısına yakın (yürüme~16), E-2 otopark girişine yakın (sürüş~13).
    spots = _spots_with_free({"B-2", "E-2"})
    near_mall = allocator.find_best_parking_spot("normal", "nearest_mall", False,
                                                 spots=spots, entrance=ENTRANCES[0])
    near_entrance = allocator.find_best_parking_spot("normal", "nearest_entrance", False,
                                                     spots=spots, entrance=ENTRANCES[0])
    assert near_mall["spot_id"] == "B-2"          # AVM yaya kapısına en yakın
    assert near_entrance["spot_id"] == "E-2"      # otopark girişine en yakın
    assert near_mall["spot_id"] != near_entrance["spot_id"]   # üç kapı ayrı şeyler
    assert near_mall["walk_to_mall"] < near_entrance["walk_to_mall"]


def test_entrance_changes_choice():
    # E-1 sol-altta, E-24 sağ-altta. Sürücünün girdiği kapı seçimi değiştirmeli.
    spots = _spots_with_free({"E-1", "E-24"})
    left = allocator.find_best_parking_spot("normal", "any", spots=spots,
                                            entrance=ENTRANCES[0])
    right = allocator.find_best_parking_spot("normal", "any", spots=spots,
                                             entrance=ENTRANCES[1])
    assert left["spot_id"] == "E-1"             # sol girişten en yakın
    assert right["spot_id"] == "E-24"           # sağ girişten en yakın
    # Yol gerçekten seçilen girişten başlamalı
    assert left["path"][0] == ENTRANCES[0]
    assert right["path"][0] == ENTRANCES[1]


# Maliyet fonksiyonu testleri: ENTRANCE-0'dan sürüş mesafeleri
#   E-1 ≈ 12.1 (kapıya yakın), C-1 ≈ 23.1 (orta derinlik), E-24 ≈ 41.7 (derin/uzak).
# ALPHA=5 -> ideal mesafe = 5*t. t arttıkça seçilen yer derinleşmeli.
def test_short_stay_parks_near_entrance():
    # Kısa kalış (t=1, ideal≈5): kapıya en yakın yer seçilmeli -> E-1
    spots = _spots_with_free({"E-1", "C-1", "E-24"})
    res = allocator.find_best_parking_spot("normal", "any", duration_hours=1,
                                           spots=spots, entrance=ENTRANCES[0])
    assert res["spot_id"] == "E-1"


def test_medium_stay_parks_middle():
    # Orta kalış (t=4, ideal≈20): orta derinlikteki yer seçilmeli -> C-1
    spots = _spots_with_free({"E-1", "C-1", "E-24"})
    res = allocator.find_best_parking_spot("normal", "any", duration_hours=4,
                                           spots=spots, entrance=ENTRANCES[0])
    assert res["spot_id"] == "C-1"


def test_long_stay_parks_deeper():
    # Uzun kalış (t=8, ideal≈40): derindeki/uzak yer seçilmeli -> E-24
    spots = _spots_with_free({"E-1", "C-1", "E-24"})
    res = allocator.find_best_parking_spot("normal", "any", duration_hours=8,
                                           spots=spots, entrance=ENTRANCES[0])
    assert res["spot_id"] == "E-24"


def test_no_duration_picks_nearest():
    # Süre verilmezse maliyet fonksiyonu devre dışı; en yakın yer seçilmeli -> E-1
    spots = _spots_with_free({"E-1", "C-1", "E-24"})
    res = allocator.find_best_parking_spot("normal", "any", spots=spots,
                                           entrance=ENTRANCES[0])
    assert res["spot_id"] == "E-1"


def test_requested_spot_honored_when_free():
    # Sürücü belirli yer isterse (D-34) ve boşsa oraya yerleştirilmeli
    spots = _spots_with_free({"D-34", "E-27"})
    res = allocator.find_best_parking_spot("normal", "any", spots=spots,
                                           requested_spot_id="D-34")
    assert res["spot_id"] == "D-34"
    assert res["requested_status"] == "ok"


def test_requested_spot_taken_falls_back():
    # İstenen yer DOLUYSA alternatife düşmeli ve durum "taken" işaretlenmeli
    spots = _spots_with_free({"E-27"})        # D-34 dolu (free değil)
    res = allocator.find_best_parking_spot("normal", "any", spots=spots,
                                           requested_spot_id="D-34")
    assert res["spot_id"] == "E-27"
    assert res["requested_status"] == "taken"


def test_requested_spot_invalid_falls_back():
    # Olmayan yer (A-99) -> alternatif + "invalid"
    spots = _spots_with_free({"E-27"})
    res = allocator.find_best_parking_spot("normal", "any", spots=spots,
                                           requested_spot_id="A-99")
    assert res["spot_id"] == "E-27"
    assert res["requested_status"] == "invalid"


def test_cost_field_is_distance_to_ideal():
    # Sonuçtaki 'cost' alanı |d_i - ALPHA*t| olmalı (şeffaflık/açıklanabilirlik)
    import config
    spots = _spots_with_free({"E-1"})
    res = allocator.find_best_parking_spot("normal", "any", duration_hours=2,
                                           spots=spots, entrance=ENTRANCES[0])
    ideal = config.ALPHA_DISTANCE_PER_HOUR * 2
    assert abs(res["cost"] - abs(res["distance"] - ideal)) < 0.05


def test_explicit_preference_overrides_duration():
    # REGRESYON: açık yön tercihi verilince süre maliyet fonksiyonunu EZMEMELİ.
    # E-25 girişe yakın (çıkışa uzak), E-13 araç çıkışına yakın (girişe görece uzak).
    spots = _spots_with_free({"E-25", "E-13"})
    # Çıkışa yakın + kısa süre -> yine çıkışa yakın (E-13) gelmeli
    near_exit = allocator.find_best_parking_spot("normal", "nearest_exit",
                                                 duration_hours=1, spots=spots,
                                                 entrance=ENTRANCES[0])
    assert near_exit["spot_id"] == "E-13"        # araç çıkışına yakın (süre ezmedi)
    # Girişe yakın + uzun süre de tercihi korumalı
    near_entrance = allocator.find_best_parking_spot("normal", "nearest_entrance",
                                                     duration_hours=8, spots=spots,
                                                     entrance=ENTRANCES[0])
    assert near_entrance["spot_id"] == "E-25"    # girişe yakın (süre ezmedi)

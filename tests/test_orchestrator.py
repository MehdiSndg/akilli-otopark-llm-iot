"""
test_orchestrator.py — LLM orchestrator testleri.

LLM çağrısı mock'lanır (gerçek API/ağ gerekmez). Örnek cümlelerin doğru
parametrelere çözülmesi, varsayılana düşme ve keyword yedeği test edilir.
"""

from algorithm.graph import build_parking, ENTRANCES
from llm import orchestrator
from llm.client import LLMClient


class FakeClient(LLMClient):
    """Testte gerçek LLM yerine kullanılan sahte istemci."""

    def __init__(self, args=None, raise_on_call=False):
        self._args = args
        self._raise = raise_on_call

    def extract_tool_call(self, user_text):
        if self._raise:
            raise RuntimeError("LLM erişilemiyor (test)")
        if self._args is None:
            return None
        return {"name": "find_best_parking_spot", "args": self._args}

    def explain(self, user_text, result, params):
        return "Test açıklaması."


def _spots_with_free(free_ids):
    spots, _ = build_parking()
    return [
        {"id": s.id, "node_id": s.node_id, "type": s.type,
         "occupied": s.id not in free_ids, "x": s.x, "y": s.y, "zone": s.zone}
        for s in spots
    ]


def test_llm_args_drive_allocation():
    # LLM elektrikli + çıkışa yakın çıkarıyor; A-10 (ev) boş -> oraya yönlenmeli
    spots = _spots_with_free({"A-10", "C-12"})
    client = FakeClient(args={"vehicle_type": "ev", "preference": "nearest_exit",
                              "needs_charging": True})
    out = orchestrator.handle_request("elektrikli arabam var", spots=spots, client=client)
    assert out["source"] == "llm"
    assert out["params"]["vehicle_type"] == "ev"
    assert out["result"]["spot"]["type"] == "ev_charging"
    assert out["reply"] == "Test açıklaması."


def test_missing_params_fall_to_defaults():
    # LLM sadece preference veriyor; eksikler varsayılana çekilmeli
    spots = _spots_with_free({"C-12"})
    client = FakeClient(args={"preference": "nearest_entrance"})
    out = orchestrator.handle_request("bir yer ver", spots=spots, client=client)
    assert out["params"]["vehicle_type"] == "normal"   # varsayılan
    assert out["params"]["needs_charging"] is False
    assert out["params"]["preference"] == "nearest_entrance"


def test_ev_forces_needs_charging():
    # vehicle_type=ev ise needs_charging True'ya çekilmeli
    spots = _spots_with_free({"A-10"})
    client = FakeClient(args={"vehicle_type": "ev", "preference": "any",
                              "needs_charging": False})
    out = orchestrator.handle_request("elektrikli", spots=spots, client=client)
    assert out["params"]["needs_charging"] is True


def test_keyword_fallback_when_no_tool_call():
    # LLM araç çağırmazsa (None) metinden keyword ile çıkarılmalı
    spots = _spots_with_free({"A-3", "C-12"})   # A-3 engelli boş
    client = FakeClient(args=None)
    out = orchestrator.handle_request("engelli yerim lazım", spots=spots, client=client)
    assert out["source"] == "fallback"
    assert out["params"]["vehicle_type"] == "disabled"
    assert out["result"]["spot"]["type"] == "disabled"


def test_keyword_fallback_when_llm_errors():
    # LLM hata fırlatırsa sistem yine de çalışmalı (yedeğe düşer)
    spots = _spots_with_free({"A-10", "C-12"})
    client = FakeClient(raise_on_call=True)
    out = orchestrator.handle_request("şarjlı bir yer istiyorum çıkışa yakın",
                                      spots=spots, client=client)
    assert out["source"] == "fallback"
    assert out["params"]["vehicle_type"] == "ev"
    assert out["params"]["preference"] == "nearest_exit"
    # explain de hata verir ama şablon cevap dönmeli (boş değil)
    assert out["reply"]


def test_no_spot_returns_polite_message():
    spots = _spots_with_free(set())   # hepsi dolu
    client = FakeClient(args={"vehicle_type": "normal", "preference": "any",
                              "needs_charging": False})
    out = orchestrator.handle_request("yer ver", spots=spots, client=client)
    assert out["result"] is None
    assert out["reply"]   # nazik bir mesaj olmalı


def test_duration_extracted_from_text_in_fallback():
    # LLM araç çağırmazsa metinden "2 saat" -> duration_hours=2 çıkarılmalı
    spots = _spots_with_free({"C-12"})
    client = FakeClient(args=None)
    out = orchestrator.handle_request("2 saat kalacağım", spots=spots, client=client)
    assert out["params"]["duration_hours"] == 2


def test_duration_backfilled_when_llm_omits_it():
    # LLM süreyi atlasa bile metindeki "5 saat" yedek çıkarımla doldurulmalı
    spots = _spots_with_free({"C-12"})
    client = FakeClient(args={"vehicle_type": "normal", "preference": "any",
                              "needs_charging": False})
    out = orchestrator.handle_request("5 saat kalacağım bir yer ver",
                                      spots=spots, client=client)
    assert out["params"]["duration_hours"] == 5


def test_far_from_exit_inverts_to_nearest_entrance():
    # "çıkışa uzak" = çıkıştan uzak = girişe yakın olmalı (yön tersine çevrilir)
    spots = _spots_with_free({"C-12"})
    client = FakeClient(args=None)   # keyword yedeği
    out = orchestrator.handle_request("çıkışa en uzak bir yer", spots=spots, client=client)
    assert out["params"]["preference"] == "nearest_entrance"


def test_avm_entrance_maps_to_nearest_mall():
    # REGRESYON: "AVM girişine yakın" otopark girişiyle KARIŞTIRILMAMALI -> nearest_mall
    spots = _spots_with_free({"C-12"})
    client = FakeClient(args=None)   # keyword yedeği
    out = orchestrator.handle_request("AVM girişine yakın bir yer", spots=spots, client=client)
    assert out["params"]["preference"] == "nearest_mall"
    # "otopark girişi" ise hâlâ nearest_entrance olmalı (karışmamalı)
    out2 = orchestrator.handle_request("otopark girişine yakın", spots=spots, client=client)
    assert out2["params"]["preference"] == "nearest_entrance"


def test_quota_error_falls_back_with_note():
    # LLM 429 (kota) verirse: keyword yedeği + cevapta nazik kota notu olmalı
    spots = _spots_with_free({"A-10"})

    class QuotaClient(LLMClient):
        def extract_tool_call(self, user_text):
            raise RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded")

        def explain(self, user_text, result, params):   # çağrılmamalı
            raise AssertionError("kota hatasında explain çağrılmamalı")

    out = orchestrator.handle_request("elektrikli yer", spots=spots, client=QuotaClient())
    assert out["source"] == "fallback"
    assert out["result"]["spot"]["type"] == "ev_charging"
    assert "kota" in out["reply"].lower()


def test_entrance_passed_through_to_allocator():
    # UI'dan gelen giriş seçimi sonucu etkilemeli (E-1 sol, E-24 sağ boş)
    spots = _spots_with_free({"E-1", "E-24"})
    client = FakeClient(args={"vehicle_type": "normal", "preference": "any",
                              "needs_charging": False})
    out = orchestrator.handle_request("yer ver", spots=spots, client=client,
                                      entrance=ENTRANCES[1])
    assert out["result"]["spot_id"] == "E-24"
    assert out["result"]["path"][0] == ENTRANCES[1]


def test_ev_request_notes_when_no_charging_spot_free():
    # REGRESYON (bug #1): boş şarjlı yer yokken EV istenirse, LLM modunda dahi cevap
    # dürüstçe "boş şarjlı yer kalmadı" demeli ve normal yer vermeli (sessizce değil).
    spots = _spots_with_free({"C-12"})   # yalnız normal C-12 boş; tüm EV/engelli dolu
    client = FakeClient(args={"vehicle_type": "ev", "preference": "any",
                              "needs_charging": True})
    out = orchestrator.handle_request("elektrikli arabam var", spots=spots, client=client)
    assert out["result"]["spot"]["type"] == "normal"      # EV yok -> normal verildi
    assert "şarjlı yer kalmadı" in out["reply"].lower()   # ama dürüstçe belirtildi


def test_direct_spot_request_keyword():
    # "D-34'e yerleştir" -> metinden D-34 çıkarılıp (LLM yokken) oraya yerleşmeli
    spots = _spots_with_free({"D-34", "E-27"})
    client = FakeClient(args=None)                        # keyword yedeği
    out = orchestrator.handle_request("beni D-34 e yerleştir", spots=spots, client=client)
    assert out["result"]["spot_id"] == "D-34"
    assert out["result"]["requested_status"] == "ok"
    assert "D-34" in out["reply"]


def test_direct_spot_request_llm_arg():
    # LLM spot_id="A-7" döndürürse o yer (boşsa) verilmeli
    spots = _spots_with_free({"A-7", "E-27"})
    client = FakeClient(args={"vehicle_type": "normal", "preference": "any",
                              "needs_charging": False, "spot_id": "A-7"})
    out = orchestrator.handle_request("A-7 olsun", spots=spots, client=client)
    assert out["result"]["spot_id"] == "A-7"
    assert out["result"]["requested_status"] == "ok"

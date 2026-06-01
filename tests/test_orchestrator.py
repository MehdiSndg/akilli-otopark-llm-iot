"""
test_orchestrator.py — LLM orchestrator testleri.

LLM çağrısı mock'lanır (gerçek API/ağ gerekmez). Örnek cümlelerin doğru
parametrelere çözülmesi, varsayılana düşme ve keyword yedeği test edilir.
"""

from algorithm.graph import build_parking
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

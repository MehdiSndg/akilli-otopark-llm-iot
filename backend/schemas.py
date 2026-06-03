"""
schemas.py — Pydantic veri doğrulama şemaları (mühendislik olgunluğu).

Sisteme dışarıdan giren iki veri akışı şema ile doğrulanır; "bozuk veri sisteme
girmeden yakalanır":

  1. MQTT sensör mesajları (doluluk / sağlık / ağ geçidi) — alan/tip hatalıysa
     mesaj reddedilir (sessizce atlanmaz, loglanır).
  2. LLM'in döndürdüğü parametreler — geçersiz enum/tip makul varsayılana
     çekilir (graceful degradation: sistem yine de çalışır).

Aynı Pydantic, FastAPI istek gövdelerini de doğrular (server.py'deki modeller).
"""

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from llm import tools


# ---------------------------------------------------------------------------
# MQTT sensör mesajları — KATI doğrulama (bozuk veri reddedilir)
# ---------------------------------------------------------------------------
class SpotMessage(BaseModel):
    """otopark/spots/<bölüm>/<id> doluluk mesajı."""
    spot_id: str
    occupied: bool
    ts: Optional[float] = None

    @field_validator("spot_id")
    @classmethod
    def _non_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("spot_id boş olamaz")
        return v


class HealthMessage(BaseModel):
    """otopark/health/<id> sensör sağlık telemetrisi."""
    battery: float = Field(ge=0, le=100)
    rssi: int = Field(ge=-120, le=0)
    online: bool = True
    ts: Optional[float] = None


class GatewayMessage(BaseModel):
    """otopark/gateway/status ağ geçidi durumu (LWT)."""
    status: str
    ts: Optional[float] = None

    @field_validator("status")
    @classmethod
    def _known(cls, v):
        if v not in ("online", "offline"):
            raise ValueError(f"bilinmeyen status: {v}")
        return v


# ---------------------------------------------------------------------------
# LLM parametreleri — YUMUŞAK doğrulama (geçersiz -> varsayılan, sistem çalışsın)
# ---------------------------------------------------------------------------
class ParkingParams(BaseModel):
    """find_best_parking_spot için doğrulanmış sürücü parametreleri.

    Geçersiz enum/tip değerleri hata fırlatmaz; makul varsayılana çekilir
    (LLM zaman zaman uydurma değer döndürebilir — sistem buna dayanıklı olmalı).
    """
    vehicle_type: str = "normal"
    preference: str = "any"
    needs_charging: bool = False
    duration_hours: Optional[int] = None

    @field_validator("vehicle_type")
    @classmethod
    def _vt(cls, v):
        v = str(v).lower()
        return v if v in tools.VEHICLE_TYPES else "normal"

    @field_validator("preference")
    @classmethod
    def _pref(cls, v):
        v = str(v).lower()
        return v if v in tools.PREFERENCES else "any"

    @field_validator("duration_hours", mode="before")
    @classmethod
    def _dur(cls, v):
        if v is None:
            return None
        try:
            h = int(round(float(v)))
        except (TypeError, ValueError):
            return None
        return h if h > 0 else None

    def model_post_init(self, __context):
        # Tutarlılık: elektrikli araç şarj ister sayılır
        if self.vehicle_type == "ev":
            object.__setattr__(self, "needs_charging", True)


def parse_params(args):
    """Ham LLM argümanlarını doğrulanmış parametre dict'ine çevir (her zaman geçerli)."""
    data = dict(args or {})
    data.setdefault("vehicle_type", "normal")
    data.setdefault("preference", "any")
    data.setdefault("needs_charging", False)
    return ParkingParams(**data).model_dump()

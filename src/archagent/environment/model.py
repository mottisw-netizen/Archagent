"""The environmental semantic model (Petah Tikva spec §17).

Environmental requirements are not all drawing requirements (§16): some are
geometric (EV charging infrastructure at every parking space), some are pure
evidence (an acoustic report), and some are post-construction-only and cannot
be resolved during design by editing the model at all. These dataclasses give
each kind of environmental fact its own shape rather than one generic
"environmental note".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Serialisable


@dataclass
class AcousticZone(Serialisable):
    zone_id: str
    noise_sources: list[str] = field(default_factory=list)
    sensitive_rooms: list[str] = field(default_factory=list)


@dataclass
class NoiseSource(Serialisable):
    source_id: str
    kind: str = ""  # traffic | mechanical | construction


@dataclass
class SensitiveRoom(Serialisable):
    room_id: str
    room_type: str = "living_room"  # living_room | bedroom
    faces: list[str] = field(default_factory=list)


@dataclass
class AirEmissionSource(Serialisable):
    source_id: str
    kind: str = ""  # parking_ventilation | generator | commercial


@dataclass
class ParkingVentilation(Serialisable):
    source_id: str
    serves_level: str = ""


@dataclass
class Generator(Serialisable):
    source_id: str
    fuel: str = ""


@dataclass
class CommercialEmissionSource(Serialisable):
    source_id: str
    use: str = ""


@dataclass
class AirQualityAssessment(Serialisable):
    document: str = ""
    covered_sources: list[str] = field(default_factory=list)


@dataclass
class RadiationSource(Serialisable):
    source_id: str
    kind: str = ""


@dataclass
class RadiationMeasurement(Serialisable):
    measurement_id: str
    category: str = ""  # background | future_forecast | shielding
    value: float | None = None
    unit: str = ""


@dataclass
class RadiationReport(Serialisable):
    document: str = ""
    has_background_measurement: bool = False
    has_future_forecast: bool = False
    has_shielding_detail: bool = False


@dataclass
class ShieldingElement(Serialisable):
    element_id: str
    material: str = ""
    thickness: float | None = None


@dataclass
class AsbestosArea(Serialisable):
    area_id: str
    status: str = "unsurveyed"  # unsurveyed | surveyed | removed


@dataclass
class AsbestosSurvey(Serialisable):
    document: str = ""
    surveyed_by: str = ""
    areas: list[str] = field(default_factory=list)


@dataclass
class GreenBuildingRequirement(Serialisable):
    standard: str = "ת\"י 5281"
    certification_body: str = ""
    required_stage: str = "completion"


@dataclass
class EVChargingPoint(Serialisable):
    point_id: str
    serves_space: str = ""


@dataclass
class ConstructionNoiseSource(Serialisable):
    source_id: str
    activity: str = ""

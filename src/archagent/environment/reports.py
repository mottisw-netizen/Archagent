"""Environmental checks drawn directly from the spec §17 test examples.

Each function answers one of the record's own examples: no living-room
window facing the ramp, the air-quality assessment actually covering parking
+ generator + commercial sources, the radiation report actually containing
background + forecast + shielding, EV infrastructure actually reaching every
parking space. None of these invent a legal threshold - they check coverage
and presence, exactly what the supplied evidence says.
"""

from __future__ import annotations

from .model import (
    AirEmissionSource,
    AirQualityAssessment,
    EVChargingPoint,
    RadiationReport,
    SensitiveRoom,
)


def validate_no_sensitive_room_faces_ramp(rooms: list[SensitiveRoom]) -> list[str]:
    return [f"{room.room_id} ({room.room_type}) has a window facing the ramp"
           for room in rooms if "ramp" in room.faces]


def validate_air_quality_coverage(assessment: AirQualityAssessment,
                                  sources: list[AirEmissionSource]) -> list[str]:
    required_kinds = {source.kind for source in sources if source.kind}
    covered = set(assessment.covered_sources)
    missing = sorted(required_kinds - covered)
    return [f"the air-quality assessment does not cover {kind}" for kind in missing]


def validate_radiation_report_completeness(report: RadiationReport) -> list[str]:
    issues = []
    if not report.has_background_measurement:
        issues.append("the radiation report is missing a background measurement")
    if not report.has_future_forecast:
        issues.append("the radiation report is missing a future-construction forecast")
    if not report.has_shielding_detail:
        issues.append("the radiation report is missing a shielding detail")
    return issues


def validate_ev_charging_covers_all_parking(parking_space_ids: list[str],
                                            points: list[EVChargingPoint]) -> list[str]:
    served = {point.serves_space for point in points}
    return [f"{space} has no EV charging infrastructure" for space in parking_space_ids
           if space not in served]

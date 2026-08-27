"""Environmental semantic model checks (Petah Tikva spec §17)."""

from __future__ import annotations

from archagent.environment import (
    AirEmissionSource,
    AirQualityAssessment,
    EVChargingPoint,
    RadiationReport,
    SensitiveRoom,
    validate_air_quality_coverage,
    validate_ev_charging_covers_all_parking,
    validate_no_sensitive_room_faces_ramp,
    validate_radiation_report_completeness,
)


def test_no_living_room_windows_toward_ramp():
    rooms = [SensitiveRoom("R-1", "living_room", faces=["courtyard"]),
             SensitiveRoom("R-2", "living_room", faces=["ramp", "street"])]
    issues = validate_no_sensitive_room_faces_ramp(rooms)
    assert issues == ["R-2 (living_room) has a window facing the ramp"]


def test_air_quality_assessment_must_cover_parking_generator_and_commercial():
    sources = [AirEmissionSource("S-1", "parking_ventilation"),
              AirEmissionSource("S-2", "generator"),
              AirEmissionSource("S-3", "commercial")]
    assessment = AirQualityAssessment(covered_sources=["parking_ventilation"])
    issues = validate_air_quality_coverage(assessment, sources)
    assert "the air-quality assessment does not cover generator" in issues
    assert "the air-quality assessment does not cover commercial" in issues

    full = AirQualityAssessment(covered_sources=["parking_ventilation", "generator", "commercial"])
    assert validate_air_quality_coverage(full, sources) == []


def test_radiation_report_requires_background_forecast_and_shielding():
    incomplete = RadiationReport(has_background_measurement=True)
    issues = validate_radiation_report_completeness(incomplete)
    assert len(issues) == 2
    complete = RadiationReport(has_background_measurement=True, has_future_forecast=True,
                               has_shielding_detail=True)
    assert validate_radiation_report_completeness(complete) == []


def test_ev_charging_must_cover_every_parking_space():
    points = [EVChargingPoint("EV-1", serves_space="P-1")]
    issues = validate_ev_charging_covers_all_parking(["P-1", "P-2", "P-3"], points)
    assert issues == ["P-2 has no EV charging infrastructure",
                      "P-3 has no EV charging infrastructure"]

"""External infrastructure requirement model (spec §31)."""

from __future__ import annotations

from archagent.infrastructure import ExternalInfrastructureRequirement, needs_owner_approval


def test_generic_record_covers_any_asset_owner_without_a_bespoke_class():
    power_line = ExternalInfrastructureRequirement(
        requirement_id="REQ-1", asset_type="power_line", owner="Israel Electric Corporation",
        action="relocate", relocation=True)
    telecom = ExternalInfrastructureRequirement(
        requirement_id="REQ-2", asset_type="telecom_cabinet", owner="Bezeq", action="protect")
    assert power_line.owner != telecom.owner
    assert needs_owner_approval(power_line) is True
    assert needs_owner_approval(telecom) is False


def test_burial_also_requires_owner_approval():
    buried = ExternalInfrastructureRequirement(
        requirement_id="REQ-3", asset_type="power_line", burial=True)
    assert needs_owner_approval(buried) is True

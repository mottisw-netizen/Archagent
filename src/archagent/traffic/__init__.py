"""The traffic semantic model (Petah Tikva spec §6-8): parking, turning
paths and clearances as their own objects, distinct from generic dimensions."""

from .clearance import ClearanceReport, ClearanceViolation, check_clearances, point_to_segment_distance
from .model import DriveAisle, ParkingBalance, ParkingSpace, Ramp, TurningPath
from .parking import BalanceReconciliation, SpaceValidation, reconcile_balance, validate_space
from .ramp import RampValidation, effective_slope, validate_ramp_slope
from .turning import TurningValidation, turning_path_points, validate_turning_path

__all__ = [
    "BalanceReconciliation", "ClearanceReport", "ClearanceViolation", "DriveAisle",
    "ParkingBalance", "ParkingSpace", "Ramp", "RampValidation", "SpaceValidation",
    "TurningPath", "TurningValidation", "check_clearances", "effective_slope",
    "point_to_segment_distance", "reconcile_balance", "turning_path_points",
    "validate_ramp_slope", "validate_space", "validate_turning_path",
]

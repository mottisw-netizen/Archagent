"""archagent - AI municipal permit drawing review and correction agent.

The package implements the pipeline specified in
``.claude/skills/municipal-permit-review/SKILL.md``:

    ingest → analyse comments → extract constraints → analyse the drawing →
    map comments to elements → dependency graph → plan → simulate →
    consult → execute → validate → preview → report

Typical use::

    from archagent import Orchestrator

    result = Orchestrator("/path/to/project", mode="consultation").run()
    print(result.report)
"""

from .comments import CommentAnalyzer
from .constraints import ConstraintLedger
from .consult import ConsultationAgent, ScriptedResponder
from .drawing.api import DrawingDriver
from .drawing.json_model import JSONModelDriver
from .execute import ExecutionAgent
from .models import (
    CommentStatus,
    Constraint,
    CorrectionPlan,
    Mode,
    MunicipalComment,
    Priority,
    ProjectContext,
    ValidationResult,
)
from .orchestrator import Orchestrator, RunResult
from .planner import Planner
from .validate import ValidationAgent
from .versioning import VersionStore

__version__ = "0.1.0"

__all__ = [
    "CommentAnalyzer",
    "CommentStatus",
    "Constraint",
    "ConstraintLedger",
    "ConsultationAgent",
    "CorrectionPlan",
    "DrawingDriver",
    "ExecutionAgent",
    "JSONModelDriver",
    "Mode",
    "MunicipalComment",
    "Orchestrator",
    "Planner",
    "Priority",
    "ProjectContext",
    "RunResult",
    "ScriptedResponder",
    "ValidationAgent",
    "ValidationResult",
    "VersionStore",
    "__version__",
]

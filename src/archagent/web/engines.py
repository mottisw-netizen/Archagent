"""The two ways a run can be executed.

``pipeline`` runs the agent in this process: fastest, and the only engine that
can stop and ask the architect a question mid-run.

``claude-code`` puts Claude Code in the driver's seat through the Claude Agent
SDK. Claude reads the project, decides what to do, and drives the same
deterministic pipeline through its command line - so every guarantee still
holds (only the execution agent writes, everything is simulated first, every
number is measured) while the reasoning is Claude's. The tool guard below is
what makes that safe: Claude may read the project and run ``archagent``, and
nothing else.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import shlex
import shutil
from pathlib import Path

from ..consult import Question
from ..lang.messages import Messages
from ..llm import client as llm_client
from ..orchestrator import Orchestrator
from ..payload import run_payload
from .runs import STEP_OF_EVENT, Run

REPO_ROOT = Path(__file__).resolve().parents[3]

#: The only shell commands Claude Code may run in this application.
ALLOWED_COMMAND = re.compile(r"^(?:archagent|python3?\s+-m\s+archagent)\b")
READ_ONLY_TOOLS = {"Read", "Glob", "Grep", "TodoWrite", "Skill"}

#: Audit event -> what a human should see, in Hebrew.
EVENT_TITLES = {
    "ingest": "נקראו קבצי הפרויקט",
    "language": "זוהתה שפת ההערות",
    "llm_enabled": "המודל חובר להרצה",
    "comment_extracted": "הערה פורשה",
    "conflict": "זוהתה סתירה בין אילוצים",
    "mapping": "אותרו האלמנטים בהערה",
    "baseline": "נמדד מצב הבסיס",
    "plan_generated": "נבנתה תוכנית תיקון",
    "plan_escalated": "ההערה הועברה להחלטה אנושית",
    "no_action_required": "ההערה אינה דורשת פעולה",
    "decision_recorded": "נרשמה החלטת המשתמש",
    "precondition_failed": "תנאי מקדים נכשל - התוכנית בוטלה",
    "api_call": "בוצע שינוי במודל",
    "api_error": "שגיאת ממשק - בוצע שחזור",
    "validation_result": "הסתיים אימות",
    "version_written": "נשמרה גרסה",
    "narrative": "נכתב תקציר הדוח",
    "llm_usage": "סיכום שימוש במודל",
    "run_complete": "ההרצה הושלמה",
}


class WebResponder:
    """Turns a consultation into a question the browser can answer."""

    def __init__(self, run: Run):
        self.run = run

    def __call__(self, question: Question) -> str:
        payload = {
            "comment_id": question.comment.comment_id,
            "department": question.comment.department,
            "title": f"{question.comment.comment_id} · {question.comment.department}",
            "comment_text": question.comment.original_text.strip(),
            "summary": question.comment.summary,
            "elements": list(question.mapping.selected),
            "proposal": question.plan.strategy,
            "consequences": question.consequences(),
            "alternatives": [
                {"letter": chr(ord("A") + index + 1), "strategy": alternative["strategy"]}
                for index, alternative in enumerate(question.plan.alternatives)
            ],
            "confidence": round(question.plan.confidence.value, 3),
            "reasons": list(question.plan.consultation_reasons),
            "markdown": question.render(),
        }
        return self.run.ask(payload)


class PipelineEngine:
    """The agent, in this process, with live consultation."""

    name = "pipeline"

    def run(self, run: Run, project_dir: Path) -> None:
        options = run.options
        llm = _build_llm(options)
        run.emit("step", "מתחיל הרצה", step="ingest",
                 engine=self.name, model=getattr(llm, "model", None))

        orchestrator = Orchestrator(
            project_dir,
            mode=options.get("mode", "consultation"),
            responder=WebResponder(run),
            threshold=float(options.get("threshold", 0.85)),
            language=options.get("language", "auto"),
            llm=llm,
            effort=options.get("effort"),
            on_event=lambda record: _emit_audit(run, record),
        )
        result = orchestrator.run()
        run.language = result.language
        run.finish(run_payload(result, orchestrator.m))


class ClaudeCodeEngine:
    """Claude Code drives the run through the Claude Agent SDK."""

    name = "claude-code"

    def __init__(self, model: str | None = None):
        self.model = model

    @staticmethod
    def available() -> tuple[bool, str]:
        """Both halves must be present: the SDK, and the Claude Code CLI."""
        if importlib.util.find_spec("claude_agent_sdk") is None:
            return False, "claude-agent-sdk is not installed"
        if not shutil.which("claude"):
            return False, "the claude CLI is not on PATH"
        return True, ""

    # ------------------------------------------------------------------
    def guard_for(self, run: Run, project_dir):
        """The permission callback: Claude may read this project and run archagent.

        This is the whole security model of the engine, so it is a named method
        with tests rather than a closure.  It only works because
        ``allowed_tools`` is empty - an entry there auto-approves a tool before
        the callback is consulted.
        """
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

        async def guard(tool: str, payload: dict, context=None) -> object:
            if tool in READ_ONLY_TOOLS:
                outside = _outside_paths(payload, project_dir)
                if outside:
                    run.emit("blocked", "קריאה מחוץ לפרויקט נחסמה",
                             detail=", ".join(outside), step="ingest")
                    return PermissionResultDeny(
                        behavior="deny",
                        message="Only files inside the project and this repository can be read.",
                        interrupt=False)
                return PermissionResultAllow(behavior="allow", updated_input=payload)
            if tool == "Bash":
                command = str(payload.get("command", "")).strip()
                if ALLOWED_COMMAND.match(command):
                    run.emit("tool", "מריץ", detail=command, step="execute", tool="Bash")
                    return PermissionResultAllow(behavior="allow", updated_input=payload)
                run.emit("blocked", "פקודה נחסמה", detail=command, step="execute")
                return PermissionResultDeny(
                    behavior="deny",
                    message=("This application only allows the `archagent` command. "
                             "Run the pipeline instead of editing files by hand."),
                    interrupt=False)
            run.emit("blocked", "כלי נחסם", detail=tool, step="execute")
            return PermissionResultDeny(
                behavior="deny",
                message=f"{tool} is not available in this application; use archagent.",
                interrupt=False)

        return guard

    def run(self, run: Run, project_dir: Path) -> None:
        ok, reason = self.available()
        if not ok:
            raise RuntimeError(reason)
        asyncio.run(self._drive(run, project_dir))

    async def _drive(self, run: Run, project_dir: Path) -> None:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ResultMessage,
            TextBlock,
            ThinkingBlock,
            ToolUseBlock,
            query,
        )

        options = run.options
        output_dir = Path(project_dir) / "output" / f"cc-{run.run_id}"

        guard = self.guard_for(run, project_dir)

        agent_options = ClaudeAgentOptions(
            cwd=str(REPO_ROOT),
            model=self.model or options.get("model") or None,
            effort=options.get("effort") or "high",
            permission_mode="default",
            # allowed_tools MUST stay empty: an entry that allows a whole tool
            # auto-approves it *before* can_use_tool runs, which would silently
            # bypass the guard below.  Everything goes through the callback.
            allowed_tools=[],
            disallowed_tools=["Write", "Edit", "NotebookEdit", "WebSearch", "WebFetch"],
            can_use_tool=guard,
            setting_sources=["project"],
            skills=["municipal-permit-review"],
            max_turns=int(options.get("max_turns", 24)),
            system_prompt=SYSTEM_PROMPT,
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        )

        prompt = _claude_prompt(project_dir, output_dir, options)
        run.emit("step", "Claude Code מתחיל לעבוד", step="ingest", engine=self.name)

        try:
            async for message in query(prompt=prompt, options=agent_options):
                if run.cancelled:
                    break
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock) and block.text.strip():
                            run.emit("claude", "Claude", detail=block.text.strip(),
                                     step="plan")
                        elif isinstance(block, ThinkingBlock):
                            run.emit("thinking", "חושב…", step="plan")
                        elif isinstance(block, ToolUseBlock):
                            run.emit("tool", block.name,
                                     detail=_describe_tool(block.name, block.input),
                                     step="execute", tool=block.name)
                elif isinstance(message, ResultMessage):
                    run.emit("claude_result", "Claude Code סיים",
                             detail=(message.result or "")[:2000], step="report",
                             cost_usd=message.total_cost_usd, turns=message.num_turns,
                             is_error=message.is_error)
        except Exception as error:
            raise RuntimeError(f"Claude Code failed: {error}") from error

        payload = _latest_payload(project_dir)
        if payload is None:
            raise RuntimeError("Claude Code finished without producing a run payload; "
                               "see the transcript above")
        run.language = payload.get("language", "he")
        run.finish(payload)


SYSTEM_PROMPT = """\
You are operating inside Archagent, a municipal permit drawing review product.

The deterministic pipeline in this repository is the product. Your job is to
drive it and to explain what happened - not to edit drawings yourself.

Rules of this environment:
- The only shell command available to you is `archagent` (the project CLI).
  Every other command is blocked, and file editing tools are disabled.
- Never edit a project model, a report or a comment file by hand.
- Report honestly: if comments were left unresolved or the validation failed,
  say so plainly and say what a human has to decide.
- Answer in the language of the municipal comments (usually Hebrew).
"""


def _claude_prompt(project_dir: Path, output_dir: Path, options: dict) -> str:
    mode = options.get("mode", "consultation")
    language = options.get("language", "auto")
    responder = "defer" if mode == "consultation" else "auto"
    command = (f"archagent run {shlex.quote(str(project_dir))} --mode {mode} "
               f"--lang {language} --responder {responder} "
               f"--output {shlex.quote(str(output_dir))}")
    if options.get("no_llm"):
        command += " --no-llm"
    return f"""\
Review the municipal permit comments for the project at `{project_dir}` and
correct the drawing.

1. Look at what the project contains (`{project_dir}`) - the comments, the
   constraints and the source model.
2. Run the pipeline:

   {command}

3. Read the correction report it produced under `{output_dir}` and tell the
   architect, in the language of the comments: what was corrected, what is
   still open and what needs their decision. Be specific - name the comments.

Do not edit any file yourself. If the command fails, report the failure.
"""


def _outside_paths(payload: dict, project_dir) -> list[str]:
    """Paths in a read request that leave the project or the repository."""
    roots = [Path(project_dir).resolve(), REPO_ROOT.resolve()]
    outside = []
    for key in ("file_path", "path", "notebook_path"):
        value = payload.get(key)
        if not value:
            continue
        candidate = Path(str(value))
        if not candidate.is_absolute():
            continue
        resolved = candidate.resolve()
        if not any(resolved == root or root in resolved.parents for root in roots):
            outside.append(str(value))
    return outside


def _describe_tool(name: str, payload: dict) -> str:
    if name == "Bash":
        return str(payload.get("command", ""))[:300]
    if name in ("Read", "Glob", "Grep"):
        return str(payload.get("file_path") or payload.get("pattern") or "")[:200]
    return json.dumps(payload, ensure_ascii=False)[:200]


def _latest_payload(project_dir: Path) -> dict | None:
    candidates = sorted((Path(project_dir) / "output").glob("*/run_payload.json"),
                        key=lambda path: path.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
    return None


def _emit_audit(run: Run, record: dict) -> None:
    event = record.get("event", "")
    title = EVENT_TITLES.get(event, event.replace("_", " "))
    detail = record.get("result")
    if isinstance(detail, (dict, list)):
        detail = json.dumps(detail, ensure_ascii=False)[:300]
    params = record.get("params") or {}
    if event == "comment_extracted":
        detail = f"{params.get('comment_id', '')}: {detail}"
    elif event == "mapping":
        detail = f"{params.get('comment_id', '')} → {detail}"
    elif event == "api_call":
        detail = (f"{params.get('element_id', '')}.{params.get('property', '')}: "
                  f"{_value(record.get('before'))} → {_value(record.get('after'))}")
    run.emit("audit", title, detail=str(detail or ""), step=STEP_OF_EVENT.get(event, ""),
             event=event, actor=record.get("actor", ""))


def _value(value) -> str:
    """Format a change value for a human reading the live stream."""
    if isinstance(value, dict) and {"x", "y", "w", "h"} <= set(value):
        return "(" + ", ".join(f"{value[key]:.2f}" for key in ("x", "y", "w", "h")) + ")"
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, list):
        return f"{len(value)} שורות"
    return str(value)


def _build_llm(options: dict):
    if options.get("no_llm"):
        return None
    return llm_client.from_env(model=options.get("model"), effort=options.get("effort"),
                               cache_dir=options.get("llm_cache"))


ENGINES = {"pipeline": PipelineEngine, "claude-code": ClaudeCodeEngine}


def build_engine(name: str, options: dict):
    engine = ENGINES.get(name)
    if engine is None:
        raise KeyError(name)
    if name == "claude-code":
        return ClaudeCodeEngine(model=options.get("model"))
    return PipelineEngine()


def messages_for(language: str) -> Messages:
    return Messages(language if language in ("he", "en") else "he")

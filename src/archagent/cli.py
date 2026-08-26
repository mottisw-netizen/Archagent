"""Command line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import units
from .comments import CommentAnalyzer
from .llm import client as llm_client
from .llm.interpret import LLMCommentInterpreter
from .constraints import ConstraintLedger, constraints_from_document
from .consult import ScriptedResponder, auto_approve, cli_responder, defer
from .drawing.json_model import JSONModelDriver
from .ingest import Ingestor
from .orchestrator import Orchestrator


def _llm(args: argparse.Namespace):
    """Build the Claude client unless the user asked for rules only."""
    if getattr(args, "no_llm", False):
        return None
    required = bool(getattr(args, "llm", False))
    client = llm_client.from_env(model=getattr(args, "model", None),
                                 effort=getattr(args, "effort", None),
                                 cache_dir=getattr(args, "llm_cache", None),
                                 required=required)
    if client is None and required:
        raise SystemExit("no Anthropic credentials found: set ANTHROPIC_API_KEY "
                         "or run `ant auth login`")
    if client is None:
        print("! no Anthropic credentials found - falling back to the rule parser "
              "(pass --no-llm to silence this)", file=sys.stderr)
    return client


def _responder(name: str, answers: str | None):
    if answers:
        return ScriptedResponder.from_file(answers)
    return {"auto": auto_approve, "ask": cli_responder, "defer": defer}[name]


def cmd_run(args: argparse.Namespace) -> int:
    orchestrator = Orchestrator(
        args.project, mode=args.mode, threshold=args.threshold,
        responder=_responder(args.responder, args.answers), output_dir=args.output,
        llm=_llm(args), language=args.lang, effort=args.effort,
        sources=args.source,
    )
    result = orchestrator.run()
    validation = result.validation
    print(f"run {result.context.run_id}  mode={args.mode}  "
          f"{result.parent_version or 'original'} -> {result.version or 'markup'}")
    print()
    counts: dict[str, int] = {}
    for item in validation.comments:
        counts[item.status.value] = counts.get(item.status.value, 0) + 1
    width = max((len(key) for key in counts), default=0)
    for status, count in counts.items():
        print(f"  {status:<{width}}  {count}")
    print()
    if result.llm:
        usage = result.llm.get("usage", {})
        tokens = ", ".join(f"{k.replace('_tokens', '')} {v:,}" for k, v in sorted(usage.items()))
        print(f"  model           : {result.llm['model']} "
              f"({result.llm['calls']} calls{', ' + tokens if tokens else ''})")
        for failure in result.llm.get("failures", []):
            print(f"      ! {failure}")
    else:
        print("  model           : none (deterministic parser only)")
    print(f"  language        : {result.language}")
    print(f"  changes applied : {len(result.changes)}")
    print(f"  validation      : {validation.result}")
    print(f"  open items      : {len(result.context.open_items)}")
    unmet = [text for text, ok in result.definition_of_done if not ok]
    print(f"  definition of done: {'complete' if not unmet else str(len(unmet)) + ' unmet'}")
    for text in unmet:
        print(f"      - {text}")
    if result.files:
        print()
        for name, path in sorted(result.files.items()):
            print(f"  {name}: {path}")
    return 0 if validation.result != "failed" else 1


def cmd_comments(args: argparse.Namespace) -> int:
    ingestor = Ingestor(args.project)
    manifest = ingestor.scan()
    client = _llm(args)
    analyzer = CommentAnalyzer(
        interpreter=LLMCommentInterpreter(client, effort=args.effort) if client else None)
    rows = []
    for entry in manifest:
        if entry.role != "municipal_comments":
            continue
        text = ingestor.text_of(entry)
        if not text:
            print(f"! {entry.file}: {entry.notes}", file=sys.stderr)
            continue
        for comment in analyzer.analyze_document(text, source_ref=Path(entry.file).name):
            rows.append((comment.comment_id, comment.department,
                         comment.summary or comment.normalized_requirement
                         or comment.required_action,
                         f"{comment.confidence.value:.2f}"))
    if args.json:
        print(json.dumps([dict(zip(("id", "department", "requirement", "confidence"), row))
                          for row in rows], indent=2, ensure_ascii=False))
        return 0
    for row in rows:
        print(f"{row[0]:<8} {row[1]:<14} {row[2]:<50} {row[3]}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    driver = JSONModelDriver.load(args.model)
    ledger = ConstraintLedger()
    analyzer = CommentAnalyzer()
    for path in args.constraints:
        constraints_from_document(Path(path).read_text(encoding="utf-8"),
                                  "Zoning Plan" if "zoning" in Path(path).name else
                                  "Project Requirement", Path(path).name, ledger, analyzer)
    failures = 0
    for result in ledger.evaluate(driver):
        measured = (units.format_value(result.measured, result.unit, result.op)
                    if result.measured is not None else "-")
        required = (units.format_value(result.required, result.unit)
                    if result.required is not None else "-")
        marker = {"pass": "ok  ", "fail": "FAIL", "not_evaluated": "?   "}[result.status]
        failures += result.status == "fail"
        print(f"{marker} {result.constraint_id:<7} {result.rule:<52} "
              f"{measured:>10} {result.op} {required}")
    return 1 if failures else 0


def _add_llm_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--llm", action="store_true",
                       help="require Claude; fail if no credentials are configured")
    group.add_argument("--no-llm", action="store_true",
                       help="use the deterministic parser only")
    parser.add_argument("--model", default=None,
                        help=f"model id (default: {llm_client.DEFAULT_MODEL})")
    parser.add_argument("--effort", choices=("low", "medium", "high", "xhigh", "max"),
                        default=None, help=f"reasoning effort (default: {llm_client.DEFAULT_EFFORT})")
    parser.add_argument("--llm-cache", default=None, metavar="DIR",
                        help="cache model answers on disk, so a re-run costs nothing")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="archagent",
        description="AI municipal permit drawing review and correction agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="run the full review and correction pipeline")
    run.add_argument("project", help="project directory")
    run.add_argument("--mode", choices=("consultation", "autonomous"), default="consultation")
    run.add_argument("--responder", choices=("ask", "auto", "defer"), default="defer",
                     help="how consultation questions are answered")
    run.add_argument("--answers", help="JSON file of scripted answers keyed by comment id")
    run.add_argument("--threshold", type=float, default=0.85)
    run.add_argument("--output", help="output directory")
    run.add_argument("--lang", choices=("auto", "he", "en"), default="auto",
                     help="report language (default: the language of the comments)")
    run.add_argument("--source", action="append", default=[], metavar="REF",
                     help="a drawing to work on: a file path, or a live CAD host "
                          "such as revit://127.0.0.1:8735 (repeatable)")
    _add_llm_arguments(run)
    run.set_defaults(func=cmd_run)

    comments = subparsers.add_parser("comments", help="show how the comments are interpreted")
    comments.add_argument("project")
    comments.add_argument("--json", action="store_true")
    _add_llm_arguments(comments)
    comments.set_defaults(func=cmd_comments)

    validate = subparsers.add_parser("validate", help="measure a model against constraint files")
    validate.add_argument("model")
    validate.add_argument("constraints", nargs="+")
    validate.set_defaults(func=cmd_validate)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

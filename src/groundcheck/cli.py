"""groundcheck CLI. The interface is the one from §5 of the spec."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .adapter import build_adapter
from .diff import DiffError, diff_runs
from .diff import render as render_diff
from .gate import DEFAULT_MAX_REGRESSION, GateError, compare
from .gate import render as render_gate
from .report import ReportError, aggregate, load_run, render, resolve_suite
from .run import run_suite, write_run
from .suite import SuiteError, load_suite

# Subcommands specified but not implemented yet. They are declared with the milestone
# that brings them so `groundcheck --help` reflects the real state of the project, not a promise.
PENDING: dict[str, str] = {}


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        suite = load_suite(args.suite)
    except SuiteError as exc:
        print(f"invalid suite — {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"could not read the suite: {exc}", file=sys.stderr)
        return 2

    try:
        adapter = build_adapter(args.system, timeout=args.timeout, mapping=args.mapping)
    except (ValueError, OSError) as exc:
        print(f"invalid system — {exc}", file=sys.stderr)
        return 2

    def progress(obs) -> None:
        if args.quiet:
            return
        mark = "!" if obs.error else ("-" if obs.response and obs.response.abstained else "ok")
        print(f"  {mark:>2}  {obs.case_id}  [{obs.category}]", file=sys.stderr)

    record = run_suite(suite, adapter, on_case=progress)

    if args.out:
        path = write_run(record, args.out)
        if not args.quiet:
            errors = sum(1 for o in record.observations if o.error)
            print(
                f"\n{record.suite['case_count']} cases · {errors} with errors · suite sha256 "
                f"{suite.sha256[:12]}\nrun → {path}",
                file=sys.stderr,
            )
    else:
        json.dump(record.to_json_dict(), sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    try:
        run = load_run(args.run)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"could not read the run: {exc}", file=sys.stderr)
        return 2
    try:
        suite = resolve_suite(run, suite_path=args.suite)
        rows = aggregate(run, suite, k=args.k)
    except ReportError as exc:
        print(f"cannot report — {exc}", file=sys.stderr)
        return 2
    except SuiteError as exc:
        print(f"invalid suite — {exc}", file=sys.stderr)
        return 2

    payload = _report_payload(rows, run, args.k)
    if args.json:
        json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        print(render(run, rows, k=args.k))
    return 0


def _report_payload(rows, run, k):
    return {
        "suite": run["suite"],
        "system": run["system"],
        "k": k,
        "categories": {
            cat: {
                "n": f.n,
                "errors": f.errors,
                f"recall_at_{k}": None if cat == "negative_control" else _mean(f.recall),
                "mrr": None if cat == "negative_control" else _mean(f.rr),
                f"precision_at_{k}": None if cat == "negative_control" else _mean(f.precision),
                "checks": {
                    n: {
                        "passed": r.hits,
                        "verifiable": r.n_verifiable,
                        "total": r.n_total,
                        "rate": r.value,
                    }
                    for n, r in sorted(f.checks.items())
                    if r.n_total
                },
            }
            for cat, f in rows.items()
        },
    }


def _mean(values):
    from .metrics import mean

    return mean(values)


def _cmd_gate(args: argparse.Namespace) -> int:
    """Returns 0 on pass, 1 on regression (fails the build), 2 if it could not compare."""
    try:
        baseline = json.loads(Path(args.against).read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"could not read the baseline: {exc}", file=sys.stderr)
        return 2

    current = _payload_from(args.run, args.suite, args.k)
    if isinstance(current, int):
        return current

    try:
        findings = compare(baseline, current, max_regression=args.max_regression)
    except GateError as exc:
        print(f"cannot compare — {exc}", file=sys.stderr)
        return 2

    print(render_gate(findings, max_regression=args.max_regression))
    return 1 if any(f.blocks for f in findings) else 0


def _cmd_diff(args: argparse.Namespace) -> int:
    try:
        before = load_run(args.before)
        after = load_run(args.after)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"could not read one of the runs: {exc}", file=sys.stderr)
        return 2
    try:
        suite = resolve_suite(after, suite_path=args.suite)
        flips, movement = diff_runs(before, after, suite, k=args.k)
    except (DiffError, ReportError) as exc:
        print(f"cannot compare — {exc}", file=sys.stderr)
        return 2
    except SuiteError as exc:
        print(f"invalid suite — {exc}", file=sys.stderr)
        return 2

    print(render_diff(before, after, flips, movement, suite, k=args.k))
    return 0


def _payload_from(run_path: str, suite_path: str | None, k: int):
    """Loads a run and returns its JSON report, or an exit code on failure."""
    try:
        run = load_run(run_path)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"could not read the run: {exc}", file=sys.stderr)
        return 2
    try:
        suite = resolve_suite(run, suite_path=suite_path)
        rows = aggregate(run, suite, k=k)
    except ReportError as exc:
        print(f"cannot report — {exc}", file=sys.stderr)
        return 2
    except SuiteError as exc:
        print(f"invalid suite — {exc}", file=sys.stderr)
        return 2
    return _report_payload(rows, run, k)


def _cmd_pending(name: str) -> int:
    print(f"`groundcheck {name}` does not exist yet — arrives in {PENDING[name]}", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="groundcheck",
        description="Evaluation harness for RAG systems. Measures retrieval, grounding, "
        "citations and abstention reproducibly.",
    )
    parser.add_argument("--version", action="version", version=f"groundcheck {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a suite against a system")
    run.add_argument("--suite", required=True, help="path to the golden set (YAML)")
    run.add_argument(
        "--system",
        required=True,
        help="`mock:file.yaml` for a scripted system, or the real endpoint URL",
    )
    run.add_argument("--out", help="directory to write the run to; without it, JSON goes to stdout")
    run.add_argument("--timeout", type=float, default=60.0, help="timeout per question (s)")
    run.add_argument("--mapping", help="YAML mapping the system response onto the contract")
    run.add_argument("--quiet", action="store_true", help="no progress on stderr")
    run.set_defaults(func=_cmd_run)

    report = sub.add_parser("report", help="report with a per-category breakdown")
    report.add_argument("run", help="JSON file of a run")
    report.add_argument("--suite", help="path to the suite if it moved since the run")
    report.add_argument("--k", type=int, default=5, help="k for recall@k and precision@k")
    report.add_argument("--json", action="store_true", help="JSON output instead of a table")
    report.set_defaults(func=_cmd_report)

    gate = sub.add_parser("gate", help="fails the build if a metric degraded")
    gate.add_argument("run", help="run to evaluate")
    gate.add_argument("--against", required=True, help="baseline (output of `report --json`)")
    gate.add_argument("--max-regression", type=float, default=DEFAULT_MAX_REGRESSION,
                      help=f"tolerated drop per metric (default {DEFAULT_MAX_REGRESSION})")
    gate.add_argument("--suite", help="path to the suite if it moved since the run")
    gate.add_argument("--k", type=int, default=5, help="must match the baseline")
    gate.set_defaults(func=_cmd_gate)

    diff = sub.add_parser("diff", help="compares two runs and names what moved")
    diff.add_argument("before", help="reference run")
    diff.add_argument("after", help="new run")
    diff.add_argument("--suite", help="ruta a la suite si se movio desde las corridas")
    diff.add_argument("--k", type=int, default=5)
    diff.set_defaults(func=_cmd_diff)

    for name, milestone in PENDING.items():
        p = sub.add_parser(name, help=f"[{milestone}]")
        p.add_argument("args", nargs="*")
        p.set_defaults(func=lambda a, _n=name: _cmd_pending(_n))

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

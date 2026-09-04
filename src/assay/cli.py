"""CLI de assay. La interfaz es la de §5 del contexto."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .adapter import build_adapter
from .report import ReportError, aggregate, load_run, render, resolve_suite
from .run import run_suite, write_run
from .suite import SuiteError, load_suite

# Subcomandos especificados pero todavia no implementados. Se declaran con el hito que
# los trae para que `assay --help` sea el estado real del proyecto y no una promesa.
PENDING = {
    "gate": "M5 — gate de CI que falla el build ante una regresion",
    "diff": "M6 — comparar dos corridas y nombrar la categoria que se movio",
}


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        suite = load_suite(args.suite)
    except SuiteError as exc:
        print(f"suite invalida — {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"no se pudo leer la suite: {exc}", file=sys.stderr)
        return 2

    try:
        adapter = build_adapter(args.system, timeout=args.timeout)
    except (ValueError, OSError) as exc:
        print(f"sistema invalido — {exc}", file=sys.stderr)
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
                f"\n{record.suite['case_count']} casos · {errors} con error · suite sha256 "
                f"{suite.sha256[:12]}\ncorrida → {path}",
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
        print(f"no se pudo leer la corrida: {exc}", file=sys.stderr)
        return 2
    try:
        suite = resolve_suite(run, suite_path=args.suite)
        filas = aggregate(run, suite, k=args.k)
    except ReportError as exc:
        print(f"no se puede reportar — {exc}", file=sys.stderr)
        return 2
    except SuiteError as exc:
        print(f"suite invalida — {exc}", file=sys.stderr)
        return 2

    if args.json:
        payload = {
            "suite": run["suite"],
            "system": run["system"],
            "k": args.k,
            "categories": {
                cat: {
                    "n": f.n,
                    "errors": f.errores,
                    f"recall_at_{args.k}": None if cat == "negative_control" else _mean(f.recall),
                    "mrr": None if cat == "negative_control" else _mean(f.rr),
                    f"precision_at_{args.k}": (
                        None if cat == "negative_control" else _mean(f.precision)
                    ),
                    "checks": {
                        n: {
                            "passed": r.aciertos,
                            "verifiable": r.n_verificable,
                            "total": r.n_total,
                            "rate": r.value,
                        }
                        for n, r in sorted(f.checks.items())
                        if r.n_total
                    },
                }
                for cat, f in filas.items()
            },
        }
        json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        print(render(run, filas, k=args.k))
    return 0


def _mean(values):
    from .metrics import mean

    return mean(values)


def _cmd_pending(name: str) -> int:
    print(f"`assay {name}` todavia no existe — llega en {PENDING[name]}", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assay",
        description="Harness de evals para sistemas RAG. Mide retrieval, fundamento, "
        "citas y abstencion de forma reproducible.",
    )
    parser.add_argument("--version", action="version", version=f"assay {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="correr una suite contra un sistema")
    run.add_argument("--suite", required=True, help="ruta al golden set (YAML)")
    run.add_argument(
        "--system",
        required=True,
        help="`mock:archivo.yaml` para un sistema guionado, o la URL del endpoint real",
    )
    run.add_argument("--out", help="directorio donde escribir la corrida; sin esto, JSON a stdout")
    run.add_argument("--timeout", type=float, default=60.0, help="timeout por pregunta (s)")
    run.add_argument("--quiet", action="store_true", help="sin progreso en stderr")
    run.set_defaults(func=_cmd_run)

    report = sub.add_parser("report", help="reporte con desglose por categoria")
    report.add_argument("run", help="archivo JSON de una corrida")
    report.add_argument("--suite", help="ruta a la suite si se movio desde la corrida")
    report.add_argument("--k", type=int, default=5, help="k de recall@k y precision@k")
    report.add_argument("--json", action="store_true", help="salida JSON en vez de tabla")
    report.set_defaults(func=_cmd_report)

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

"""Command line entry point (see specs/001-drum-stem-extraction/contracts/cli.md)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from poc.errors import PocError


def _cmd_separate(args: argparse.Namespace) -> int:
    from poc.evaluation.run import run_separation
    from poc.separation.demucs_adapter import DemucsSeparator

    run_dir = run_separation(
        args.audio_path,
        args.output_dir,
        DemucsSeparator(device=args.device, seed=args.seed),
        write_accompaniment=not args.no_accompaniment,
    )
    run = json.loads((run_dir / "run.json").read_text())
    for warning in run["warnings"]:
        print(f"warning: {warning['code']}: {warning['message']}", file=sys.stderr)
    print(run_dir.resolve())
    return 0


def _cmd_summarize(args: argparse.Namespace) -> int:
    from poc.evaluation.summary import summarize

    result = summarize(args.runs_dir, args.report_dir)
    for run_id in result.incomplete:
        print(f"skipped (evaluation.yaml not filled in): {run_id}", file=sys.stderr)
    print(result.markdown, end="")
    return 0


def _cmd_check_repro(args: argparse.Namespace) -> int:
    raise NotImplementedError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poc", description="AI Drum Practice Coach PoC tools")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("separate", help="separate one song into drum / accompaniment stems")
    p.add_argument("audio_path", type=Path)
    p.add_argument("--output-dir", type=Path, default=Path("output/runs"))
    p.add_argument("--device", choices=["auto", "mps", "cpu"], default="auto")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--no-accompaniment", action="store_true")
    p.set_defaults(func=_cmd_separate)

    p = sub.add_parser("summarize", help="aggregate filled-in evaluation sheets")
    p.add_argument("--runs-dir", type=Path, default=Path("output/runs"))
    p.add_argument("--report-dir", type=Path, default=Path("output/reports"))
    p.set_defaults(func=_cmd_summarize)

    p = sub.add_parser("check-repro", help="compare drum stems of two runs of the same input")
    p.add_argument("run_dir_a", type=Path)
    p.add_argument("run_dir_b", type=Path)
    p.add_argument("--tolerance", type=float, default=1e-4)
    p.set_defaults(func=_cmd_check_repro)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except PocError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    sys.exit(main())

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
    from poc.evaluation.repro import compare_runs

    diff, passed = compare_runs(args.run_dir_a, args.run_dir_b, args.tolerance)
    result = "PASS" if passed else "FAIL"
    print(f"max_abs_diff={diff:g} tolerance={args.tolerance:g} result={result}")
    return 0 if passed else 1


def _cmd_transcribe(args: argparse.Namespace) -> int:
    from poc.transcription.adtof_adapter import AdtofTranscriber, parse_thresholds
    from poc.transcription.run import run_transcription

    transcriber = AdtofTranscriber(thresholds=parse_thresholds(args.thresholds))
    out = run_transcription(args.poc1_run_dir, args.input, args.output_dir, transcriber)
    data = json.loads((out / "transcription.json").read_text())
    for warning in data["warnings"]:
        print(f"warning: {warning['code']}: {warning['message']}", file=sys.stderr)
    print(out.resolve())
    return 0


def _cmd_check_events(args: argparse.Namespace) -> int:
    from poc.transcription.run import compare_transcriptions

    n_a, n_b, mismatches, passed = compare_transcriptions(
        args.transcription_dir_a, args.transcription_dir_b
    )
    result = "PASS" if passed else "FAIL"
    print(f"events_a={n_a} events_b={n_b} mismatches={mismatches} result={result}")
    return 0 if passed else 1


def _cmd_record(args: argparse.Namespace) -> int:
    raise NotImplementedError


def _cmd_evaluate(args: argparse.Namespace) -> int:
    raise NotImplementedError


def _cmd_summarize_events(args: argparse.Namespace) -> int:
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

    # --- PoC 2 (specs/002-drum-event-extraction/contracts/cli.md) ---
    p = sub.add_parser("transcribe", help="extract drum events from a PoC 1 run")
    p.add_argument("poc1_run_dir", type=Path)
    p.add_argument("--input", choices=["drum_stem", "mix", "accompaniment"], default="drum_stem")
    p.add_argument("--output-dir", type=Path, default=Path("output/transcriptions"))
    p.add_argument("--thresholds", default="", help="e.g. kick=0.12,hihat=0.12")
    p.set_defaults(func=_cmd_transcribe)

    p = sub.add_parser("check-events", help="compare events of two transcriptions of one input")
    p.add_argument("transcription_dir_a", type=Path)
    p.add_argument("transcription_dir_b", type=Path)
    p.set_defaults(func=_cmd_check_events)

    p = sub.add_parser("record", help="record a TD-17 play-along (MIDI + drum audio)")
    p.add_argument("poc1_run_dir", type=Path, nargs="?")
    p.add_argument("--check", action="store_true", help="check loopback and pad note numbers")
    p.add_argument("--list-devices", action="store_true")
    p.add_argument("--device", default="TD-17")
    p.add_argument("--midi-port", default="TD-17")
    p.add_argument("--output-dir", type=Path, default=Path("output/recordings"))
    p.set_defaults(func=_cmd_record)

    p = sub.add_parser("evaluate", help="evaluate drum events against ground truth")
    p.add_argument("recording_dir", type=Path, nargs="?")
    p.add_argument("--annotation", type=Path)
    p.add_argument("--tolerance-ms", type=float, default=50.0)
    p.add_argument("--ghost-velocity", type=int, default=40)
    p.set_defaults(func=_cmd_evaluate)

    p = sub.add_parser("summarize-events", help="aggregate PoC 2 evaluations")
    p.add_argument("--evaluations-dir", type=Path, default=Path("output/evaluations"))
    p.add_argument("--report-dir", type=Path, default=Path("output/reports"))
    p.set_defaults(func=_cmd_summarize_events)

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

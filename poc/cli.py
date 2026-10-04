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
    from poc.errors import UserInputError
    from poc.recording.devices import describe_devices

    if args.list_devices:
        print(describe_devices())
        return 0
    if args.check:
        from poc.recording.check import run_check

        return 0 if run_check(args.device, args.midi_port) else 1
    if args.calibrate:
        from poc.recording.record import record_calibration

        out = record_calibration(args.device, args.midi_port, args.output_dir / "calibrations")
        print((out / "calibration.json").read_text(), file=sys.stderr)
        print(out.resolve())
        return 0
    if args.poc1_run_dir is None:
        raise UserInputError("give a PoC 1 run directory, --calibrate, --check, or --list-devices")
    if args.tap_beats:
        from poc.recording.record import record_beat_taps

        out = record_beat_taps(
            args.poc1_run_dir,
            args.device,
            args.midi_port,
            args.output_dir,
            max_seconds=args.max_seconds,
        )
        data = json.loads((out / "recording.json").read_text())
        print(
            f"beats={data['beats']} downbeats={data['downbeats']} notes={data['note_count']}",
            file=sys.stderr,
        )
        print(out.resolve())
        return 0
    from poc.recording.record import record_play_along

    out = record_play_along(
        args.poc1_run_dir,
        args.device,
        args.midi_port,
        args.output_dir,
        args.max_seconds,
        click=args.click,
    )
    data = json.loads((out / "recording.json").read_text())
    print(f"notes={data['note_count']} duration={data['duration_sec']:.1f}s", file=sys.stderr)
    print(out.resolve())
    return 0


def _print_evaluation(out: Path) -> None:
    data = json.loads((out / "evaluation.json").read_text())
    print(f"evaluation: {out.resolve()}", file=sys.stderr)
    for kind, result in data["results"].items():
        print(f"[{kind}]  instrument  P      R      F1     median|p95 ms", file=sys.stderr)
        for inst, m in result["metrics"].items():
            t = m["timing_ms"]
            cells = [m["precision"], m["recall"], m["f1"]]
            text = "  ".join("  -  " if v is None else f"{v:.3f}" for v in cells)
            timing = "-" if t["median_abs"] is None else f"{t['median_abs']:.1f}|{t['p95_abs']:.1f}"
            print(f"  {inst:8s}  {text}  {timing}", file=sys.stderr)
    if data.get("residual_drum_hits"):
        print(f"residual original drums: {data['residual_drum_hits']['counts']}", file=sys.stderr)


def _cmd_annotate(args: argparse.Namespace) -> int:
    from poc.evaluation.annotate import annotation_config, serve

    config = annotation_config(args.annotation_yaml, args.runs_dir, args.source, beats=args.beats)
    serve(config, port=args.port, open_browser=not args.no_browser)
    return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
    from poc.errors import UserInputError
    from poc.evaluation.events_eval import evaluate_annotation, evaluate_recording
    from poc.transcription.adtof_adapter import AdtofTranscriber, parse_thresholds

    transcriber = AdtofTranscriber(thresholds=parse_thresholds(args.thresholds))
    if args.annotation:
        out = evaluate_annotation(
            args.annotation, transcriber=transcriber, tolerance_ms=args.tolerance_ms
        )
    elif args.recording_dir:
        from poc.separation.demucs_adapter import DemucsSeparator

        out = evaluate_recording(
            args.recording_dir,
            separator=DemucsSeparator(),
            transcriber=transcriber,
            calibration_dir=args.calibration,
            tolerance_ms=args.tolerance_ms,
            ghost_velocity=args.ghost_velocity,
        )
    else:
        raise UserInputError("give a recording directory or --annotation")
    _print_evaluation(out)
    print(out.resolve())
    return 0


def _cmd_summarize_events(args: argparse.Namespace) -> int:
    from poc.evaluation.events_summary import summarize_events

    _, markdown = summarize_events(args.evaluations_dir, args.report_dir)
    print(markdown, end="")
    return 0


def _cmd_tune_thresholds(args: argparse.Namespace) -> int:
    from poc.evaluation.tuning import load_songs, report_markdown, tune
    from poc.transcription.adtof_adapter import AdtofTranscriber, events_from_activations

    transcriber = AdtofTranscriber()
    songs = load_songs(args.evaluations_dir, args.recordings_dir, transcriber.activations)

    def events_fn(activations, thresholds):
        return events_from_activations(activations, {**transcriber.thresholds, **thresholds})

    report = tune(songs, events_fn)
    markdown = report_markdown(report)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    (args.report_dir / "poc2_thresholds.md").write_text(markdown)
    (args.report_dir / "poc2_thresholds.json").write_text(json.dumps(report, indent=1) + "\n")
    print(markdown, end="")
    return 0


# --- PoC 3 (specs/003-beat-bar-mapping/contracts/cli.md) ---


def _cmd_beats(args: argparse.Namespace) -> int:
    from poc.beat.beat_this_adapter import BeatThisEstimator
    from poc.beat.run import load_beatgrid, run_beats

    out = run_beats(
        args.poc1_run_dir,
        args.input,
        args.output_dir,
        BeatThisEstimator(),
        regularize=not args.no_regularize,
        offset=args.offset,
        transcriptions_dir=args.transcriptions_dir,
    )
    grid = load_beatgrid(out)
    inferred = sum(b.inferred for b in grid.beats)
    print(
        f"bpm={grid.bpm} meter={grid.meter} beats={len(grid.beats)} (filled {inferred}) "
        f"bars={len(grid.downbeats)} downbeats={grid.downbeat_source} "
        f"(changed {grid.regularization['changed_downbeats']}, "
        f"phase changes {len(grid.regularization['phase_changes'])}) "
        f"offset={grid.offset['applied_ms']}ms",
        file=sys.stderr,
    )
    for warning in grid.warnings:
        print(f"warning: {warning.code}: {warning.message}", file=sys.stderr)
    print(out.resolve())
    return 0


def _cmd_map(args: argparse.Namespace) -> int:
    from poc.mapping.reference import load_reference, run_map

    out = run_map(args.beatgrid_dir, args.transcription_dir, args.output_dir)
    reference = load_reference(out)
    print(
        f"events={len(reference.events)} bars={reference.bars} unmapped={reference.unmapped_count}",
        file=sys.stderr,
    )
    print(out.resolve())
    return 0


def _cmd_bars(args: argparse.Namespace) -> int:
    from poc.mapping.reference import events_in_bars, load_reference

    reference = load_reference(args.reference_dir)
    print("bar beat grid  instrument  time_sec  deviation_ms")
    for event, p in events_in_bars(reference, args.first_bar, args.last_bar):
        print(
            f"{p.bar:3d} {p.beat:4d} {p.grid:<4s}  {event.instrument:<10s}  "
            f"{event.time_sec:8.3f}  {p.deviation_ms:+8.1f}"
        )
    return 0


def _cmd_evaluate_beats(args: argparse.Namespace) -> int:
    from poc.evaluation.beats_eval import run_evaluate_beats

    out = run_evaluate_beats(
        args.beatgrid_dir,
        args.output_dir,
        taps_dir=args.taps,
        annotation=args.annotation,
        transcription_dir=args.transcription,
        transcriptions_dir=args.transcriptions_dir,
        tolerance_ms=args.tolerance_ms,
    )
    data = json.loads((out / "evaluation.json").read_text())
    print(f"evaluation: {out.resolve()}", file=sys.stderr)
    print("variant              beat F  downbeat F  bpm err%  meter  mapping", file=sys.stderr)
    for v in data["variants"]:
        cells = [v["beats"]["f_measure"], v["downbeats"]["f_measure"]]
        text = "  ".join("  -   " if c is None else f"{c:.3f} " for c in cells)
        print(
            f"  {v['name']:<18s} {text}     {v['bpm_error_pct']}   {v['meter_match']}  "
            f"{v['mapping']['accuracy']}",
            file=sys.stderr,
        )
    if data["tap_jitter_ms"]:
        print(f"tap jitter: {data['tap_jitter_ms']}", file=sys.stderr)
    print(out.resolve())
    return 0


def _cmd_summarize_beats(args: argparse.Namespace) -> int:
    from poc.evaluation.beats_summary import summarize_beats

    print(summarize_beats(args.evaluations_dir, args.report_dir), end="")
    return 0


def _cmd_check_beats(args: argparse.Namespace) -> int:
    from poc.evaluation.beats_summary import compare_beatgrids

    n_a, n_b, diff, passed = compare_beatgrids(args.beatgrid_dir_a, args.beatgrid_dir_b)
    result = "PASS" if passed else "FAIL"
    print(f"beats_a={n_a} beats_b={n_b} max_diff_sec={diff:g} result={result}")
    return 0 if passed else 1


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
    p.add_argument("--calibrate", action="store_true", help="measure MIDI-to-audio latency per pad")
    p.add_argument("--list-devices", action="store_true")
    p.add_argument("--device", default="TD-17")
    p.add_argument("--midi-port", default="TD-17")
    p.add_argument("--output-dir", type=Path, default=Path("output/recordings"))
    p.add_argument("--max-seconds", type=float, help="stop after this many seconds of the song")
    p.add_argument(
        "--click", action="store_true", help="play a click on every song beat (Beat This!)"
    )
    p.add_argument(
        "--tap-beats",
        action="store_true",
        help="play the original song and tap its beats (hi-hat; kick on downbeats)",
    )
    p.set_defaults(func=_cmd_record)

    p = sub.add_parser("annotate", help="mark hits of a song in the browser (manual annotation)")
    p.add_argument("annotation_yaml", type=Path)
    p.add_argument(
        "--source",
        choices=["drums", "song"],
        default="drums",
        help="play the PoC 1 drum stem (default) or the original song",
    )
    p.add_argument("--runs-dir", type=Path, default=Path("output/runs"))
    p.add_argument("--port", type=int, default=0, help="default: any free port")
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--beats", action="store_true", help="mark beats / downbeats (beat_regions)")
    p.set_defaults(func=_cmd_annotate)

    p = sub.add_parser("evaluate", help="evaluate drum events against ground truth")
    p.add_argument("recording_dir", type=Path, nargs="?")
    p.add_argument("--annotation", type=Path)
    p.add_argument("--tolerance-ms", type=float, default=50.0)
    p.add_argument("--ghost-velocity", type=int, default=40)
    p.add_argument("--calibration", type=Path, help="calibration directory (default: latest)")
    p.add_argument("--thresholds", default="", help="e.g. kick=0.12,hihat=0.12")
    p.set_defaults(func=_cmd_evaluate)

    p = sub.add_parser("summarize-events", help="aggregate PoC 2 evaluations")
    p.add_argument("--evaluations-dir", type=Path, default=Path("output/evaluations"))
    p.add_argument("--report-dir", type=Path, default=Path("output/reports"))
    p.set_defaults(func=_cmd_summarize_events)

    p = sub.add_parser("tune-thresholds", help="choose detection thresholds with TD-17 data")
    p.add_argument("--evaluations-dir", type=Path, default=Path("output/evaluations"))
    p.add_argument("--recordings-dir", type=Path, default=Path("output/recordings"))
    p.add_argument("--report-dir", type=Path, default=Path("output/reports"))
    p.set_defaults(func=_cmd_tune_thresholds)

    p = sub.add_parser("beats", help="estimate beats / downbeats of a PoC 1 run (BeatGrid)")
    p.add_argument("poc1_run_dir", type=Path)
    p.add_argument("--input", choices=["mix", "drum_stem"], default="mix")
    p.add_argument("--no-regularize", action="store_true", help="use the raw downbeats")
    p.add_argument(
        "--offset",
        action="store_true",
        help="shift the grid onto the drums of the latest drum stem transcription",
    )
    p.add_argument("--transcriptions-dir", type=Path, default=Path("output/transcriptions"))
    p.add_argument("--output-dir", type=Path, default=Path("output/beatgrids"))
    p.set_defaults(func=_cmd_beats)

    p = sub.add_parser("map", help="map drum events onto bars and beats (ReferencePerformance)")
    p.add_argument("beatgrid_dir", type=Path)
    p.add_argument("transcription_dir", type=Path)
    p.add_argument("--output-dir", type=Path, default=Path("output/references"))
    p.set_defaults(func=_cmd_map)

    p = sub.add_parser("bars", help="list the drum events of some bars")
    p.add_argument("reference_dir", type=Path)
    p.add_argument("first_bar", type=int)
    p.add_argument("last_bar", type=int, nargs="?")
    p.set_defaults(func=_cmd_bars)

    p = sub.add_parser("evaluate-beats", help="evaluate a BeatGrid against beat ground truth")
    p.add_argument("beatgrid_dir", type=Path)
    p.add_argument("--taps", type=Path, help="a `record --tap-beats` recording directory")
    p.add_argument("--annotation", type=Path, help="annotation.yaml with beat_regions")
    p.add_argument("--transcription", type=Path, help="default: latest drum stem transcription")
    p.add_argument("--transcriptions-dir", type=Path, default=Path("output/transcriptions"))
    p.add_argument("--tolerance-ms", type=float, default=70.0)
    p.add_argument("--output-dir", type=Path, default=Path("output/beat_evaluations"))
    p.set_defaults(func=_cmd_evaluate_beats)

    p = sub.add_parser("summarize-beats", help="aggregate PoC 3 evaluations")
    p.add_argument("--evaluations-dir", type=Path, default=Path("output/beat_evaluations"))
    p.add_argument("--report-dir", type=Path, default=Path("output/reports"))
    p.set_defaults(func=_cmd_summarize_beats)

    p = sub.add_parser("check-beats", help="compare two BeatGrids of the same input")
    p.add_argument("beatgrid_dir_a", type=Path)
    p.add_argument("beatgrid_dir_b", type=Path)
    p.set_defaults(func=_cmd_check_beats)

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

"""`poc annotate`: serve poc/evaluation/annotator.html on localhost with the song and the
regions of an annotation.yaml already loaded, and save hits.csv next to it (research R-13).

The server listens on 127.0.0.1 only; the audio never leaves the machine."""

from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

from poc.errors import UserInputError
from poc.evaluation.groundtruth import LABELS

PAGE = Path(__file__).with_name("annotator.html")
VALID_LABELS = set(LABELS) | {"sg", "hg"}


def annotation_config(annotation_yaml: Path, runs_dir: Path, source: str) -> dict:
    """Regions, existing hits and the audio path for the page. `source` is "drums" (the
    PoC 1 drum stem) or "song" (the original file); both share one timeline."""
    annotation_yaml = Path(annotation_yaml)
    data = yaml.safe_load(annotation_yaml.read_text()) or {}
    run_dir = Path(runs_dir) / str(data.get("poc1_run_id", ""))
    if not (run_dir / "run.json").exists():
        raise UserInputError(f"{annotation_yaml}: PoC 1 run {data.get('poc1_run_id')!r} not found")
    regions = sorted([float(a), float(b)] for a, b in data.get("regions") or [])
    if not regions:
        raise UserInputError(f"{annotation_yaml}: no regions")
    if source == "drums":
        audio = run_dir / "drums.wav"
    else:
        audio = Path(json.loads((run_dir / "run.json").read_text())["song"]["path"])
    if not audio.exists():
        raise UserInputError(f"audio not found: {audio}")
    hits_path = annotation_yaml.parent / str(data.get("hits_csv", "hits.csv"))
    return {
        "name": annotation_yaml.parent.name,
        "regions": regions,
        "audio": audio,
        "hits_path": hits_path,
        "hits_csv": hits_path.read_text() if hits_path.exists() else "",
    }


def write_hits(hits_path: Path, csv_text: str) -> int:
    """Validate `time_sec,label` rows and write them. Returns the number of hits."""
    rows = []
    for line_no, line in enumerate(csv_text.splitlines(), start=1):
        if not line.strip() or (line_no == 1 and line.startswith("time")):
            continue
        time_text, _, label = line.partition(",")
        try:
            time_sec = float(time_text)
        except ValueError:
            raise UserInputError(f"line {line_no}: invalid time {time_text!r}") from None
        if label.strip() not in VALID_LABELS:
            raise UserInputError(f"line {line_no}: invalid label {label!r}")
        rows.append(f"{time_sec:.3f},{label.strip()}")
    Path(hits_path).write_text("time_sec,label\n" + "".join(r + "\n" for r in rows))
    return len(rows)


def serve(config: dict, port: int = 0, open_browser: bool = True) -> None:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path == "/":
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/config":
                public = {k: config[k] for k in ("name", "regions", "hits_csv")}
                self._send(200, json.dumps(public).encode(), "application/json")
            elif self.path == "/audio":
                self._send(200, Path(config["audio"]).read_bytes(), "application/octet-stream")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):  # noqa: N802
            if self.path != "/hits":
                self._send(404, b"not found", "text/plain")
                return
            body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
            try:
                count = write_hits(config["hits_path"], body)
            except UserInputError as err:
                self._send(400, str(err).encode(), "text/plain; charset=utf-8")
                return
            config["hits_csv"] = body
            print(f"saved {count} hits to {config['hits_path']}", flush=True)
            self._send(200, json.dumps({"saved": count}).encode(), "application/json")

        def log_message(self, *args):  # keep the terminal quiet
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"annotator: {url}  (Ctrl+C to stop)", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

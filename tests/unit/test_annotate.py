import json
import threading
import time
import urllib.request

import pytest

from poc.errors import UserInputError
from poc.evaluation import annotate


@pytest.fixture
def annotation(tmp_path):
    run_dir = tmp_path / "runs" / "20261004-000000_abcd"
    run_dir.mkdir(parents=True)
    song = tmp_path / "song.m4a"
    song.write_bytes(b"song")
    (run_dir / "run.json").write_text(json.dumps({"song": {"path": str(song)}}))
    (run_dir / "drums.wav").write_bytes(b"drums")
    ann_dir = tmp_path / "annotations" / "demo"
    ann_dir.mkdir(parents=True)
    path = ann_dir / "annotation.yaml"
    path.write_text(
        "schema_version: 1\npoc1_run_id: 20261004-000000_abcd\n"
        "regions:\n  - [30.0, 35.0]\n  - [10.0, 15.0]\nhits_csv: hits.csv\n"
    )
    return path, tmp_path / "runs"


def test_annotation_config(annotation):
    path, runs = annotation
    config = annotate.annotation_config(path, runs, "drums")
    assert config["name"] == "demo"
    assert config["regions"] == [[10.0, 15.0], [30.0, 35.0]]
    assert config["audio"].name == "drums.wav"
    assert config["hits_path"] == path.parent / "hits.csv"
    assert config["hits_csv"] == ""
    assert annotate.annotation_config(path, runs, "song")["audio"].name == "song.m4a"


def test_annotation_config_unknown_run(annotation, tmp_path):
    path, _ = annotation
    with pytest.raises(UserInputError):
        annotate.annotation_config(path, tmp_path / "nowhere", "drums")


def test_write_hits_validates_and_normalizes(tmp_path):
    out = tmp_path / "hits.csv"
    assert annotate.write_hits(out, "time_sec,label\n10.5,k\n10.5,h\n11,sg\n\n") == 3
    assert out.read_text() == "time_sec,label\n10.500,h\n10.500,k\n11.000,sg\n"
    with pytest.raises(UserInputError):
        annotate.write_hits(out, "10.5,x\n")
    with pytest.raises(UserInputError):
        annotate.write_hits(out, "abc,k\n")


def test_server_serves_config_and_saves_hits(annotation, monkeypatch):
    path, runs = annotation
    config = annotate.annotation_config(path, runs, "drums")
    servers = []
    real = annotate.ThreadingHTTPServer

    def capture(*args, **kwargs):
        servers.append(real(*args, **kwargs))
        return servers[-1]

    monkeypatch.setattr(annotate, "ThreadingHTTPServer", capture)
    thread = threading.Thread(target=annotate.serve, args=(config,), kwargs={"open_browser": False})
    thread.start()
    while not servers:
        time.sleep(0.01)
    base = f"http://127.0.0.1:{servers[0].server_address[1]}/"
    try:
        assert b"Drum Annotator" in urllib.request.urlopen(base).read()
        assert json.loads(urllib.request.urlopen(base + "config").read())["regions"][0] == [10, 15]
        assert urllib.request.urlopen(base + "audio").read() == b"drums"
        req = urllib.request.Request(base + "hits", data=b"time_sec,label\n12.0,s\n", method="POST")
        assert json.loads(urllib.request.urlopen(req).read()) == {"saved": 1}
        assert (path.parent / "hits.csv").read_text() == "time_sec,label\n12.000,s\n"
    finally:
        servers[0].shutdown()
        thread.join()


def test_annotation_config_beats_mode(annotation):
    path, runs = annotation
    with pytest.raises(UserInputError):  # no beat_regions yet
        annotate.annotation_config(path, runs, "drums", beats=True)
    path.write_text(path.read_text() + "beat_regions:\n  - [40.0, 50.0]\n")
    (path.parent / "beats.csv").write_text("time_sec,label\n40.000,d\n")
    config = annotate.annotation_config(path, runs, "drums", beats=True)
    assert config["mode"] == "beats"
    assert config["regions"] == [[40.0, 50.0]]
    assert config["hits_path"] == path.parent / "beats.csv"
    assert config["hits_csv"].startswith("time_sec,label")

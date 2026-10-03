import time

from poc.evaluation.metrics import Stopwatch, environment_info, mps_driver_bytes, peak_rss_bytes


def test_stopwatch_records_stages_and_total():
    watch = Stopwatch()
    with watch.stage("decode"):
        time.sleep(0.01)
    with watch.stage("separate"):
        time.sleep(0.02)
    with watch.stage("decode"):  # repeated stages accumulate
        time.sleep(0.01)
    result = watch.result()
    assert set(result) == {"decode", "separate", "total"}
    assert result["decode"] >= 0.02
    assert result["separate"] >= 0.02
    assert result["total"] >= result["decode"] + result["separate"]


def test_peak_rss_is_positive_bytes():
    rss = peak_rss_bytes()
    assert isinstance(rss, int)
    assert rss > 10 * 1024**2  # a Python process with numpy uses well over 10 MB


def test_mps_driver_bytes_is_none_on_cpu():
    assert mps_driver_bytes("cpu") is None


def test_environment_info_keys():
    info = environment_info()
    assert set(info) == {"python", "torch", "demucs", "ffmpeg", "platform", "machine"}
    assert all(isinstance(v, str) and v for v in info.values())

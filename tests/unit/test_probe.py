from pathlib import Path

import pytest

from poc.audio.probe import check_drm, parse_probe
from poc.errors import DrmProtectedError, UnsupportedAudioError


def probe_json(codec="aac", channels=2, sample_rate=44100, codec_tag="mp4a", fmt="mov,mp4,m4a"):
    return {
        "streams": [
            {"codec_type": "video", "codec_name": "mjpeg"},
            {
                "codec_type": "audio",
                "codec_name": codec,
                "codec_tag_string": codec_tag,
                "sample_rate": str(sample_rate),
                "channels": channels,
            },
        ],
        "format": {"format_name": fmt, "duration": "240.000000"},
    }


def test_m4p_extension_is_drm():
    with pytest.raises(DrmProtectedError):
        check_drm(Path("song.m4p"), probe_json(), "")


def test_drms_codec_tag_is_drm():
    with pytest.raises(DrmProtectedError):
        check_drm(Path("song.m4a"), probe_json(codec_tag="drms"), "")


@pytest.mark.parametrize("word", ["DRM", "encrypted", "protected"])
def test_drm_words_in_stderr(word):
    with pytest.raises(DrmProtectedError):
        check_drm(Path("song.m4a"), None, f"stream is {word} and cannot be decoded")


def test_plain_file_is_not_drm():
    check_drm(Path("song.m4a"), probe_json(), "")


@pytest.mark.parametrize("codec", ["pcm_s16le", "pcm_s24be", "pcm_f32le", "mp3", "aac", "alac"])
def test_supported_codecs(codec):
    result = parse_probe(probe_json(codec=codec, channels=1, sample_rate=48000))
    assert result.codec == codec
    assert result.channels == 1
    assert result.sample_rate == 48000
    assert result.duration_sec == pytest.approx(240.0)
    assert result.format_name == "mov,mp4,m4a"


def test_unsupported_codec():
    with pytest.raises(UnsupportedAudioError):
        parse_probe(probe_json(codec="opus"))


def test_too_many_channels():
    with pytest.raises(UnsupportedAudioError):
        parse_probe(probe_json(channels=6))


def test_no_audio_stream():
    data = probe_json()
    data["streams"] = data["streams"][:1]
    with pytest.raises(UnsupportedAudioError):
        parse_probe(data)

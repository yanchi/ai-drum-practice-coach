import hashlib
import shutil

import numpy as np
import pytest
from conftest import sine, write_wav

from poc.audio.decode import load_song
from poc.errors import InputReadError

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.mark.parametrize(("sr", "channels"), [(48000, 1), (44100, 2)])
def test_load_wav(tmp_path, sr, channels):
    audio = sine(440, 2, sr, channels=channels)
    path = write_wav(tmp_path, "tone.wav", audio, sr, subtype="FLOAT")

    song, decoded, warnings = load_song(path)

    assert decoded.dtype == np.float32
    assert decoded.shape == audio.shape
    assert np.allclose(decoded, audio, atol=1e-6)
    assert song.sample_rate == sr
    assert song.channels == channels
    assert song.num_samples == audio.shape[1]
    assert song.codec == "pcm_f32le"
    assert song.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert warnings == []


def test_missing_file(tmp_path):
    with pytest.raises(InputReadError):
        load_song(tmp_path / "missing.wav")


def test_not_audio(tmp_path):
    path = tmp_path / "notes.wav"
    path.write_text("not audio")
    with pytest.raises(InputReadError):
        load_song(path)

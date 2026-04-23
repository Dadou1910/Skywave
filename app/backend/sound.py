"""
Sound alerts for training mode.

Generates soft sine-wave tones entirely in Python — no audio files needed,
no extra dependencies beyond PyQt6.QtMultimedia which ships with PyQt6.

Two tones:
  - enter_tone : gentle high ding  (440 Hz, soft)  — you reached the target
  - exit_tone  : low soft thud     (220 Hz, soft)  — you left the target
"""

import struct
import math
import tempfile
import os

from PyQt6.QtCore import QUrl
from PyQt6.QtMultimedia import QSoundEffect


# ── Tone generation ───────────────────────────────────────────────────────────
# We write a minimal WAV file to a temp file and point QSoundEffect at it.
# QSoundEffect is low-latency (unlike QMediaPlayer) — ideal for alerts.

def _make_wav(freq: float, duration: float, volume: float, sample_rate: int = 44100) -> str:
    """
    Generate a sine wave with a quick fade-in and fade-out envelope,
    write it as a WAV file to a temp path, return the path.
    """
    n_samples = int(sample_rate * duration)
    fade      = int(sample_rate * 0.02)   # 20ms fade in/out

    samples = []
    for i in range(n_samples):
        t     = i / sample_rate
        sine  = math.sin(2 * math.pi * freq * t)

        # Amplitude envelope: fade in, sustain, fade out
        if i < fade:
            env = i / fade
        elif i > n_samples - fade:
            env = (n_samples - i) / fade
        else:
            env = 1.0

        sample = int(sine * env * volume * 32767)
        samples.append(max(-32767, min(32767, sample)))

    # WAV header
    data_bytes = b"".join(struct.pack("<h", s) for s in samples)
    n_bytes    = len(data_bytes)

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + n_bytes,
        b"WAVE",
        b"fmt ",
        16,           # chunk size
        1,            # PCM
        1,            # mono
        sample_rate,
        sample_rate * 2,
        2,            # block align
        16,           # bits per sample
        b"data",
        n_bytes,
    )

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.write(header + data_bytes)
    tmp.close()
    return tmp.name


# ── SoundAlert ────────────────────────────────────────────────────────────────

class SoundAlert:
    """
    Two pre-generated tones for training feedback.
    Call play_enter() when the metric crosses into target zone,
    call play_exit() when it drops out.
    """

    def __init__(self):
        self._enabled = True

        # Generate WAV files once at startup
        self._enter_path = _make_wav(freq=523.0, duration=0.35, volume=0.35)  # C5 — bright
        self._exit_path  = _make_wav(freq=262.0, duration=0.45, volume=0.25)  # C4 — low soft

        self._enter = QSoundEffect()
        self._enter.setSource(QUrl.fromLocalFile(self._enter_path))
        self._enter.setVolume(0.6)

        self._exit = QSoundEffect()
        self._exit.setSource(QUrl.fromLocalFile(self._exit_path))
        self._exit.setVolume(0.5)

    def play_enter(self) -> None:
        """Play the 'entered target zone' tone."""
        if self._enabled:
            self._enter.play()

    def play_exit(self) -> None:
        """Play the 'left target zone' tone."""
        if self._enabled:
            self._exit.play()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def cleanup(self) -> None:
        """Remove temp WAV files. Call on app exit."""
        for path in (self._enter_path, self._exit_path):
            try:
                os.unlink(path)
            except OSError:
                pass
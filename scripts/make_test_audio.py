"""
Generate a synthetic test audio file that simulates a typical instrumental
song structure:

  0:00  Intro        (12s, low energy, rising)
  0:12  Main A       (28s, full mix, high energy)
  0:40  Fill In      (3s, percussive transition)
  0:43  Main B       (30s, full mix, slightly different texture)
  1:13  Break        (12s, sparse, low energy)
  1:25  Main C       (40s, full mix, returns to energy)
  2:05  Ending       (15s, decrescendo)
  2:20  Fade Out     (10s, fading to silence)
  ---
  Total ~2:30

Output: examples/test_song.wav (22050 Hz, mono)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

SR = 22050


def _tone(freq: float, dur: float, sr: int = SR, amp: float = 0.3) -> np.ndarray:
    t = np.arange(int(dur * sr)) / sr
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _chord(freqs, dur: float, sr: int = SR, amp: float = 0.2) -> np.ndarray:
    out = np.zeros(int(dur * sr), dtype=np.float32)
    for f in freqs:
        out += _tone(f, dur, sr, amp / len(freqs))
    return out


def _fade(signal: np.ndarray, fade_in: float = 0.0, fade_out: float = 0.0, sr: int = SR) -> np.ndarray:
    out = signal.copy()
    if fade_in > 0:
        fi = int(fade_in * sr)
        out[:fi] *= np.linspace(0, 1, fi)
    if fade_out > 0:
        fo = int(fade_out * sr)
        out[-fo:] *= np.linspace(1, 0, fo)
    return out


def _mix(*parts: np.ndarray) -> np.ndarray:
    n = max(p.shape[0] for p in parts)
    out = np.zeros(n, dtype=np.float32)
    for p in parts:
        out[:p.shape[0]] += p
    return out


def _harmonic_layer(dur: float, root_freq: float, color: str = "A") -> np.ndarray:
    if color == "A":
        freqs = [root_freq, root_freq * 1.5, root_freq * 2]
    elif color == "B":
        freqs = [root_freq * 1.06, root_freq * 1.6, root_freq * 2.12]
    else:
        freqs = [root_freq, root_freq * 1.25, root_freq * 1.5]
    tone = _chord(freqs, dur, amp=0.18)
    t = np.arange(tone.shape[0]) / SR
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.5 * t)
    tone *= lfo.astype(np.float32)
    return tone


def _perc_layer(dur: float, bpm: float = 120, sr: int = SR) -> np.ndarray:
    out = np.zeros(int(dur * sr), dtype=np.float32)
    beat_period = 60.0 / bpm
    t = 0.0
    while t < dur:
        idx = int(t * sr)
        env_len = int(0.1 * sr)
        if idx + env_len < out.shape[0]:
            env = np.exp(-np.arange(env_len) / (env_len * 0.3))
            out[idx:idx + env_len] += env * 0.5
        t += beat_period
    return out


def build_test_song() -> np.ndarray:
    parts: list[np.ndarray] = []

    intro = _harmonic_layer(12.0, 220.0, color="A") * 0.5
    intro = _fade(intro, fade_in=3.0)
    parts.append(intro)

    main_a = _mix(
        _harmonic_layer(28.0, 220.0, color="A"),
        _perc_layer(28.0, bpm=120) * 0.6,
    )
    parts.append(main_a)

    fill = _perc_layer(3.0, bpm=240) * 1.2
    parts.append(fill)

    main_b = _mix(
        _harmonic_layer(30.0, 220.0, color="B"),
        _perc_layer(30.0, bpm=120) * 0.6,
    )
    parts.append(main_b)

    break_part = _harmonic_layer(12.0, 165.0, color="A") * 0.3
    parts.append(break_part)

    main_c = _mix(
        _harmonic_layer(40.0, 220.0, color="C"),
        _perc_layer(40.0, bpm=120) * 0.7,
    )
    parts.append(main_c)

    ending = _harmonic_layer(15.0, 220.0, color="A") * 0.6
    ending = _fade(ending, fade_out=2.0)
    parts.append(ending)

    fade_out = _harmonic_layer(10.0, 220.0, color="A") * 0.5
    fade_out = _fade(fade_out, fade_out=10.0)
    parts.append(fade_out)

    signal = np.concatenate(parts)
    peak = np.max(np.abs(signal))
    if peak > 0:
        signal = signal / peak * 0.85
    return signal.astype(np.float32)


def main():
    out_dir = Path(__file__).resolve().parent.parent / "examples"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "test_song.wav"
    sig = build_test_song()
    sf.write(out_path, sig, SR, subtype="PCM_16")
    print(f"Wrote {out_path} ({sig.shape[0] / SR:.2f}s, {SR} Hz)")


if __name__ == "__main__":
    main()

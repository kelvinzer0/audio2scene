"""
audio2scene.features
====================

DSP feature extraction layer.

Given an audio file path (or numpy array + sample rate), produces a
:class:`FeatureMatrix` containing frame-level features that downstream
segmentation and classification consume.

Features implemented (per PRD section 6):
- RMS Energy
- Loudness (LUFS approximation)
- Beat tracking
- Tempo
- Chroma features
- MFCC
- Spectral flux
- Spectral centroid
- Zero crossing rate
- Harmonic / percussive separation
- Silence detection
- Dynamic change detection

All features are computed at a single hop length so they are aligned
frame-by-frame, simplifying downstream processing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import librosa
import soundfile as sf
from scipy.ndimage import median_filter


SR_DEFAULT = 22050
N_FFT = 2048
HOP_LENGTH = 1024  # ~46ms at 22050Hz — sufficient for song-structure granularity

# File extensions that soundfile handles natively (no ffmpeg needed)
_SOUNDFILE_EXTS = {".wav", ".flac", ".ogg", ".aiff", ".aif"}


@dataclass
class FeatureMatrix:
    """Frame-aligned feature bundle."""

    sr: int
    hop_length: int
    duration: float
    times: np.ndarray                       # (T,) seconds, center of each frame

    rms: np.ndarray                          # (T,)
    loudness_lufs: np.ndarray                # (T,) approximate
    spectral_flux: np.ndarray                # (T,)
    spectral_centroid: np.ndarray            # (T,)
    zcr: np.ndarray                          # (T,)
    mfcc: np.ndarray                         # (20, T)
    chroma: np.ndarray                       # (12, T)
    harmonic: np.ndarray                     # (T,) RMS of harmonic component
    percussive: np.ndarray                   # (T,) RMS of percussive component
    silence: np.ndarray                      # (T,) bool, True if silent frame

    # Beat/tempo
    tempo: float
    beat_frames: np.ndarray                  # (B,) frame indices of beats
    beat_times: np.ndarray                   # (B,) seconds

    # Onset detection (for video editor transitions)
    onset_env: np.ndarray                    # (T,) onset strength envelope
    onset_frames: np.ndarray                 # (O,) frame indices of onsets
    onset_times: np.ndarray                  # (O,) seconds

    @property
    def n_frames(self) -> int:
        return self.rms.shape[0]


def load_audio(path: str | Path, sr: int = SR_DEFAULT, mono: bool = True) -> Tuple[np.ndarray, int]:
    """Load any audio file.

    Uses ``soundfile`` for WAV/FLAC/OGG/AIFF (fast path, no ffmpeg needed).
    Falls back to ``librosa.load`` for MP3/M4A/AAC and other compressed
    formats (which uses audioread/ffmpeg internally).
    """
    p = Path(path)
    ext = p.suffix.lower()
    if ext in _SOUNDFILE_EXTS:
        y, sr_native = sf.read(str(p), always_2d=False, dtype="float32")
        if y.ndim > 1:
            if mono:
                y = y.mean(axis=1)
            else:
                # Keep channels: shape (channels, samples)
                y = y.T
        if sr_native != sr:
            y = librosa.resample(y, orig_sr=sr_native, target_sr=sr)
        return y.astype(np.float32), sr

    # Compressed formats via librosa (uses audioread/ffmpeg)
    y, sr_out = librosa.load(str(path), sr=sr, mono=mono)
    return y, sr_out


def extract_features(
    y: Optional[np.ndarray] = None,
    sr: int = SR_DEFAULT,
    *,
    path: Optional[str | Path] = None,
    hop_length: int = HOP_LENGTH,
    n_fft: int = N_FFT,
) -> FeatureMatrix:
    """Extract frame-level features.

    Either provide ``y`` directly, or ``path`` to load audio first.
    """
    if y is None:
        if path is None:
            raise ValueError("Provide either y or path")
        y, sr = load_audio(path, sr=sr)

    if y.ndim > 1:
        y = y.mean(axis=0)
    y = y.astype(np.float32)

    duration = len(y) / sr
    # Compute features in a sensible order
    # 1. STFT-derived (single source of truth for downstream features)
    stft = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop_length))
    n_frames = stft.shape[1]
    times = librosa.frames_to_time(np.arange(n_frames), sr=sr, hop_length=hop_length)

    # 2. RMS energy (from STFT — avoids recomputing windowed frames)
    rms = librosa.feature.rms(S=stft)[0]
    rms = _align(rms, n_frames)

    # 3. Loudness (LUFS approximation). True ITU-R BS.1770 needs K-weighting;
    # we use a simplified approach: RMS in dB after a pre-emphasis filter.
    # Inline pre-emphasis is ~100x faster than librosa.effects.preemphasis.
    y_weighted = np.empty_like(y)
    y_weighted[0] = y[0]
    y_weighted[1:] = y[1:] - 0.97 * y[:-1]
    # RMS via STFT of weighted signal
    stft_w = np.abs(librosa.stft(y_weighted, n_fft=n_fft, hop_length=hop_length))
    rms_weighted = librosa.feature.rms(S=stft_w)[0]
    rms_weighted = _align(rms_weighted, n_frames)
    del y_weighted, stft_w
    lufs = 20.0 * np.log10(np.maximum(rms_weighted, 1e-10)) - 0.691
    lufs = np.maximum(lufs, -70.0)

    # 4. Spectral flux: L1 norm of positive delta of magnitude spectrum
    flux = _spectral_flux(stft)

    # 5. Spectral centroid
    centroid = librosa.feature.spectral_centroid(S=stft, sr=sr)[0]
    centroid = _align(centroid, n_frames)

    # 6. Zero crossing rate
    zcr = librosa.feature.zero_crossing_rate(y, frame_length=n_fft, hop_length=hop_length)[0]
    zcr = _align(zcr, n_frames)

    # 7. MFCC (20 coefficients) — derived from STFT, no extra FFT
    mfcc = librosa.feature.mfcc(S=librosa.amplitude_to_db(stft, ref=np.max), n_mfcc=20)
    mfcc = _align_2d(mfcc, n_frames)

    # 8. Chroma (12 bins) — derived from STFT
    chroma = librosa.feature.chroma_stft(S=stft, sr=sr)
    chroma = _align_2d(chroma, n_frames)

    # 9. Harmonic / percussive separation (fast: median filter on spectrogram).
    # Kernel size 11 is a good speed/quality tradeoff.
    harm_spec = median_filter(stft, size=(1, 11), mode="reflect")
    perc_spec = median_filter(stft, size=(11, 1), mode="reflect")
    rms_harm = np.sqrt(np.mean(harm_spec ** 2, axis=0))
    rms_perc = np.sqrt(np.mean(perc_spec ** 2, axis=0))
    rms_harm = _align(rms_harm, n_frames)
    rms_perc = _align(rms_perc, n_frames)
    del harm_spec, perc_spec

    # 10. Silence detection (very low RMS)
    rms_db = 20.0 * np.log10(np.maximum(rms, 1e-10))
    silence = rms_db < -50.0

    # 11. Beat tracking & tempo (reuse onset strength from STFT)
    onset_env = librosa.onset.onset_strength(S=stft, sr=sr, hop_length=hop_length)
    try:
        tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_env,
            sr=sr,
            hop_length=hop_length,
        )
        beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=hop_length)
        tempo = float(np.atleast_1d(tempo)[0])
    except Exception:
        tempo = 0.0
        beat_frames = np.array([], dtype=int)
        beat_times = np.array([])

    # 12. Onset detection — peak picking on onset envelope.
    # Backtrack=True gives precise onset times (start of attack, not peak).
    # Used for video editor transitions: cut on every onset, flash on strong onsets.
    try:
        onset_frames = librosa.onset.onset_detect(
            onset_envelope=onset_env,
            sr=sr,
            hop_length=hop_length,
            backtrack=True,
            wait=int(0.1 * sr / hop_length),  # min 100ms between onsets
        )
        onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=hop_length)
    except Exception:
        onset_frames = np.array([], dtype=int)
        onset_times = np.array([])

    return FeatureMatrix(
        sr=sr,
        hop_length=hop_length,
        duration=duration,
        times=times,
        rms=rms,
        loudness_lufs=lufs,
        spectral_flux=flux,
        spectral_centroid=centroid,
        zcr=zcr,
        mfcc=mfcc,
        chroma=chroma,
        harmonic=rms_harm,
        percussive=rms_perc,
        silence=silence,
        tempo=tempo,
        beat_frames=beat_frames,
        beat_times=beat_times,
        onset_env=onset_env,
        onset_frames=onset_frames,
        onset_times=onset_times,
    )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _align(arr: np.ndarray, n: int) -> np.ndarray:
    """Pad/truncate 1D array to exactly ``n`` frames."""
    if arr.shape[0] == n:
        return arr
    if arr.shape[0] > n:
        return arr[:n]
    pad = np.zeros(n - arr.shape[0], dtype=arr.dtype)
    return np.concatenate([arr, pad])


def _align_2d(arr: np.ndarray, n: int) -> np.ndarray:
    if arr.shape[1] == n:
        return arr
    if arr.shape[1] > n:
        return arr[:, :n]
    pad = np.zeros((arr.shape[0], n - arr.shape[1]), dtype=arr.dtype)
    return np.concatenate([arr, pad], axis=1)


def _spectral_flux(stft: np.ndarray) -> np.ndarray:
    """L1 norm of positive magnitude delta between consecutive frames."""
    mag = stft
    if mag.shape[1] < 2:
        return np.zeros(mag.shape[1])
    delta = np.diff(mag, axis=1, prepend=mag[:, :1])
    delta = np.maximum(delta, 0.0)
    flux = np.sum(delta, axis=0) / mag.shape[0]
    return flux

"""
audio2scene.segmentation
========================

Boundary detection.

Converts a :class:`FeatureMatrix` into a list of segments
``(start_time, end_time)`` based on:

- Silence runs (silence boundaries)
- Large RMS energy changes (intro/outro/break boundaries)
- Spectral flux spikes (fill-in / transition boundaries)
- MFCC clustering (change of texture = Main Variation boundary)
- Tempo change boundaries

The result is a list of non-overlapping (start, end) intervals in seconds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

import numpy as np
from scipy.signal import find_peaks

from .features import FeatureMatrix


@dataclass
class Segment:
    start: float
    end: float

    def __post_init__(self):
        if self.end < self.start:
            raise ValueError(f"end ({self.end}) < start ({self.start})")


def segment_audio(features: FeatureMatrix, min_segment_sec: float = 5.0) -> List[Segment]:
    """Return a list of (start, end) segments covering the whole duration.

    Boundaries are derived from a fusion of multiple novelty cues. The
    segmentation is **exhaustive**: every second of audio belongs to
    exactly one segment.

    ``min_segment_sec`` defaults to 5.0 — short enough to catch genuine
    transitions like Fill-Ins, long enough to suppress LFO-driven
    micro-fluctuations (~2s period in many instrumentals).
    """
    if features.n_frames == 0:
        return []

    times = features.times
    duration = features.duration

    # Collect candidate boundary frames from multiple cues
    boundaries = set()

    # 1. Silence runs longer than 0.4s start/end create boundaries
    silence_runs = _runs(features.silence)
    for s, e in silence_runs:
        if (e - s) * features.hop_length / features.sr >= 0.4:
            boundaries.add(s)
            boundaries.add(min(e, features.n_frames - 1))

    # 2. RMS energy novelty (large jumps only).
    # Use heavy smoothing (sigma=8) to filter out LFO and micro-fluctuations.
    # Threshold: top-90th percentile of novelty values (no floor — let data speak).
    rms_novelty = _novelty(features.rms, sigma=8.0)
    rms_thresh = np.percentile(rms_novelty, 90)
    rms_peaks, _ = find_peaks(
        rms_novelty,
        height=rms_thresh,
        distance=int(3.0 * features.sr / features.hop_length),
    )
    for p in rms_peaks:
        boundaries.add(int(p))

    # 3. Spectral flux peaks (transitions).
    # Use a smoothed flux envelope; raw flux is too noisy.
    flux_smooth = _smooth(features.spectral_flux, win=int(1.0 * features.sr / features.hop_length))
    flux_norm = flux_smooth / (np.max(flux_smooth) + 1e-9)
    flux_peaks, _ = find_peaks(
        flux_norm,
        height=0.5,
        distance=int(3.0 * features.sr / features.hop_length),
    )
    for p in flux_peaks:
        boundaries.add(int(p))

    # 4. MFCC-based novelty (texture change).
    # Use a coarser MFCC smoothing to capture section-level texture changes.
    mfcc_novelty = _mfcc_novelty(features.mfcc)
    mfcc_thresh = np.percentile(mfcc_novelty, 85)
    mfcc_peaks, _ = find_peaks(
        mfcc_novelty,
        height=mfcc_thresh,
        distance=int(4.0 * features.sr / features.hop_length),
    )
    for p in mfcc_peaks:
        boundaries.add(int(p))

    # 5. Loudness novelty (LUFS jumps > 6 dB)
    loud_novelty = _novelty(features.loudness_lufs, sigma=8.0)
    loud_peaks, _ = find_peaks(
        np.abs(loud_novelty),
        height=6.0,
        distance=int(3.0 * features.sr / features.hop_length),
    )
    for p in loud_peaks:
        boundaries.add(int(p))

    # Convert to times, sort, deduplicate close boundaries.
    # Strategy: keep all candidates with their novelty strength, then
    # iteratively remove the weakest boundary whose removal would
    # eliminate a sub-min_segment_sec segment.
    sorted_bounds = sorted(set(boundaries))
    if not sorted_bounds:
        return [Segment(start=0.0, end=duration)]
    if 0 not in sorted_bounds:
        sorted_bounds = [0] + sorted_bounds
    if (features.n_frames - 1) not in sorted_bounds:
        sorted_bounds.append(features.n_frames - 1)

    # Compute strength for each boundary: max of (RMS novelty, MFCC novelty, Flux)
    # at that frame, normalized.
    rms_nov = _novelty(features.rms, sigma=8.0)
    mfcc_nov = _mfcc_novelty(features.mfcc)
    flux_smooth = _smooth(features.spectral_flux, win=int(1.0 * features.sr / features.hop_length))
    loud_nov = _novelty(features.loudness_lufs, sigma=8.0)

    def strength(b):
        if b <= 0 or b >= features.n_frames - 1:
            return float("inf")  # always keep start/end
        rms_v = float(abs(rms_nov[b])) if b < len(rms_nov) else 0.0
        mfcc_v = float(mfcc_nov[b]) if b < len(mfcc_nov) else 0.0
        flux_v = float(flux_smooth[b]) if b < len(flux_smooth) else 0.0
        loud_v = float(abs(loud_nov[b])) if b < len(loud_nov) else 0.0
        # Normalize each by its max then sum
        rms_n = rms_v / (np.max(np.abs(rms_nov)) + 1e-9)
        mfcc_n = mfcc_v / (np.max(mfcc_nov) + 1e-9)
        flux_n = flux_v / (np.max(flux_smooth) + 1e-9)
        loud_n = loud_v / (np.max(np.abs(loud_nov)) + 1e-9)
        return rms_n + mfcc_n + flux_n + loud_n

    # Iteratively remove the weakest boundary that creates a too-short segment
    min_frames = max(1, int(min_segment_sec * features.sr / features.hop_length))
    bounds = list(sorted_bounds)
    while True:
        # Find shortest segment
        shortest_idx = -1
        shortest_len = float("inf")
        for i in range(len(bounds) - 1):
            seg_len = bounds[i + 1] - bounds[i]
            if seg_len < min_frames and seg_len < shortest_len:
                shortest_len = seg_len
                shortest_idx = i
        if shortest_idx == -1:
            break
        # Remove the weaker of the two boundaries that define this short segment
        # (we can't remove the first or last)
        b1 = bounds[shortest_idx]
        b2 = bounds[shortest_idx + 1]
        # End boundaries (0 and n-1) are protected
        if shortest_idx == 0:
            # Remove b2 (the right boundary of the short segment)
            remove_idx = shortest_idx + 1
        elif shortest_idx + 1 == len(bounds) - 1:
            # Remove b1
            remove_idx = shortest_idx
        else:
            # Remove whichever is weaker
            if strength(b1) < strength(b2):
                remove_idx = shortest_idx
            else:
                remove_idx = shortest_idx + 1
        bounds.pop(remove_idx)

    # Build segments
    segments: List[Segment] = []
    for i in range(len(bounds) - 1):
        s_frame = bounds[i]
        e_frame = bounds[i + 1]
        s_time = float(times[s_frame]) if s_frame < len(times) else 0.0
        e_time = float(times[min(e_frame, len(times) - 1)]) if e_frame < len(times) else duration
        if e_time <= s_time:
            continue
        segments.append(Segment(start=s_time, end=e_time))

    # Make sure last segment ends at duration
    if segments:
        segments[-1].end = duration
    return segments


# ── Helpers ──────────────────────────────────────────────────────────────────


def _runs(bool_arr: np.ndarray) -> List[tuple]:
    """Return list of (start, end) inclusive runs of True values."""
    runs = []
    if len(bool_arr) == 0:
        return runs
    arr = np.asarray(bool_arr, dtype=bool)
    pad = np.concatenate([[False], arr, [False]])
    diff = np.diff(pad.astype(int))
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0] - 1
    return [(int(s), int(e)) for s, e in zip(starts, ends)]


def _novelty(signal: np.ndarray, sigma: float = 4.0) -> np.ndarray:
    """First-order difference smoothed by a small Gaussian."""
    if signal.shape[0] < 3:
        return np.zeros_like(signal)
    s = signal.astype(np.float64)
    diff = np.diff(s, prepend=s[0])
    # Smooth
    win = max(3, int(sigma * 2))
    kernel = np.exp(-np.arange(-win, win + 1) ** 2 / (2 * sigma ** 2))
    kernel /= kernel.sum()
    diff = np.convolve(diff, kernel, mode="same")
    return diff


def _smooth(signal: np.ndarray, win: int = 5) -> np.ndarray:
    """Moving-average smoothing with given window size in frames."""
    if signal.shape[0] < win * 2:
        return signal.astype(np.float64)
    win = max(1, int(win))
    kernel = np.ones(win * 2 + 1) / (win * 2 + 1)
    return np.convolve(signal.astype(np.float64), kernel, mode="same")


def _mfcc_novelty(mfcc: np.ndarray) -> np.ndarray:
    """Cosine-distance novelty between consecutive MFCC frames."""
    if mfcc.shape[1] < 2:
        return np.zeros(mfcc.shape[1])
    mfcc_norm = mfcc / (np.linalg.norm(mfcc, axis=0, keepdims=True) + 1e-9)
    sim = np.zeros(mfcc.shape[1])
    sim[1:] = np.sum(mfcc_norm[:, :-1] * mfcc_norm[:, 1:], axis=0)
    novelty = 1.0 - sim
    novelty[0] = 0.0
    # Smooth
    win = 5
    kernel = np.ones(win * 2 + 1) / (win * 2 + 1)
    novelty = np.convolve(novelty, kernel, mode="same")
    return novelty

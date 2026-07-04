"""
audio2scene.classifier
======================

Scene / structure classification.

Given a :class:`FeatureMatrix` and a list of :class:`Segment` boundaries,
assigns each segment a label from the PRD-supported label set:

- ``Intro``
- ``Fade In``
- ``Main Variation A|B|C|D``
- ``Fill In``
- ``Break``
- ``Ending``
- ``Fade Out``

Decision logic (heuristic + signal-driven):

1. First non-silent segment of the song -> ``Intro`` (or ``Fade In``
   if RMS rises monotonically over >2s).
2. Last non-silent segment -> ``Ending`` (or ``Fade Out`` if RMS
   falls monotonically over >2s).
3. Segments shorter than 4s with high spectral flux -> ``Fill In``.
4. Segments with RMS energy < 0.5x of the song median -> ``Break``.
5. Other segments -> ``Main Variation`` with a letter index (A/B/C/D)
   assigned by clustering on MFCC mean (cosine distance to last assigned
   main variation; new letter if cosine < 0.85).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np

from .features import FeatureMatrix
from .segmentation import Segment


# ── Data model ───────────────────────────────────────────────────────────────


@dataclass
class LabeledSegment:
    label: str
    start: float
    end: float
    confidence: float
    intensity: float = 0.0          # 0..1, normalized energy/flux composite
    intensity_label: str = ""       # "low" / "medium" / "high" / "drop"

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "confidence": round(self.confidence, 3),
            "intensity": round(self.intensity, 3),
            "intensity_label": self.intensity_label,
        }


# ── Classifier ───────────────────────────────────────────────────────────────


def classify_segments(features: FeatureMatrix, segments: List[Segment]) -> List[LabeledSegment]:
    """Label each segment with a structural label and confidence."""
    if not segments:
        return []

    sr = features.sr
    hop = features.hop_length
    fps = sr / hop  # frames per second

    # Pre-compute per-segment stats
    stats = []
    for seg in segments:
        s_f = max(0, int(seg.start * fps))
        e_f = min(features.n_frames - 1, int(seg.end * fps))
        if e_f <= s_f:
            e_f = s_f + 1
        rms_seg = features.rms[s_f:e_f]
        flux_seg = features.spectral_flux[s_f:e_f]
        cent_seg = features.spectral_centroid[s_f:e_f]
        zcr_seg = features.zcr[s_f:e_f]
        harm_seg = features.harmonic[s_f:e_f]
        perc_seg = features.percussive[s_f:e_f]
        mfcc_seg = features.mfcc[:, s_f:e_f]
        silence_frac = float(np.mean(features.silence[s_f:e_f])) if (e_f - s_f) > 0 else 0.0

        # Combined texture vector: MFCC[1:13] + mean spectral centroid (norm) + mean ZCR (norm).
        # MFCC alone gives cosine ~0.999 between similar textures; combining with
        # centroid/ZCR adds discriminative power.
        cent_mean_val = float(np.mean(cent_seg)) if cent_seg.size else 0.0
        zcr_mean_val = float(np.mean(zcr_seg)) if zcr_seg.size else 0.0
        mfcc_mean_vec = np.mean(mfcc_seg[1:13, :], axis=1) if mfcc_seg.size else np.zeros(12)
        # Normalize and append centroid + zcr as additional dims
        texture_vec = np.concatenate([
            mfcc_mean_vec,
            [cent_mean_val * 1e-3],   # scale down to be comparable to MFCC
            [zcr_mean_val * 1e2],     # scale up
        ])

        stats.append({
            "seg": seg,
            "s_f": s_f,
            "e_f": e_f,
            "duration": seg.end - seg.start,
            "rms_mean": float(np.mean(rms_seg)) if rms_seg.size else 0.0,
            "rms_max": float(np.max(rms_seg)) if rms_seg.size else 0.0,
            "rms_std": float(np.std(rms_seg)) if rms_seg.size else 0.0,
            "rms_slope": _slope(rms_seg),
            "flux_mean": float(np.mean(flux_seg)) if flux_seg.size else 0.0,
            "flux_max": float(np.max(flux_seg)) if flux_seg.size else 0.0,
            "cent_mean": cent_mean_val,
            "zcr_mean": zcr_mean_val,
            "harm_mean": float(np.mean(harm_seg)) if harm_seg.size else 0.0,
            "perc_mean": float(np.mean(perc_seg)) if perc_seg.size else 0.0,
            "mfcc_mean": texture_vec,  # 14-dim
            "silence_frac": silence_frac,
        })

    # Song-level references
    rms_median = float(np.median(features.rms)) if features.rms.size else 0.0
    flux_median = float(np.median(features.spectral_flux)) if features.spectral_flux.size else 0.0

    # Compute song-level mean texture for deviation-based similarity.
    # Cosine similarity on raw MFCC is always ~0.99 for tonal music because
    # MFCC coefficients are highly correlated. Centering on the song mean
    # exposes the variation across sections.
    all_textures = np.stack([st["mfcc_mean"] for st in stats], axis=0)  # (N, D)
    song_mean_texture = all_textures.mean(axis=0)
    song_std_texture = all_textures.std(axis=0) + 1e-9
    # Z-score normalize each segment's texture
    for st in stats:
        st["texture_z"] = (st["mfcc_mean"] - song_mean_texture) / song_std_texture

    # Find first and last non-silent segments
    non_silent_idx = [i for i, st in enumerate(stats) if st["silence_frac"] < 0.5]
    if not non_silent_idx:
        non_silent_idx = list(range(len(stats)))
    first_idx = non_silent_idx[0]
    last_idx = non_silent_idx[-1]

    labels: List[Optional[str]] = [None] * len(stats)
    confidences: List[float] = [0.5] * len(stats)

    # 1. Intro / Fade In (first non-silent segment)
    first = stats[first_idx]
    if first["rms_slope"] > 0.3 and first["duration"] >= 2.0:
        labels[first_idx] = "Fade In"
        confidences[first_idx] = _conf(0.85)
    else:
        labels[first_idx] = "Intro"
        confidences[first_idx] = _conf(0.90)

    # 2. Ending / Fade Out (last non-silent segment)
    last = stats[last_idx]
    if last["rms_slope"] < -0.3 and last["duration"] >= 2.0:
        labels[last_idx] = "Fade Out"
        confidences[last_idx] = _conf(0.85)
    else:
        labels[last_idx] = "Ending"
        confidences[last_idx] = _conf(0.90)

    # 3. Middle segments: Fill In / Break / Main Variation
    main_variations: List[np.ndarray] = []  # texture_z vectors of each main variation
    main_letters = ["A", "B", "C", "D"]

    for i in range(len(stats)):
        if labels[i] is not None:
            continue
        st = stats[i]

        # Fill In: very short segment (<3s) with high flux (>1.8x median)
        if st["duration"] < 3.0 and st["flux_mean"] > flux_median * 1.8:
            labels[i] = "Fill In"
            confidences[i] = _conf(0.75)
            continue

        # Break: low RMS relative to median
        if st["rms_mean"] < rms_median * 0.5 and st["duration"] >= 1.0:
            labels[i] = "Break"
            confidences[i] = _conf(0.75)
            continue

        # Main Variation: assign letter based on z-scored texture similarity
        label_letter = _assign_main_letter(st["texture_z"], main_variations, main_letters)
        main_variations.append(st["texture_z"])
        labels[i] = f"Main Variation {label_letter}"
        if label_letter == "A" and len(main_variations) > 1:
            confidences[i] = _conf(0.80)
        else:
            confidences[i] = _conf(0.85)

    # Build labeled segments + intensity scoring
    # Intensity = normalized composite of RMS_mean and Flux_mean relative to song median.
    # Used downstream by video editor for effect mapping (drop / build-up / break).
    rms_max_song = float(np.max(features.rms)) if features.rms.size else 0.0
    flux_max_song = float(np.max(features.spectral_flux)) if features.spectral_flux.size else 0.0

    out: List[LabeledSegment] = []
    for i, st in enumerate(stats):
        seg = st["seg"]
        # Intensity = 0.6 * rms_norm + 0.4 * flux_norm
        rms_norm = st["rms_mean"] / (rms_max_song + 1e-9)
        flux_norm = st["flux_mean"] / (flux_max_song + 1e-9)
        intensity = float(np.clip(0.6 * rms_norm + 0.4 * flux_norm, 0.0, 1.0))

        # Intensity label — used for effect mapping
        # "drop" = very high intensity after a low-intensity segment
        if i > 0 and stats[i - 1]["rms_mean"] < rms_median * 0.6 and intensity > 0.7:
            intensity_label = "drop"
        elif intensity >= 0.7:
            intensity_label = "high"
        elif intensity >= 0.4:
            intensity_label = "medium"
        else:
            intensity_label = "low"

        out.append(LabeledSegment(
            label=labels[i] or "Main Variation A",
            start=seg.start,
            end=seg.end,
            confidence=confidences[i],
            intensity=intensity,
            intensity_label=intensity_label,
        ))
    return out


# ── Helpers ──────────────────────────────────────────────────────────────────


def _slope(arr: np.ndarray) -> float:
    """Linear slope of arr normalized to [0,1] range; >0 = rising, <0 = falling."""
    if arr.size < 2:
        return 0.0
    a = arr.astype(np.float64)
    a = (a - a.min()) / (a.max() - a.min() + 1e-9)
    n = a.size
    x = np.arange(n) / max(1, n - 1)
    slope = np.polyfit(x, a, 1)[0]
    return float(slope)


def _assign_main_letter(mfcc_mean: np.ndarray, history: List[np.ndarray], letters: List[str]) -> str:
    """Decide letter for current main variation based on cosine similarity to history.

    Operates on z-scored texture vectors (deviation from song mean), so the
    threshold can be more lenient than raw MFCC. If max similarity to any
    existing main >= 0.85, assign same letter. Otherwise assign next letter.
    Caps at 'D'.
    """
    if not history:
        return "A"
    v = mfcc_mean / (np.linalg.norm(mfcc_mean) + 1e-9)
    sims = []
    for h in history:
        h_norm = h / (np.linalg.norm(h) + 1e-9)
        sims.append(float(np.dot(v, h_norm)))
    best_idx = int(np.argmax(sims))
    if sims[best_idx] >= 0.85:
        # Reuse: find which letter that historical main was
        seen = []
        for h in history:
            v2 = h / (np.linalg.norm(h) + 1e-9)
            assigned = None
            for s_idx, s_letter in seen:
                if float(np.dot(v2, s_idx)) >= 0.85:
                    assigned = s_letter
                    break
            if assigned is None:
                if len(seen) < len(letters):
                    assigned = letters[len(seen)]
                else:
                    assigned = letters[-1]
            seen.append((v2, assigned))
        return seen[best_idx][1]
    else:
        n_distinct = _count_distinct(history, letters, threshold=0.85)
        if n_distinct < len(letters):
            return letters[n_distinct]
        return letters[-1]


def _count_distinct(history: List[np.ndarray], letters: List[str], threshold: float = 0.85) -> int:
    """Count distinct clusters among history using cosine threshold."""
    clusters: List[np.ndarray] = []
    for h in history:
        v = h / (np.linalg.norm(h) + 1e-9)
        matched = False
        for c in clusters:
            if float(np.dot(v, c)) >= threshold:
                matched = True
                break
        if not matched:
            clusters.append(v)
    return len(clusters)


def _conf(base: float) -> float:
    """Clamp confidence to [0,1]."""
    return max(0.0, min(1.0, base))

"""
audio2scene.video_editor
========================

Maps music structure (segments + beats + onsets + intensity) to
video editor effect events.

Effect vocabulary (per PRD section "Mapping ke efek"):

  Cut       — beat kecil / onset biasa   (hard cut between shots)
  Flash     — beat kuat / onset kuat      (white flash transition)
  Zoom      — build-up (rising intensity) (slow zoom-in)
  Glitch    — drop (sudden high after low) (digital glitch effect)
  Fade In   — Intro / Fade In segment     (fade from black)
  Fade Out  — Ending / Fade Out segment   (fade to black)
  Title     — first segment               (title card overlay)
  Hold      — Break                       (hold on wide shot)

The mapping pipeline (per PRD):
  FFT/STFT → Spectral Flux → Beat + Onset → Segmentasi → Skor Intensitas → Mapping

Output: list of :class:`VideoEvent` dicts ready to import into NLE
(Non-Linear Editor) like DaVinci Resolve, Premiere, or ffmpeg.

Example::

    import audio2scene
    segments, feats = audio2scene.detect("song.mp3", return_features=True)
    events = audio2scene.map_video_events(segments, feats)
    # events is List[VideoEvent]
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Optional

import numpy as np

from .classifier import LabeledSegment
from .features import FeatureMatrix


@dataclass
class VideoEvent:
    """A single video editor event at a specific time."""
    time: float                # seconds — when the event fires
    effect: str                # Cut / Flash / Zoom / Glitch / Fade In / Fade Out / Title / Hold
    intensity: float           # 0..1, how strong (drives effect parameters)
    segment_label: str         # which segment this event belongs to
    duration: float = 0.0      # seconds — for hold/zoom/fade effects (0 for instantaneous)
    source: str = ""           # "beat" / "onset" / "segment_start" / "segment_end"
    metadata: Optional[dict] = None  # extra params (beat_strength, etc.)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["time"] = round(self.time, 3)
        d["duration"] = round(self.duration, 3)
        d["intensity"] = round(self.intensity, 3)
        return d


def map_video_events(
    segments: List[LabeledSegment],
    features: FeatureMatrix,
    *,
    beat_strategy: str = "auto",   # "auto" | "all" | "downbeat_only"
    onset_strategy: str = "all",   # "all" | "strong_only"
    include_fades: bool = True,
    include_title: bool = True,
) -> List[VideoEvent]:
    """Produce video editor events from segments + features.

    Parameters
    ----------
    segments : list of LabeledSegment
        Output of :func:`audio2scene.classify_segments`.
    features : FeatureMatrix
        Output of :func:`audio2scene.extract_features`.
    beat_strategy : str
        "all" — emit Cut/Flash on every detected beat.
        "downbeat_only" — only on beats aligned to bar starts (every 4th).
        "auto" — pick based on tempo (slow songs: all beats; fast: downbeats only).
    onset_strategy : str
        "all" — emit on every onset.
        "strong_only" — only on onsets above 70th percentile strength.
    include_fades : bool
        If True (default), emit Fade In at start, Fade Out at end.
    include_title : bool
        If True (default), emit Title event at first segment start.

    Returns
    -------
    list of VideoEvent, sorted by time.
    """
    if not segments:
        return []

    events: List[VideoEvent] = []
    duration = features.duration

    # ─── 1. Fade In / Title at start ─────────────────────────────────────────
    first_seg = segments[0]
    if include_fades and first_seg.label in ("Intro", "Fade In"):
        events.append(VideoEvent(
            time=first_seg.start,
            effect="Fade In",
            intensity=0.5,
            segment_label=first_seg.label,
            duration=min(first_seg.duration, 2.0),
            source="segment_start",
        ))
    elif include_fades:
        # No intro — still a short fade-in to avoid hard cut
        events.append(VideoEvent(
            time=first_seg.start,
            effect="Fade In",
            intensity=0.3,
            segment_label=first_seg.label,
            duration=0.5,
            source="segment_start",
        ))

    if include_title:
        events.append(VideoEvent(
            time=first_seg.start + 0.5,  # 0.5s after start
            effect="Title",
            intensity=0.8,
            segment_label=first_seg.label,
            duration=3.0,
            source="segment_start",
        ))

    # ─── 2. Fade Out at end ──────────────────────────────────────────────────
    last_seg = segments[-1]
    if include_fades and last_seg.label in ("Ending", "Fade Out"):
        events.append(VideoEvent(
            time=last_seg.start,
            effect="Fade Out",
            intensity=0.7,
            segment_label=last_seg.label,
            duration=min(last_seg.duration, 3.0),
            source="segment_start",
        ))

    # ─── 3. Segment-transition effects ───────────────────────────────────────
    # Build segment_time → segment index lookup (binary search)
    seg_starts = np.array([s.start for s in segments])

    def find_segment(t: float) -> int:
        if not seg_starts.size:
            return 0
        idx = int(np.searchsorted(seg_starts, t, side="right") - 1)
        return max(0, min(idx, len(segments) - 1))

    # ─── 4. Beat events → Cut or Flash ───────────────────────────────────────
    # Compute beat strength: onset envelope value at each beat frame
    beat_frames = features.beat_frames
    onset_env = features.onset_env

    if beat_frames.size > 0:
        # Strength per beat
        beat_strengths = []
        for bf in beat_frames:
            bf_int = int(bf)
            if 0 <= bf_int < len(onset_env):
                beat_strengths.append(float(onset_env[bf_int]))
            else:
                beat_strengths.append(0.0)
        beat_strengths = np.array(beat_strengths)
        beat_max = float(beat_strengths.max()) if beat_strengths.size else 0.0

        # Determine which beats to emit
        if beat_strategy == "all":
            emit_idx = list(range(len(beat_frames)))
        elif beat_strategy == "downbeat_only":
            # Assume 4/4 — emit every 4th beat
            emit_idx = list(range(0, len(beat_frames), 4))
        else:  # "auto"
            if features.tempo < 110:
                emit_idx = list(range(len(beat_frames)))  # slow: every beat
            else:
                emit_idx = list(range(0, len(beat_frames), 2))  # fast: every 2nd

        beat_median = float(np.median(beat_strengths)) if beat_strengths.size else 0.0
        for i in emit_idx:
            t = float(features.beat_times[i])
            if t < 0 or t > duration:
                continue
            strength = beat_strengths[i] / (beat_max + 1e-9)
            seg_idx = find_segment(t)
            seg = segments[seg_idx]
            # Strong beat → Flash, normal beat → Cut
            if strength > 0.7 and beat_strengths[i] > beat_median * 1.5:
                effect = "Flash"
            else:
                effect = "Cut"
            events.append(VideoEvent(
                time=t,
                effect=effect,
                intensity=float(strength),
                segment_label=seg.label,
                source="beat",
                metadata={"beat_index": i, "beat_strength": round(float(beat_strengths[i]), 4)},
            ))

    # ─── 5. Onset events → Cut (if not already covered by a beat) ────────────
    onset_times = features.onset_times
    if onset_times.size > 0:
        # Compute onset strengths
        onset_strengths = []
        for of in features.onset_frames:
            of_int = int(of)
            if 0 <= of_int < len(onset_env):
                onset_strengths.append(float(onset_env[of_int]))
            else:
                onset_strengths.append(0.0)
        onset_strengths = np.array(onset_strengths)

        # Filter strategy
        if onset_strategy == "strong_only":
            thresh = float(np.percentile(onset_strengths, 70))
            mask = onset_strengths >= thresh
        else:
            mask = np.ones_like(onset_strengths, dtype=bool)

        # Skip onsets within 80ms of a beat (avoid duplicate events)
        beat_times_arr = features.beat_times
        for i, t in enumerate(onset_times):
            if not mask[i]:
                continue
            if t < 0 or t > duration:
                continue
            # Check if too close to a beat
            if beat_times_arr.size > 0:
                closest = float(np.min(np.abs(beat_times_arr - t)))
                if closest < 0.08:
                    continue
            seg_idx = find_segment(float(t))
            seg = segments[seg_idx]
            strength = float(onset_strengths[i] / (onset_strengths.max() + 1e-9))
            # Strong onset → Flash, normal → Cut
            effect = "Flash" if strength > 0.75 else "Cut"
            events.append(VideoEvent(
                time=float(t),
                effect=effect,
                intensity=strength,
                segment_label=seg.label,
                source="onset",
            ))

    # ─── 6. Build-up (rising intensity in Main segment) → Zoom ───────────────
    # Detect segments where intensity slope is rising significantly
    for i, seg in enumerate(segments):
        if seg.label.startswith("Main") and seg.duration >= 4.0:
            # Check RMS slope in this segment
            fps = features.sr / features.hop_length
            s_f = max(0, int(seg.start * fps))
            e_f = min(features.n_frames - 1, int(seg.end * fps))
            if e_f > s_f + 5:
                rms_seg = features.rms[s_f:e_f]
                rms_slope = _quick_slope(rms_seg)
                if rms_slope > 0.2:  # rising
                    events.append(VideoEvent(
                        time=seg.start,
                        effect="Zoom",
                        intensity=seg.intensity,
                        segment_label=seg.label,
                        duration=seg.duration,
                        source="segment_start",
                        metadata={"rms_slope": round(float(rms_slope), 3)},
                    ))

    # ─── 7. Drop (sudden high after low) → Glitch ────────────────────────────
    for i, seg in enumerate(segments):
        if seg.intensity_label == "drop":
            events.append(VideoEvent(
                time=seg.start,
                effect="Glitch",
                intensity=seg.intensity,
                segment_label=seg.label,
                duration=min(seg.duration, 1.0),
                source="segment_start",
            ))

    # ─── 8. Break → Hold ─────────────────────────────────────────────────────
    for seg in segments:
        if seg.label == "Break" and seg.duration >= 1.0:
            events.append(VideoEvent(
                time=seg.start,
                effect="Hold",
                intensity=seg.intensity,
                segment_label=seg.label,
                duration=seg.duration,
                source="segment_start",
            ))

    # ─── Sort & dedupe ───────────────────────────────────────────────────────
    events.sort(key=lambda e: e.time)

    # Dedupe: drop duplicate effects within 50ms
    deduped: List[VideoEvent] = []
    for ev in events:
        if deduped and abs(deduped[-1].time - ev.time) < 0.05 and deduped[-1].effect == ev.effect:
            # Keep the stronger one
            if ev.intensity > deduped[-1].intensity:
                deduped[-1] = ev
            continue
        deduped.append(ev)

    return deduped


def events_to_json(events: List[VideoEvent], pretty: bool = True) -> str:
    """Serialize events to JSON string."""
    import json
    data = {"events": [e.to_dict() for e in events], "n_events": len(events)}
    return json.dumps(data, indent=2 if pretty else None, ensure_ascii=False)


def events_summary(events: List[VideoEvent]) -> dict:
    """Return summary stats: count per effect, total duration, density."""
    from collections import Counter
    counter = Counter(e.effect for e in events)
    return {
        "n_events": len(events),
        "by_effect": dict(counter),
        "density_per_sec": round(len(events) / max(1, events[-1].time - events[0].time), 3) if events else 0.0,
    }


def _quick_slope(arr: np.ndarray) -> float:
    """Quick linear slope on normalized array. >0 = rising."""
    if arr.size < 2:
        return 0.0
    a = arr.astype(np.float64)
    rng = a.max() - a.min()
    if rng < 1e-9:
        return 0.0
    a = (a - a.min()) / rng
    n = a.size
    x = np.arange(n) / max(1, n - 1)
    return float(np.polyfit(x, a, 1)[0])

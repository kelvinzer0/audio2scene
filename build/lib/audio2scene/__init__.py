"""
audio2scene
===========

AI-powered structural labeling for instrumental music.

Public API:

>>> import audio2scene
>>> segments = audio2scene.detect("music.mp3")
>>> for seg in segments:
...     print(seg.label, seg.start, seg.end, seg.confidence)

CLI:

    audio2scene music.mp3 --json
    audio2scene music.mp3 --csv
    audio2scene music.mp3 --txt
    audio2scene music.mp3 --pretty
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

from .classifier import LabeledSegment
from .features import FeatureMatrix, extract_features, load_audio
from .segmentation import Segment, segment_audio
from .timeline import (
    segments_to_csv,
    segments_to_json,
    segments_to_pretty,
    segments_to_txt,
)
from .video_editor import (
    VideoEvent,
    events_to_json,
    events_summary,
    map_video_events,
)
from .remotion_generator import (
    DataSpec,
    SceneSlice,
    generate_remotion_project,
    map_content_to_timeline,
)

__version__ = "0.5.0"

__all__ = [
    "LabeledSegment",
    "FeatureMatrix",
    "Segment",
    "VideoEvent",
    "DataSpec",
    "SceneSlice",
    "detect",
    "extract_features",
    "load_audio",
    "segment_audio",
    "segments_to_json",
    "segments_to_csv",
    "segments_to_txt",
    "segments_to_pretty",
    "map_video_events",
    "events_to_json",
    "events_summary",
    "generate_remotion_project",
    "map_content_to_timeline",
    "__version__",
]


def detect(
    path_or_array: Union[str, Path, "np.ndarray"],
    *,
    sr: int = 22050,
    hop_length: int = 1024,
    min_segment_sec: float = 5.0,
    return_features: bool = False,
) -> Union[List[LabeledSegment], tuple]:
    """Detect structural segments in audio.

    Parameters
    ----------
    path_or_array : str | Path | np.ndarray
        Either an audio file path (MP3/WAV/FLAC/OGG/AAC/M4A) or a numpy
        array of float samples.
    sr : int
        Sample rate to use (default 22050).
    hop_length : int
        Hop length in samples (default 512). Smaller = more granular.
    min_segment_sec : float
        Minimum segment duration in seconds (default 1.5). Segments
        shorter than this are merged into neighbors.
    return_features : bool
        If True, returns ``(segments, FeatureMatrix)`` for advanced usage.

    Returns
    -------
    list of LabeledSegment, optionally with FeatureMatrix.
    """
    if isinstance(path_or_array, (str, Path)):
        y, sr = load_audio(path_or_array, sr=sr)
    else:
        y = path_or_array

    features = extract_features(y=y, sr=sr, hop_length=hop_length)
    segments = segment_audio(features, min_segment_sec=min_segment_sec)
    labeled = _classify(features, segments)

    if return_features:
        return labeled, features
    return labeled


def _classify(features: FeatureMatrix, segments: List[Segment]) -> List[LabeledSegment]:
    """Indirection so users can override classifier without subclassing."""
    from .classifier import classify_segments
    return classify_segments(features, segments)

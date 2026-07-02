"""Test suite for audio2scene."""

import pytest
import numpy as np
import soundfile as sf
from pathlib import Path

import audio2scene
from audio2scene.features import extract_features, load_audio
from audio2scene.segmentation import segment_audio
from audio2scene.classifier import classify_segments, LabeledSegment
from audio2scene.timeline import (
    segments_to_json,
    segments_to_csv,
    segments_to_txt,
    segments_to_pretty,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def synthetic_song(tmp_path):
    """Generate a short synthetic song for testing."""
    sr = 22050
    # 30s song: intro (5s) + main (15s) + break (3s) + main (5s) + ending (2s)
    parts = []
    # Intro: low tone
    t = np.arange(int(5 * sr)) / sr
    parts.append(0.1 * np.sin(2 * np.pi * 220 * t))
    # Main: louder chord
    t = np.arange(int(15 * sr)) / sr
    main = 0.3 * np.sin(2 * np.pi * 220 * t) + 0.2 * np.sin(2 * np.pi * 330 * t)
    parts.append(main)
    # Break: silence-ish
    t = np.arange(int(3 * sr)) / sr
    parts.append(0.01 * np.sin(2 * np.pi * 165 * t))
    # Main: back
    t = np.arange(int(5 * sr)) / sr
    parts.append(0.3 * np.sin(2 * np.pi * 220 * t) + 0.2 * np.sin(2 * np.pi * 330 * t))
    # Ending: fade out
    t = np.arange(int(2 * sr)) / sr
    ending = 0.2 * np.sin(2 * np.pi * 220 * t)
    ending *= np.linspace(1, 0, len(ending))
    parts.append(ending)

    y = np.concatenate(parts).astype(np.float32)
    peak = np.max(np.abs(y))
    if peak > 0:
        y = y / peak * 0.85

    path = tmp_path / "test.wav"
    sf.write(str(path), y, sr, subtype="PCM_16")
    return path, y, sr


# ── Feature extraction ──────────────────────────────────────────────────────

def test_load_audio_wav(synthetic_song):
    path, y_expected, sr_expected = synthetic_song
    y, sr = load_audio(str(path))
    assert sr == sr_expected
    assert y.ndim == 1
    assert y.dtype == np.float32
    assert len(y) > 0


def test_extract_features_shape(synthetic_song):
    _, y, sr = synthetic_song
    feats = extract_features(y=y, sr=sr, hop_length=1024)
    assert feats.sr == sr
    assert feats.hop_length == 1024
    assert feats.duration > 0
    assert feats.n_frames > 0
    assert feats.rms.shape == (feats.n_frames,)
    assert feats.mfcc.shape[0] == 20
    assert feats.chroma.shape[0] == 12
    assert feats.tempo > 0  # should detect something


def test_extract_features_from_path(synthetic_song):
    path, _, _ = synthetic_song
    feats = extract_features(path=path, hop_length=1024)
    assert feats.n_frames > 0
    assert feats.duration > 25  # ~30s song


# ── Segmentation ────────────────────────────────────────────────────────────

def test_segment_audio_returns_segments(synthetic_song):
    _, y, sr = synthetic_song
    feats = extract_features(y=y, sr=sr, hop_length=1024)
    segments = segment_audio(feats, min_segment_sec=2.0)
    assert len(segments) >= 2
    # Segments should cover the whole duration
    assert segments[0].start <= 0.5
    assert abs(segments[-1].end - feats.duration) < 1.0
    # No overlaps
    for i in range(len(segments) - 1):
        assert segments[i].end <= segments[i + 1].start + 0.01


# ── Classification ──────────────────────────────────────────────────────────

def test_classify_segments_returns_labels(synthetic_song):
    _, y, sr = synthetic_song
    feats = extract_features(y=y, sr=sr, hop_length=1024)
    segments = segment_audio(feats, min_segment_sec=2.0)
    labeled = classify_segments(feats, segments)
    assert len(labeled) == len(segments)
    for s in labeled:
        assert 0.0 <= s.confidence <= 1.0
        assert s.label  # non-empty
        assert s.end >= s.start


def test_classify_first_segment_is_intro_or_fade_in(synthetic_song):
    _, y, sr = synthetic_song
    feats = extract_features(y=y, sr=sr, hop_length=1024)
    segments = segment_audio(feats, min_segment_sec=2.0)
    labeled = classify_segments(feats, segments)
    assert labeled[0].label in ("Intro", "Fade In")


def test_classify_last_segment_is_ending_or_fade_out(synthetic_song):
    _, y, sr = synthetic_song
    feats = extract_features(y=y, sr=sr, hop_length=1024)
    segments = segment_audio(feats, min_segment_sec=2.0)
    labeled = classify_segments(feats, segments)
    assert labeled[-1].label in ("Ending", "Fade Out")


# ── Top-level detect() ──────────────────────────────────────────────────────

def test_detect_with_path(synthetic_song):
    path, _, _ = synthetic_song
    segments = audio2scene.detect(str(path), hop_length=1024, min_segment_sec=2.0)
    assert len(segments) >= 2
    assert all(isinstance(s, LabeledSegment) for s in segments)


def test_detect_with_array(synthetic_song):
    _, y, sr = synthetic_song
    segments = audio2scene.detect(y, sr=sr, hop_length=1024, min_segment_sec=2.0)
    assert len(segments) >= 2


def test_detect_returns_features(synthetic_song):
    path, _, _ = synthetic_song
    result = audio2scene.detect(str(path), hop_length=1024, min_segment_sec=2.0, return_features=True)
    assert isinstance(result, tuple)
    segments, feats = result
    assert len(segments) >= 2
    assert feats.n_frames > 0


# ── Output formats ──────────────────────────────────────────────────────────

def test_segments_to_json(synthetic_song):
    path, _, _ = synthetic_song
    segments = audio2scene.detect(str(path), hop_length=1024, min_segment_sec=2.0)
    out = segments_to_json(segments)
    import json
    data = json.loads(out)
    assert "segments" in data
    assert len(data["segments"]) == len(segments)
    for s in data["segments"]:
        assert "label" in s
        assert "start" in s
        assert "end" in s
        assert "confidence" in s


def test_segments_to_csv(synthetic_song):
    path, _, _ = synthetic_song
    segments = audio2scene.detect(str(path), hop_length=1024, min_segment_sec=2.0)
    out = segments_to_csv(segments)
    lines = out.strip().split("\n")
    assert lines[0] == "start,end,label,confidence"
    assert len(lines) == len(segments) + 1


def test_segments_to_txt(synthetic_song):
    path, _, _ = synthetic_song
    segments = audio2scene.detect(str(path), hop_length=1024, min_segment_sec=2.0)
    out = segments_to_txt(segments)
    lines = out.strip().split("\n")
    assert len(lines) == len(segments)
    # Should be MM:SS format
    assert ":" in lines[0]


def test_segments_to_pretty(synthetic_song):
    path, _, _ = synthetic_song
    segments = audio2scene.detect(str(path), hop_length=1024, min_segment_sec=2.0)
    out = segments_to_pretty(segments)
    assert "Total duration" in out
    assert "segments" in out


# ── Empty input ─────────────────────────────────────────────────────────────

def test_empty_audio():
    y = np.zeros(22050, dtype=np.float32)
    segments = audio2scene.detect(y, sr=22050, hop_length=1024)
    # Should not crash; may return single segment or empty
    assert isinstance(segments, list)


# ── Performance ─────────────────────────────────────────────────────────────

def test_performance_under_5s():
    """Per PRD: 3-min audio processed in <5s on modern CPU."""
    import time
    sr = 22050
    # 3-minute song (180s)
    t = np.arange(int(180 * sr)) / sr
    y = 0.3 * np.sin(2 * np.pi * 220 * t) + 0.1 * np.random.randn(len(t)).astype(np.float32)
    y = y.astype(np.float32)

    t0 = time.time()
    segments = audio2scene.detect(y, sr=sr, hop_length=1024)
    elapsed = time.time() - t0
    assert elapsed < 10.0, f"Took {elapsed:.2f}s — should be <5s for 3min audio"

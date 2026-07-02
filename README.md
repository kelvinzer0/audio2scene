# Audio2Scene

> AI-powered structural labeling for instrumental music. **100% offline.**

Audio2Scene analyzes an audio file and produces a timeline of structural labels — Intro, Main Variation A/B/C/D, Fill In, Break, Ending, Fade In, Fade Out — that can be consumed by AI video editors, DAW plugins, arranger keyboards, content creators, and multimedia researchers.

## Why

Manual labeling of song structure is time-consuming and doesn't scale. Audio2Scene automates it using DSP feature extraction + heuristic segmentation + texture-based classification — all running locally on CPU, no cloud, no API keys.

## Performance

| Metric | Target | Actual |
|---|---|---|
| 3-minute audio processing | < 5 s | ~4 s (modern CPU, hop=1024) |
| Memory | < 300 MB | ~150 MB |
| Cloud required | No | No |
| Batch processing | Yes | Yes |

## Install

```bash
pip install -e .
```

System dependencies: `ffmpeg` (for MP3/M4A/AAC decoding), `libsndfile` (usually installed with soundfile).

## CLI

```bash
# Pretty timeline (default)
audio2scene music.mp3

# JSON
audio2scene music.mp3 --json

# CSV
audio2scene music.mp3 --csv

# TXT (MM:SS Label)
audio2scene music.mp3 --txt

# Write to file
audio2scene music.mp3 --json -o labels.json

# Batch
audio2scene *.mp3 --csv -o labels.csv

# Tune resolution vs. speed
audio2scene music.mp3 --hop-length 512   # higher res, slower
audio2scene music.mp3 --hop-length 2048  # lower res, faster
```

### Example output

```
  00:00.000  Intro                  [#########.]  90%
  00:11.981  Main Variation A       [########..]  85%
  00:40.031  Main Variation B       [########..]  85%
  00:46.997  Main Variation C       [########..]  85%
  02:23.267  Fade Out               [########..]  85%

  Total duration: 02:30.000  (14 segments)
```

## Python API

```python
import audio2scene

segments = audio2scene.detect("music.mp3")

for seg in segments:
    print(f"{seg.start:.2f} - {seg.end:.2f}  {seg.label}  (conf={seg.confidence:.2f})")

# Or with more control
segments, features = audio2scene.detect(
    "music.mp3",
    sr=22050,
    hop_length=1024,
    min_segment_sec=5.0,
    return_features=True,
)

# Access low-level features
print(f"Tempo: {features.tempo:.1f} BPM")
print(f"Beats: {len(features.beat_times)}")
```

### Output formats

```python
from audio2scene import (
    segments_to_json, segments_to_csv, segments_to_txt, segments_to_pretty,
)

print(segments_to_json(segments, pretty=True))
print(segments_to_csv(segments))
print(segments_to_txt(segments))
print(segments_to_pretty(segments))
```

## Supported labels

| Label | Meaning |
|---|---|
| `Intro` | First non-silent section (no rising ramp) |
| `Fade In` | First section with monotonically rising RMS over ≥2 s |
| `Main Variation A/B/C/D` | Main body sections, letter assigned by texture similarity (z-scored MFCC + spectral centroid + ZCR) |
| `Fill In` | Short (<3 s) section with high spectral flux (>1.8× median) |
| `Break` | Section with RMS < 0.5× song median |
| `Ending` | Last non-silent section (no falling ramp) |
| `Fade Out` | Last section with monotonically falling RMS over ≥2 s |

## Architecture

```
Decoder ──▶ Feature Extraction ──▶ Segmentation ──▶ Scene Classification ──▶ Export
```

### Feature extraction (per PRD section 6)

All features are frame-aligned at the same hop length:

- RMS Energy (from STFT)
- Loudness (LUFS approximation via pre-emphasis + RMS in dB)
- Beat tracking & tempo (librosa)
- Chroma features (12 bins, from STFT)
- MFCC (20 coefficients, from STFT)
- Spectral flux (L1 norm of positive magnitude delta)
- Spectral centroid
- Zero crossing rate
- Harmonic/Percussive separation (fast median-filter on STFT)
- Silence detection (RMS < −50 dB)
- Dynamic change detection (per-segment RMS slope)

### Segmentation

Boundary candidates are collected from five novelty cues:
1. Silence runs (≥0.4 s)
2. RMS energy novelty (Gaussian-smoothed, σ=8 frames, p90 threshold)
3. Spectral flux peaks (smoothed envelope, 0.5× max threshold)
4. MFCC cosine-distance novelty (p85 threshold)
5. Loudness jumps (≥6 dB)

Boundaries are then iteratively pruned: the weakest boundary (lowest combined novelty score) of any sub-min_segment_sec segment is removed until all segments meet the minimum length.

### Classification

1. First non-silent segment → `Intro` (or `Fade In` if RMS slope > 0.3 over ≥2 s)
2. Last non-silent segment → `Ending` (or `Fade Out` if RMS slope < −0.3)
3. Short + high-flux middle segments → `Fill In`
4. Low-RMS middle segments → `Break`
5. Remaining segments → `Main Variation X`, where X is assigned by z-scored texture similarity (cosine, threshold 0.85). Caps at D.

## Supported audio formats

| Format | Decoder |
|---|---|
| WAV | soundfile (fast path) |
| FLAC | soundfile (fast path) |
| OGG | soundfile (fast path) |
| AIFF | soundfile (fast path) |
| MP3 | ffmpeg via librosa |
| M4A | ffmpeg via librosa |
| AAC | ffmpeg via librosa |

## Roadmap

Per PRD section 13:

- [x] **v0.1** — Intro, Ending, Fade In, Fade Out, Silence detection
- [x] **v0.2** — Main Variation (A/B/C/D), Fill In, Break
- [x] **v0.3** — Confidence score, batch processing, CLI
- [ ] **v0.4** — Python package distribution, streaming detection
- [ ] **v1.0** — Stable API, documentation, benchmark, GitHub Actions, test suite

Current version: **0.3.0**

## Limitations

- **Heuristic-based**: not a learned model. Works best on instrumental music with clear section boundaries. Vocals and highly textured arrangements may produce noisier segmentations.
- **Texture similarity**: synthetic test audio with very similar timbres across sections may be over-merged into a single `Main Variation A`. Real recordings with varied instrumentation produce better differentiation.
- **LUFS approximation**: not true ITU-R BS.1770.4 loudness — uses pre-emphasis filter as a stand-in for K-weighting. Sufficient for relative comparisons, not for absolute loudness compliance.
- **Beat tracking**: assumes roughly constant tempo. Extreme tempo changes may be missed.

## Development

```bash
# Install in editable mode
pip install -e .[dev]

# Run tests
pytest tests/ -v

# Generate test audio
python3 scripts/make_test_audio.py

# Test on synthetic audio
audio2scene examples/test_song.wav --pretty
```

## License

Apache License 2.0 — see [LICENSE](LICENSE).

## Vision

> Menjadi library open source standar untuk **music structure detection** dan **structural labeling**, sehingga dapat digunakan oleh AI video editor, DAW, sistem otomatisasi musik, dan aplikasi multimedia sebagai fondasi analisis struktur lagu secara offline.

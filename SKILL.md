# SKILL.md — audio2scene

> **Skill manifest for AI agents.** This file tells an agent **when** to use audio2scene, **how** to invoke it, and **what to expect** back. Read this before deciding whether to load the heavier `README.md` / source code.

---

## Skill identity

| Field | Value |
|---|---|
| Name | `audio2scene` |
| Version | 0.4.0 |
| Type | Local CLI + Python library |
| License | Apache-2.0 |
| Repo | https://github.com/kelvinzer0/audio2scene |
| Cloud required | No |
| Install | `pip install -e .` (or `pip install audio2scene` once published) |

---

## What it does

Detects the **structural sections** of an instrumental audio file and returns labeled timestamps:

```
Intro → Main A → Fill In → Main B → Break → Main C → Ending → Fade Out
```

Starting **v0.4**, also produces **video editor effect events** (Cut / Flash / Zoom / Glitch / Fade) by mapping beats, onsets, and segment intensity to NLE-ready transitions.

Useful as a **upstream primitive** for: AI video editors, DAW automation, arranger keyboards, music visualization, multimedia research, batch music tagging pipelines.

## Algorithms implemented

| Algorithm | Purpose | Where |
|---|---|---|
| **FFT / STFT** | Time-frequency representation (all features derived from this) | `features.py:librosa.stft` |
| **Beat Tracking** (librosa.beat.beat_track) | Detect beats for cut/transition timing | `features.py` |
| **Onset Detection** (librosa.onset.onset_detect) | Detect attack starts (kick/snare/cymbal/drop) | `features.py` |
| **Novelty Detection** (RMS/Flux/MFCC/Loudness novelty) | Detect structural boundaries (intro/verse/chorus/outro) | `segmentation.py` |
| **Spectral Flux** | Measure spectral change between frames; transition detector | `features.py` |
| **RMS Energy / Loudness (LUFS approx)** | Volume trajectory; dramatic transition trigger | `features.py` |
| **MFCC** | Timbre recognition; segment similarity | `features.py` |
| **Chromagram** | Harmony / chord change detection | `features.py` |
| **HPSS** (median-filter on STFT) | Harmonic / percussive separation | `features.py` |
| **ZCR** | Noisiness / brightness | `features.py` |
| **Intensity Scoring** | Composite 0..1 score per segment (0.6×RMS + 0.4×Flux) | `classifier.py` |
| **Effect Mapping** | Beat/Onset/Segment → Cut/Flash/Zoom/Glitch/Fade events | `video_editor.py` |

---

## When to trigger this skill

Trigger if **any** of these match:

| Pattern | Example user request |
|---|---|
| "label song structure" | "Label the structure of this MP3" |
| "detect sections of audio" | "Find intro / verse / chorus timestamps" |
| "split music into scenes" | "Break this track into scenes for my video editor" |
| "music segmentation" | "Segment this instrumental into parts" |
| "generate timeline from audio" | "I need a timeline of sections for automation" |
| "find break / fill / intro timestamps" | "Where are the breaks in this song?" |
| Batch: "process folder of MP3s" | "Tag every track in /music/*.mp3" |

### Do NOT trigger if

| Pattern | Why |
|---|---|
| User asks for **transcription / notes** | audio2scene is structural, not pitch transcription — use `basic-pitch` instead |
| User asks for **beat grid only** | Use `librosa.beat.beat_track` directly |
| User asks for **vocal separation** | Use `spleeter` / `demucs` |
| User asks for **genre classification** | audio2scene does not classify genre |
| User asks for **tempo only** | Run `librosa.beat.tempo` — 5 lines of code, no need for this skill |
| User asks for **lyrics** | Out of scope |

---

## Video editor pipeline (v0.4+)

The full AI Video Editor pipeline (per industry standard) is now built-in:

```
FFT/STFT  →  Spectral Flux  →  Beat + Onset Detection
                                     ↓
                              Segmentation
                                     ↓
                            Intensity Scoring
                                     ↓
                          Effect Mapping
                                     ↓
   Beat kecil    → Cut
   Beat kuat     → Flash
   Build-up      → Zoom
   Drop          → Glitch
   Ending        → Fade Out
   Intro         → Fade In
   Break         → Hold
   First segment → Title
```

### CLI

```bash
# Get video editor events as JSON
audio2scene song.mp3 --video-editor -o events.json

# Tune beat / onset strategy
audio2scene song.mp3 --video-editor --beat-strategy downbeat_only --onset-strategy strong_only

# Skip fade/title events
audio2scene song.mp3 --video-editor --no-fades --no-title
```

### Python API

```python
import audio2scene

segments, feats = audio2scene.detect("song.mp3", return_features=True)
events = audio2scene.map_video_events(segments, feats)

for ev in events:
    print(f"{ev.time:.2f}s  {ev.effect:<8} intensity={ev.intensity:.2f}  ({ev.segment_label})")

# Stats
summary = audio2scene.events_summary(events)
# {'n_events': 808, 'by_effect': {'Cut': 770, 'Flash': 34, ...}, 'density_per_sec': 3.77}
```

### VideoEvent schema

```json
{
  "time": 1.533,
  "effect": "Cut",
  "intensity": 0.366,
  "segment_label": "Main Variation A",
  "duration": 0.0,
  "source": "beat",
  "metadata": {"beat_index": 0, "beat_strength": 1.3247}
}
```

Effect vocabulary:

| Effect | When triggered | Typical NLE action |
|---|---|---|
| `Cut` | Beat (small) or onset | Hard cut to next shot |
| `Flash` | Beat (strong) or strong onset | White flash transition (200-500ms) |
| `Zoom` | Build-up segment (rising RMS) | Slow zoom-in over segment duration |
| `Glitch` | Drop (sudden high after low intensity) | Digital glitch effect (1s) |
| `Hold` | Break segment | Hold on wide shot |
| `Fade In` | Intro / Fade In segment start | Fade from black (2s) |
| `Fade Out` | Ending / Fade Out segment start | Fade to black (3s) |
| `Title` | First segment start + 0.5s | Title card overlay (3s) |

---

## Quick start (agent-facing)

### Step 1 — verify install

```bash
audio2scene --version
# Expected: audio2scene 0.3.0
```

If missing, install:
```bash
cd /home/z/my-project/audio2scene && pip install --break-system-packages -e .
```

### Step 2 — single file

```bash
# Default: pretty timeline to stdout
audio2scene path/to/song.mp3

# Structured output
audio2scene song.mp3 --json -o labels.json
audio2scene song.mp3 --csv  -o labels.csv
audio2scene song.mp3 --txt  -o labels.txt
```

### Step 3 — batch (multiple files)

```bash
audio2scene *.mp3 --json -o labels/
# writes labels/song1.json, labels/song2.json, ...
```

### Step 4 — Python API (for chaining)

```python
import audio2scene

segments = audio2scene.detect("song.mp3")
for s in segments:
    print(f"{s.start:.2f}-{s.end:.2f}  {s.label}  (conf={s.confidence:.2f})")
```

---

## Output schema

### LabeledSegment

```python
@dataclass
class LabeledSegment:
    label: str           # e.g. "Main Variation A"
    start: float         # seconds
    end: float           # seconds
    confidence: float    # 0.0 - 1.0
```

### Label vocabulary (closed set)

| Label | When |
|---|---|
| `Intro` | First non-silent section |
| `Fade In` | First section with rising RMS ≥2s |
| `Main Variation A` | First main section |
| `Main Variation B/C/D` | Distinct texture (z-scored MFCC cosine < 0.85) |
| `Fill In` | Short (<3s) + high spectral flux (>1.8× median) |
| `Break` | RMS < 0.5× song median |
| `Ending` | Last non-silent section |
| `Fade Out` | Last section with falling RMS ≥2s |

### JSON shape

```json
{
  "segments": [
    {"label": "Intro",            "start": 0.0,    "end": 12.63, "confidence": 0.98},
    {"label": "Main Variation A", "start": 12.63,  "end": 41.28, "confidence": 0.95}
  ]
}
```

### CSV shape

```
start,end,label,confidence
0.0,12.63,Intro,0.98
12.63,41.28,Main Variation A,0.95
```

### TXT shape (MM:SS Label)

```
00:00 Intro
00:12 Main Variation A
00:41 Fill In
```

---

## Tunable parameters

| Flag | Default | Effect |
|---|---|---|
| `--hop-length` | 1024 | Smaller = higher resolution + slower (512 ≈ 2x time, 2048 ≈ 0.5x time) |
| `--min-segment` | 5.0 | Min segment length in seconds. Raise to 8-10 for cleaner output on noisy sources |
| `--sr` | 22050 | Sample rate. 16000 = faster + lower quality, 44100 = slower + higher quality |
| `--format` | pretty | One of: `json` / `csv` / `txt` / `pretty` |

**Stable presets:**

```bash
# Fast scan (low res)
audio2scene song.mp3 --hop-length 2048 --min-segment 8.0

# Detailed (slower)
audio2scene song.mp3 --hop-length 512  --min-segment 3.0

# Production JSON output
audio2scene song.mp3 --json --hop-length 1024 --min-segment 5.0 -o labels.json
```

---

## Performance envelope

| Audio length | Wall time (CPU) | Memory |
|---|---|---|
| 30 s  | ~1 s   | ~80 MB |
| 3 min | ~4.6 s | ~150 MB |
| 10 min | ~15 s  | ~250 MB |
| 30 min | ~45 s  | ~600 MB (exceeds 300 MB target) |

For > 30 min audio, consider:
1. Splitting first with `ffmpeg -t 1800 -c copy part1.mp3 ...`
2. Or wait for v0.4 streaming detection (not yet implemented)

---

## Integration patterns

### Pattern A — pre-processing for AI video editor

```python
import audio2scene
segments = audio2scene.detect("bgm.mp3")
# Pass to video editor: each segment = one scene cut point
editor.set_scenes([(s.start, s.end, s.label) for s in segments])
```

### Pattern B — DAW marker export

```python
import audio2scene
segments = audio2scene.detect("song.wav", min_segment_sec=3.0)

# Write as Audacity label track
with open("labels.txt", "w") as f:
    for s in segments:
        f.write(f"{s.start}\t{s.end}\t{s.label}\n")
```

### Pattern C — batch tag a music library

```bash
for f in ~/music/*.mp3; do
  audio2scene "$f" --json -o "labels/$(basename "${f%.mp3}").json" --quiet
done
```

### Pattern D — pipeline with other audio skills

```python
# 1. Separate vocals (different skill)
# 2. Run audio2scene on the instrumental
# 3. Generate per-section spectrograms
import audio2scene
segs = audio2scene.detect("instrumental.wav", return_features=True)
# feats.mfcc, feats.chroma, feats.beat_times all available
```

---

## Failure modes (and how to handle)

| Symptom | Likely cause | Fix |
|---|---|---|
| `FileNotFoundError: ffmpeg` | Compressed format (mp3/m4a) | `apt install ffmpeg` |
| All sections labeled "Main Variation A" | Audio has very uniform texture | Lower `--min-segment` to 3.0 or accept — real songs do this too |
| Too many tiny segments (<5s each) | Noisy source / LFO artifacts | Raise `--min-segment` to 8.0 or 10.0 |
| Empty segments list | Audio is all silence or <2s long | Check `audio2scene song.mp3 --pretty` output |
| Memory error on >30min file | Exceeds 300MB target | Split with ffmpeg first |
| Beat tracking fails (tempo=0) | No clear rhythmic content | Non-fatal — segmentation still works |

---

## Verification (smoke test)

Run this after install to confirm the skill works:

```bash
cd /home/z/my-project/audio2scene
python3 scripts/make_test_audio.py
audio2scene examples/test_song.wav --pretty
# Should show ~14 segments in ~5 seconds
```

---

## Underlying primitives (for advanced agents)

If you need finer control than `audio2scene.detect()`, drop down a layer:

```python
from audio2scene.features import extract_features, load_audio
from audio2scene.segmentation import segment_audio
from audio2scene.classifier import classify_segments

y, sr = load_audio("song.mp3")
feats = extract_features(y=y, sr=sr, hop_length=1024)

# Access raw features
feats.rms                  # (T,) RMS energy per frame
feats.loudness_lufs        # (T,) approximate LUFS
feats.mfcc                 # (20, T)
feats.chroma               # (12, T)
feats.spectral_flux        # (T,)
feats.spectral_centroid    # (T,)
feats.zcr                  # (T,)
feats.harmonic             # (T,) harmonic RMS
feats.percussive           # (T,) percussive RMS
feats.silence              # (T,) bool
feats.tempo                # float BPM
feats.beat_times           # (B,) seconds

# Custom segmentation
segs = segment_audio(feats, min_segment_sec=8.0)

# Custom classifier (override labels)
labeled = classify_segments(feats, segs)
```

---

## Roadmap alignment (PRD section 13)

| Version | Status | Notes |
|---|---|---|
| v0.1 — Intro/Ending/Fade/Silence | ✅ shipped | |
| v0.2 — Main Variation/Fill In/Break | ✅ shipped | |
| v0.3 — Confidence/Batch/CLI | ✅ shipped | |
| v0.4 — Onset detection/Intensity scoring/Video editor mapping | ✅ shipped | current |
| v1.0 — Stable API/docs/benchmark/CI | ⏳ planned | GitHub Actions test workflow still TODO |

---

## Anti-features (do NOT expect)

- ❌ No vocal detection
- ❌ No chord recognition
- ❌ No key detection (use `librosa.key` estimates)
- ❌ No genre classification
- ❌ No mood / emotion tagging
- ❌ No lyrics alignment
- ❌ No beat-grid export (only beat times as feature)
- ❌ No GPU acceleration (CPU only by design — see PRD vision)

---

## Related skills (compose with)

| Skill | Use together for |
|---|---|
| `spleeter` / `demucs` | Separate vocals first → run audio2scene on instrumental |
| `basic-pitch` | Get MIDI notes per section |
| `librosa` | Lower-level DSP if audio2scene's API is too coarse |
| `ffmpeg` | Pre-split long files, format conversion |
| `charts` (matplotlib) | Visualize the timeline as a PNG |

---

## Contact / source of truth

- **Source**: https://github.com/kelvinzer0/audio2scene
- **PRD**: see `README.md` (this file is the agent-facing summary, README is human-facing)
- **License**: Apache-2.0
- **Author**: Kelvin Yuli Andrian

---

**Version of this SKILL.md**: 1.0
**Last updated**: 2026-07-02
**Schema**: ClawHub-compatible skill manifest

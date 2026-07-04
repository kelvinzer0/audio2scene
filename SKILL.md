# SKILL.md — audio2scene

> **Skill manifest for AI agents.** This file tells an agent **when** to use audio2scene, **how** to invoke it, and **what to expect** back.

---

## Skill identity

| Field | Value |
|---|---|
| Name | `audio2scene` |
| Version | 0.5.0 |
| Type | Local CLI + Python library |
| License | Apache-2.0 |
| Repo | https://github.com/kelvinzer0/audio2scene |
| Install | `pipx install git+https://github.com/kelvinzer0/audio2scene.git` |
| Cloud required | No |

---

## What it does

**Auto Video Editor** — takes a `data.json` spec (music + text + videos + images) and produces a ready-to-render Remotion video project with AI-driven typography effects and beat-synced scene cuts.

```
data.json → audio2scene generate-remotion → Remotion project → MP4 video
```

**CRITICAL**: The main command is `generate-remotion`. It takes `data.json` as input (NOT raw audio files). The audio analysis happens internally — you don't need to run it separately.

---

## When to trigger this skill

Trigger if **any** of these match:

| Pattern | Example user request |
|---|---|
| "generate video from json" | "Buat video dari data.json" |
| "auto video editor" | "Generate video otomatis dari music + text" |
| "remotion project generator" | "Buat Remotion project dari spec" |
| "typography video" | "Video dengan efek teks animasi" |
| "music video generator" | "Buat music video dari MP3" |
| "tiktok/reels video" | "Buat video untuk TikTok" |
| "brand video" | "Video pembuka toko dengan logo" |

### Do NOT trigger if

| Pattern | Why |
|---|---|
| User asks for audio transcription | Not what this tool does |
| User asks for beat grid only | Use `audio2scene song.mp3` directly |
| User asks for vocal separation | Use spleeter/demucs instead |
| User asks for genre classification | Not supported |

---

## Quick Start (3 steps)

### Step 1: Install

```bash
pipx install git+https://github.com/kelvinzer0/audio2scene.git
```

### Step 2: Create `data.json`

```json
{
  "music": "https://archive.org/download/.../song.mp3",
  "screen": "1080:1920",
  "duration": "30s",
  "font": "Inter",
  "logo": "https://example.com/logo.png",
  "symbol": "https://example.com/favicon.png",
  "text": ["My Brand", "Are you ready?", "2024", "Thanks for watching"],
  "videos": ["https://cdn.pixabay.com/video/clip1.mp4"],
  "images": ["https://cdn.pixabay.com/photo/bg1.jpg"]
}
```

### Step 3: Generate + Render

```bash
audio2scene generate-remotion -i data.json -o ./my-video --render --scale 0.5
```

Output: `./my-video/out/video.mp4`

---

## data.json Fields

| Field | Required | Default | Description |
|---|---|---|---|
| `music` | ✅ | — | Audio path or URL (mp3/wav/flac) |
| `text` | ✅ | — | Array of strings. Each = 1 scene |
| `screen` | ❌ | `"1280:720"` | `"W:H"`. `"1080:1920"` = TikTok vertical |
| `duration` | ❌ | full song | `30`, `"30s"`, `"2m"` |
| `font` | ❌ | system | Google Font: `"Inter"`, `"Roboto"` |
| `logo` | ❌ | — | Logo URL/path. Animated intro |
| `symbol` | ❌ | — | Favicon URL/path. Corner watermark |
| `videos` | ❌ | `[]` | B-roll URLs/paths |
| `images` | ❌ | `[]` | Background image URLs/paths |

**All fields support both URL (https://...) and local file paths.**

---

## CLI Commands

### Main: `generate-remotion`

```bash
# Generate project only
audio2scene generate-remotion -i data.json -o ./my-video

# Generate + install + render (single command)
audio2scene generate-remotion -i data.json -o ./my-video --render

# Fast render (quarter-res)
audio2scene generate-remotion -i data.json -o ./my-video --render --fast

# HQ render (half-res)
audio2scene generate-remotion -i data.json -o ./my-video --render --scale 0.5

# Render first 30s only
audio2scene generate-remotion -i data.json -o ./my-video --render --frames=0-900
```

### Secondary: audio analysis

```bash
audio2scene song.mp3                    # pretty timeline
audio2scene song.mp3 --json             # JSON segments
audio2scene song.mp3 --video-editor     # video editor events JSON
```

---

## Text → Effect Auto-Selection

Each `text[]` entry is analyzed with regex to pick the best typography effect:

| Rule | Effect | Example text |
|---|---|---|
| Scene 0 (first) | `inline-highlight` | "My Brand" |
| Contains `?` | `typewriter` | "Ready?" |
| Pure digits | `slot-machine-roll` | "2024" |
| Digits + `,.` | `number-wheel` | "1,234.56" |
| Tech keywords | `matrix-decode` | "hack the system" |
| Single UPPERCASE | `rgb-glitch-text` | "HELLO" |
| Conjunctions (for/the/untuk) | `marker-highlight` | "This is for you" |
| 3+ words + 3+ periods | `spring-scale-in` | "Fast. Crisp. Fluid." |
| 2+ sentences | `mask-reveal-up` | "Hello. World." |
| Contains `-` or `·` | `infinite-marquee` | "ship · build" |
| Single word | `shimmer-sweep` | "Tonight" |
| Other | random (14 effects) | "Late night vibes" |

---

## Python API

```python
import audio2scene

# Generate Remotion project
audio2scene.generate_remotion_project("data.json", "./my-video")

# Analyze audio
segments = audio2scene.detect("song.mp3")

# Video editor events
segments, features = audio2scene.detect("song.mp3", return_features=True)
events = audio2scene.map_video_events(segments, features)
```

---

## System dependencies

- `ffmpeg` — audio decoding
- `Node.js 18+` + `npm` — required for `--render` (Remotion)

---

## Anti-features (do NOT expect)

- ❌ No vocal detection / separation
- ❌ No chord / key detection
- ❌ No genre classification
- ❌ No lyrics alignment
- ❌ No GPU acceleration (CPU only)

---

## Related skills

| Skill | Use together for |
|---|---|
| `remocn` | Typography component registry (36 components bundled) |
| `remotion-best-practices` | Remotion video creation patterns |
| `charts` | Visualize audio analysis results |

---

**Version**: 0.5.0
**Last updated**: 2026-07-04

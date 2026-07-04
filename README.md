# Audio2Scene

> **Auto Video Editor** — data.json in, MP4 out. 100% offline, no cloud, no API keys.

Provide music + text + videos + images in a `data.json` → get back a ready-to-render Remotion video with AI-driven typography effects, beat-synced scene cuts, and B-roll.

**Live demo**: https://kelvinzer0.github.io/audio2scene/

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
  "text": [
    "My Brand",
    "Are you ready?",
    "2024",
    "Fast. Crisp. Fluid.",
    "Thanks for watching"
  ],
  "videos": ["https://cdn.pixabay.com/video/clip1.mp4"],
  "images": ["https://cdn.pixabay.com/photo/bg1.jpg"]
}
```

### Step 3: Generate + Render

```bash
audio2scene generate-remotion -i data.json -o ./my-video --render --scale 0.5
```

Output: `./my-video/out/video.mp4` — ready to upload!

---

## How It Works

```
data.json ──→ audio2scene ──→ Remotion project ──→ MP4 video
                  │
                  ├─ Analyze music (beats, segments, intensity)
                  ├─ Map text[] to scenes (regex-based effect selection)
                  ├─ Assign B-roll (videos/images alternate per scene)
                  ├─ Download all URLs (music, videos, images, logo, symbol)
                  └─ Generate Remotion composition with 36 remocn components
```

**Important**: `generate-remotion` is the MAIN command. It takes `data.json` (not raw audio) and produces a complete video project. The audio analysis happens internally — you don't need to run it separately.

---

## data.json Fields

| Field | Required | Default | Description |
|---|---|---|---|
| `music` | ✅ | — | Audio file path or URL (mp3/wav/flac/ogg) |
| `text` | ✅ | — | Array of text strings. Each = 1 scene with auto-selected typography effect |
| `screen` | ❌ | `"1280:720"` | Output resolution: `"W:H"`. Use `"1080:1920"` for TikTok/Reels |
| `duration` | ❌ | full song | Max render length: `30`, `"30s"`, `"2m"` |
| `font` | ❌ | system | Google Font name: `"Inter"`, `"Roboto"`, `"Playfair Display"` |
| `logo` | ❌ | — | Logo URL/path (PNG/SVG). Animated in intro scene |
| `symbol` | ❌ | — | Favicon URL/path (PNG/SVG). Watermark in all scenes |
| `videos` | ❌ | `[]` | B-roll video URLs/paths. Alternate with images per scene |
| `images` | ❌ | `[]` | Background image URLs/paths. Ken Burns animation (4 patterns) |

### Text → Effect Auto-Selection (regex-based)

Each `text[]` entry is analyzed to pick the best typography effect:

| Text content | Effect | Example |
|---|---|---|
| First text (scene 0) | `inline-highlight` | "My Brand" |
| Contains `?` | `typewriter` | "Are you ready?" |
| Pure digits | `slot-machine-roll` | "2024" |
| Digits + comma/period | `number-wheel` | "1,234.56" |
| Tech keywords (hack/encrypt) | `matrix-decode` | "hack the system" |
| Single UPPERCASE word | `rgb-glitch-text` | "HELLO" |
| Conjunctions (for/the/untuk) | `marker-highlight` | "This is for you" |
| 3+ words + 3+ periods | `spring-scale-in` | "Fast. Crisp. Fluid." |
| 2+ sentences | `mask-reveal-up` | "Hello. World." |
| Contains `-` or `·` | `infinite-marquee` | "ship · build · animate" |
| Single word | `shimmer-sweep` | "Tonight" |
| Other | random (14 effects) | "Late night vibes" |

---

## CLI Commands

### Main: `generate-remotion` (auto video editor)

```bash
# Generate project only (no render)
audio2scene generate-remotion -i data.json -o ./my-video

# Generate + install deps + render MP4 (single command)
audio2scene generate-remotion -i data.json -o ./my-video --render

# Fast render (quarter-res, 4x faster)
audio2scene generate-remotion -i data.json -o ./my-video --render --fast

# HQ render (half-res, 4x better quality)
audio2scene generate-remotion -i data.json -o ./my-video --render --scale 0.5

# Render only first 30s
audio2scene generate-remotion -i data.json -o ./my-video --render --scale 0.5 --frames=0-900
```

### Secondary: audio analysis (for developers)

```bash
# Analyze audio structure (segments, beats, events)
audio2scene song.mp3                          # pretty timeline
audio2scene song.mp3 --json                   # JSON output
audio2scene song.mp3 --video-editor -o events.json  # video editor events
```

---

## Install

### Option 1: pipx (recommended)

```bash
pipx install git+https://github.com/kelvinzer0/audio2scene.git
```

### Option 2: pip

```bash
pip install git+https://github.com/kelvinzer0/audio2scene.git
```

### Option 3: From source

```bash
git clone https://github.com/kelvinzer0/audio2scene.git
cd audio2scene
pip install -e .
```

### Verify

```bash
audio2scene --version
# audio2scene 0.5.0
```

### System dependencies

- `ffmpeg` — for MP3/M4A/AAC audio decoding
- `Node.js 18+` + `npm` — required only for `--render` flag (Remotion)

---

## Python API

```python
import audio2scene

# Generate Remotion project from data.json
audio2scene.generate_remotion_project("data.json", "./my-video")

# Or analyze audio directly
segments = audio2scene.detect("song.mp3")
for seg in segments:
    print(f"{seg.start:.1f}s - {seg.end:.1f}s  {seg.label}  (intensity={seg.intensity:.2f})")

# Get video editor events
segments, features = audio2scene.detect("song.mp3", return_features=True)
events = audio2scene.map_video_events(segments, features)
```

---

## What's Inside

- **36 remocn typography components** (shadcn registry) — bundled, no runtime download
- **13 regex rules** for automatic effect selection based on text content
- **4 Ken Burns patterns** for image animation (zoom + pan + parallax glow)
- **12 scene transitions** (fade, slide, zoom, iris, whipPan, pushThrough, focusPull)
- **Beat tracking + onset detection** via librosa
- **Intensity scoring** per segment (RMS + spectral flux composite)
- **Logo intro animation** (scale + glow pulse)
- **Symbol watermark** persistent across all scenes
- **Google Fonts** loaded via `@remotion/google-fonts`
- **URL support** for all assets (music, videos, images, logo, symbol)
- **100% offline** — no cloud, no API keys

---

## Output Structure

```
my-video/
├── package.json              # deps: remotion, @remotion/transitions, @remotion/media
├── tsconfig.json
├── remotion.config.ts        # webpack alias @ → src
├── src/
│   ├── Composition.tsx       # data-driven composition (reads timeline.json)
│   ├── Root.tsx              # dimensions + duration from audio2scene
│   └── components/remocn/    # 36 typography + transition components
└── public/
    ├── audio.mp3             # your music
    ├── timeline.json         # audio2scene analysis + content mapping
    ├── videos/               # B-roll videos
    ├── images/               # background images
    └── assets/               # logo + symbol
```

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).

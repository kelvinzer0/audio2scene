# audio2scene Remotion Preview

Remotion composition that visualizes audio2scene v0.4 video editor events.

## Setup

```bash
cd remotion/
npm install
npx remotion add @remotion/media-utils

# Place audio + events in public/
cp /path/to/song.mp3 public/audio.mp3
audio2scene song.mp3 --video-editor -o public/song.json

# Open Remotion Studio
npx remotion studio --port=3100

# Render to MP4
npx remotion render Audio2ScenePreview out/preview.mp4 --frames=0-900
```

## What it shows

The composition demonstrates the full AI Video Editor pipeline:

- Audio playback synced to timeline
- Per-segment scene background color (changes on segment boundary)
- White flash overlay on Flash events (100ms window)
- Chromatic aberration glitch effect on Glitch events (1s window)
- Title card overlay with fade in/out (3s)
- Fade in/out overlays (2s/3s)
- Live segment label + intensity badge (top-left)
- Stats panel: time, BPM, counts (top-right)
- Waveform visualization (200 bars, bottom)
- Timeline progress bar with event ticks
- Active effect indicator (center-bottom)

## Live demo

Rendered MP4 + frame stills: https://kelvinzer0.github.io/audio2scene/remotion-preview/

## Source

- `src/Root.tsx` — Composition registration (1280x720 @ 30fps, 4254 frames = 141.8s)
- `src/Composition.tsx` — Main composition with all effect overlays
- `public/song.json` — audio2scene events for DEMI - HomeBody (gitignored, run audio2scene to regenerate)
- `public/audio.mp3` — audio file (gitignored, download from archive.org)

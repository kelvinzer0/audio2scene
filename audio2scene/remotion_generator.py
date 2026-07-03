"""
audio2scene.remotion_generator
==============================

Auto Video Editor — turn a data.json spec into a ready-to-render Remotion project.

Input: data.json
  {
    "music": "song.mp3",           # path to audio file
    "screen": "1280:720",          # W:H resolution
    "text": ["Title", "Verse 1", "Chorus", "Outro"],
    "videos": ["clip1.mp4", "clip2.mp4"],
    "images": ["bg1.jpg", "bg2.png"]
  }

Output: a Remotion project folder ready to `npm install && npx remotion render`.

Pipeline:
  1. Run audio2scene on music → segments + events
  2. Parse data.json → content pools
  3. Map content to timeline:
     - Title scene → text[0]
     - Main slices → cycle through videos[]
     - Break segments → cycle through images[] (Ken Burns)
     - Ending → text[-1] + Fade Out
     - Filtered Cut events → random remocn/CSS transitions
  4. Generate Remotion project files (Root.tsx, Composition.tsx, package.json, etc.)
  5. Copy assets to public/

Usage:
  from audio2scene.remotion_generator import generate_remotion_project
  generate_remotion_project("data.json", output_dir="./my-video")

CLI:
  audio2scene generate-remotion --input data.json --output ./my-video
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Tuple

from .classifier import LabeledSegment
from .features import FeatureMatrix, extract_features, load_audio
from .segmentation import Segment, segment_audio
from .classifier import classify_segments
from .video_editor import map_video_events, VideoEvent


# ─── Data models ─────────────────────────────────────────────────────────────


@dataclass
class DataSpec:
    """User-provided spec from data.json.

    This is a DYNAMIC VIDEO GENERATOR, not a music player. The video is
    text-driven: each entry in `text[]` becomes one scene with a random
    typography effect from the remocn registry. Music analysis (audio2scene)
    is used only to time the scene cuts — segment boundaries and beat events
    decide WHEN to switch text, but the visible UI is pure typography.

    Optional `logo` and `symbol` fields enable branded intro animation:
    - `logo`: main brand logo (PNG/SVG/URL) — animated in intro scene
    - `symbol`: favicon/icon (PNG/SVG/URL) — watermark in corner throughout video
    """
    music: str
    screen: str = "1280:720"     # "W:H"
    text: List[str] = None
    videos: List[str] = None
    images: List[str] = None
    duration: Optional[float] = None  # max render duration in seconds (None = full song)
    font: Optional[str] = None  # Google Font name (e.g. "Inter", "JetBrains Mono")
    logo: Optional[str] = None  # path or URL to logo (PNG/SVG) — intro animation
    symbol: Optional[str] = None  # path or URL to symbol/favicon — corner watermark

    @classmethod
    def from_dict(cls, d: dict) -> "DataSpec":
        return cls(
            music=d["music"],
            screen=d.get("screen", "1280:720"),
            text=d.get("text", []) or [],
            videos=d.get("videos", []) or [],
            images=d.get("images", []) or [],
            duration=_parse_duration(d.get("duration")),
            font=d.get("font"),
            logo=d.get("logo"),
            symbol=d.get("symbol"),
        )

    @property
    def dimensions(self) -> Tuple[int, int]:
        w, h = self.screen.split(":")
        return int(w), int(h)


def _parse_duration(value) -> Optional[float]:
    """Parse duration field. Accepts:
    - None / missing → full song
    - int/float (seconds): 120, 60.5
    - str with unit: "120s", "2m", "1.5m", "90s"
    - str number: "120"
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if not s:
            return None
        # Strip trailing unit
        if s.endswith("s"):
            return float(s[:-1])
        if s.endswith("m"):
            return float(s[:-1]) * 60.0
        if s.endswith("h"):
            return float(s[:-1]) * 3600.0
        # Plain number string
        return float(s)
    return None


@dataclass
class SceneSlice:
    """A time slice in the timeline with mapped content.

    This is a DYNAMIC VIDEO scene — pure typography showcase. The `effect`
    field selects which remocn typography component renders the `text`.
    Music analysis only decides WHEN scenes change (via segment/Cut events),
    not WHAT is shown.
    """
    kind: str                       # "text" | "video" | "image" (kind of background)
    start: float                    # seconds
    end: float                      # seconds
    text: Optional[str] = None      # text to display (rendered by typography effect)
    effect: str = "soft-blur-in"    # remocn typography component name
    video: Optional[str] = None     # background video filename (public/videos/)
    image: Optional[str] = None     # background image filename (public/images/)
    # Transition into this slice (from previous)
    transition: str = "fade"        # transition name
    transition_duration_frames: int = 14
    # Optional metadata (kept for debugging, not shown in UI)
    segment_label: str = ""
    segment_intensity: float = 0.0
    segment_intensity_label: str = ""


# ─── Content mapping ─────────────────────────────────────────────────────────


# ─── Typography effect pool (31 remocn components) ───────────────────────────

TYPOGRAPHY_EFFECTS = [
    "soft-blur-in",
    "per-character-rise",
    "bottom-up-letters",
    "top-down-letters",
    "spring-scale-in",
    "micro-scale-fade",
    "scale-down-fade",
    "blur-out-up",
    "focus-blur-resolve",
    "line-by-line-slide",
    "per-word-crossfade",
    "fade-through",
    "shared-axis-y",
    "shared-axis-z",
    "short-slide-right",
    "kinetic-center-build",
    "short-slide-down",
    "staggered-fade-up",
    "mask-reveal-up",
    "tracking-in",
    "inline-highlight",
    "marker-highlight",
    "shimmer-sweep",
    "typewriter",
    "slot-machine-roll",
    "rolling-number",
    "infinite-marquee",
    "perspective-marquee",
    "matrix-decode",
    "rgb-glitch-text",
]

# Scene transition pool (between text scenes)
SCENE_TRANSITIONS = [
    "fade", "slideLeft", "slideRight", "slideUp", "slideDown",
    "zoomIn", "zoomOut", "irisWipe", "whipPan", "whipPanRight",
    "pushThrough", "focusPull",
]


def _seeded_random(seed: str) -> float:
    """Deterministic hash-based random in [0, 1)."""
    h = 0
    for ch in seed:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return (h % 10000) / 10000


def _pick_typography(seed: int) -> str:
    """Deterministic pick from TYPOGRAPHY_EFFECTS (random fallback)."""
    idx = int(_seeded_random(f"typo-{seed}") * len(TYPOGRAPHY_EFFECTS))
    return TYPOGRAPHY_EFFECTS[idx]


# ─── Regex-based typography selection ────────────────────────────────────────
# Advanced text analysis: select effect based on text content, not random.
# Priority order: forced rules > content-based rules > random fallback.

import re as _re

# Kata sambung (Indonesian + English) untuk Marker Highlight
_KATA_SAMBUNG = {
    "for", "untuk", "dari", "oleh", "adalah", "dan", "atau", "karena",
    "sehingga", "supaya", "agar", "jika", "kalau", "when", "while",
    "with", "without", "by", "the", "this", "that",
}

# Kata kunci tech untuk Matrix Decode
_TECH_KEYWORDS = {"hack", "decrypt", "encrypt", "code", "system", "matrix", "cyber", "binary"}

# Random fallback pool (untuk text yang tidak match rule apapun)
_RANDOM_POOL = [
    "soft-blur-in", "per-character-rise", "bottom-up-letters", "top-down-letters",
    "micro-scale-fade", "scale-down-fade", "blur-out-up", "focus-blur-resolve",
    "shared-axis-y", "shared-axis-z", "short-slide-right", "kinetic-center-build",
    "staggered-fade-up", "tracking-in",
]


def pick_typography_by_text(text: str, scene_index: int) -> str:
    """Select typography effect based on text content using regex rules.

    Priority order (first match wins):
      1. Scene pertama (index 0) → Inline Highlight (wajib)
      2. Mengandung tanda tanya '?' → Typewriter
      3. Angka only (pure digits) → Slot Machine Roll
      4. Angka dengan koma/titik (',.' atau '.') → Number Wheel
      5. Angka dengan space (e.g. "1 2 3") → Rolling Number
      6. Mengandung kata tech (hack/decrypt/encrypt) → Matrix Decode
      7. Single word UPPERCASE → RGB Glitch Text
      8. Mengandung kata sambung (for/untuk/dari/oleh/adalah) → Marker Highlight
      9. 3 words + 3 periods (e.g. "Fast. Crisp. Fluid.") → Spring Scale In
     10. 2 kalimat (2+ periods/sentences) → Mask Reveal Up
     11. Mengandung '-' atau '·' (dot separator) → Infinite Marquee
     12. Single word → Shimmer Sweep
     13. Random fallback dari _RANDOM_POOL
    """
    if not text or not text.strip():
        return "soft-blur-in"

    text_stripped = text.strip()
    text_lower = text_stripped.lower()
    words = text_stripped.split()
    word_count = len(words)

    # Rule 1: Scene pertama wajib Inline Highlight
    if scene_index == 0:
        return "inline-highlight"

    # Rule 2: Mengandung tanda tanya → Typewriter
    if "?" in text_stripped:
        return "typewriter"

    # Rule 3-5: Angka-based rules
    # Pure digits (e.g. "2024", "100")
    if _re.fullmatch(r"[\d\s]+", text_stripped) and text_stripped.replace(" ", "").isdigit():
        if " " in text_stripped:
            # Angka dengan space → Rolling Number
            return "rolling-number"
        # Pure angka tanpa space → Slot Machine Roll
        return "slot-machine-roll"

    # Angka dengan koma atau titik (e.g. "1,234.56", "3.14")
    if _re.search(r"\d+[,.]\d+", text_stripped):
        return "number-wheel"

    # Rule 6: Mengandung kata tech → Matrix Decode
    for keyword in _TECH_KEYWORDS:
        if keyword in text_lower:
            return "matrix-decode"

    # Rule 7: Single word UPPERCASE → RGB Glitch Text
    if word_count == 1 and text_stripped.isupper() and text_stripped.isalpha():
        return "rgb-glitch-text"

    # Rule 8: Mengandung kata sambung → Marker Highlight
    text_words_lower = set(text_lower.replace(".", "").replace(",", "").replace("!", "").split())
    if text_words_lower & _KATA_SAMBUNG:
        return "marker-highlight"

    # Rule 9: 3 words + 3 periods (e.g. "Fast. Crisp. Fluid.")
    period_count = text_stripped.count(".")
    if word_count >= 3 and period_count >= 3:
        return "spring-scale-in"

    # Rule 10: 2+ kalimat (2+ periods atau sentence breaks) → Mask Reveal Up
    sentences = _re.split(r"[.!?]+", text_stripped)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) >= 2:
        return "mask-reveal-up"

    # Rule 11: Mengandung '-' atau '·' (dot separator) → Infinite Marquee
    if "-" in text_stripped or "·" in text_stripped or "—" in text_stripped:
        return "infinite-marquee"

    # Rule 12: Single word → Shimmer Sweep
    if word_count == 1:
        return "shimmer-sweep"

    # Rule 13: Random fallback
    idx = int(_seeded_random(f"random-{scene_index}-{text_lower[:20]}") * len(_RANDOM_POOL))
    return _RANDOM_POOL[idx]


def _pick_transition(seed: int) -> str:
    """Deterministic pick from SCENE_TRANSITIONS."""
    idx = int(_seeded_random(f"trans-{seed}") * len(SCENE_TRANSITIONS))
    return SCENE_TRANSITIONS[idx]


def map_content_to_timeline(
    segments: List[LabeledSegment],
    events: List[VideoEvent],
    spec: DataSpec,
    fps: int = 30,
    min_cut_gap_sec: float = 3.0,
    total_duration: Optional[float] = None,
) -> List[SceneSlice]:
    """Map user content (text/videos/images) to a DYNAMIC VIDEO timeline.

    This is a text-driven video generator. Each entry in spec.text[] becomes
    one scene with a random typography effect. Music analysis (segments +
    Cut events) is used only to TIME scene boundaries — when to cut to the
    next text. The visible UI is pure typography (no segment labels,
    no intensity badges, no time/BPM displays).

    Strategy:
    1. Build a list of "cut points" from filtered Cut events (3s rule)
       plus segment boundaries — these are CANDIDATE scene boundaries.
    2. Distribute text[] across the timeline:
       - If len(text) <= len(cut_points): assign one text per cut region
       - Else: split timeline evenly into len(text) scenes
    3. Each scene gets:
       - Random typography effect (deterministic by index)
       - Background: cycle videos[] (or images[] if no videos), fallback gradient
       - Random transition from previous scene
    """
    slices: List[SceneSlice] = []
    if not spec.text:
        # No text → just one video/image scene for the whole duration
        end = total_duration or (segments[-1].end if segments else 30.0)
        video_file = Path(spec.videos[0]).name if spec.videos else None
        image_file = Path(spec.images[0]).name if spec.images else None
        slices.append(SceneSlice(
            kind="video" if video_file else ("image" if image_file else "text"),
            start=0.0, end=end,
            video=video_file, image=image_file,
            text=None, effect="soft-blur-in",
            transition="fade",
        ))
        return slices

    # Determine total duration
    if total_duration is None:
        total_duration = segments[-1].end if segments else 30.0

    n_texts = len(spec.text)

    # === Build candidate cut points from filtered Cut events + segment starts ===
    cuts = sorted(
        [e for e in events if e.effect == "Cut" and e.intensity >= 0.05],
        key=lambda e: e.time,
    )
    filtered_cuts: List[float] = []
    last_cut_time = -1e9
    for c in cuts:
        if c.time - last_cut_time >= min_cut_gap_sec and c.time < total_duration:
            filtered_cuts.append(c.time)
            last_cut_time = c.time

    # Also include segment boundaries as candidate cuts
    seg_starts = [s.start for s in segments if 0 < s.start < total_duration]
    all_cuts = sorted(set(filtered_cuts + seg_starts))

    # === Decide scene boundaries ===
    # Strategy: distribute n_texts scenes across total_duration.
    # Use cut points if we have enough; otherwise split evenly.
    if len(all_cuts) >= n_texts - 1:
        # We have enough cut points — pick n_texts-1 of them, evenly spaced in the list
        # to serve as boundaries between scenes
        if n_texts == 1:
            boundaries: List[float] = []
        else:
            # Pick n_texts-1 cut points spread across the cut list
            step = len(all_cuts) / (n_texts - 1) if n_texts > 1 else 0
            indices = [int(i * step) for i in range(n_texts - 1)]
            indices = sorted(set(indices))  # dedupe
            boundaries = [all_cuts[i] for i in indices]
    else:
        # Not enough cuts — split timeline evenly
        boundaries = [total_duration * (i + 1) / n_texts for i in range(n_texts - 1)]

    # Build scene start/end list
    scene_starts = [0.0] + boundaries
    scene_ends = boundaries + [total_duration]

    # === Assign content per scene ===
    video_idx = 0
    image_idx = 0
    text_idx = 0  # track text index separately from scene index

    for i, (start, end) in enumerate(zip(scene_starts, scene_ends)):
        if end - start < 0.3:
            continue  # skip too-short scenes
        text = spec.text[text_idx] if text_idx < n_texts else None
        # Use text_idx for effect selection (so rule "scene pertama" applies to first TEXT, not first slice)
        effect = pick_typography_by_text(text or "", text_idx)
        if text_idx < n_texts:
            text_idx += 1

        # Background: assign BOTH video AND image per scene (if available)
        # Background component will alternate: even scenes → video, odd scenes → image
        video_file = None
        image_file = None
        if spec.videos:
            video_file = Path(spec.videos[video_idx % len(spec.videos)]).name
            video_idx += 1
        if spec.images:
            image_file = Path(spec.images[image_idx % len(spec.images)]).name
            image_idx += 1
        # Determine kind: prefer "video" if both available (component will alternate)
        bg_kind = "video" if video_file else ("image" if image_file else "text")

        transition = "fade" if i == 0 else _pick_transition(i)
        transition_dur = 14 if i == 0 else 14

        slices.append(SceneSlice(
            kind=bg_kind,
            start=start,
            end=end,
            text=text,
            effect=effect,
            video=video_file,
            image=image_file,
            transition=transition,
            transition_duration_frames=transition_dur,
        ))

    return slices



# ─── Project file templates ──────────────────────────────────────────────────


PACKAGE_JSON = """{
  "name": "audio2scene-remotion-project",
  "version": "1.0.0",
  "description": "Auto-generated Remotion project from audio2scene — dynamic typography video",
  "license": "UNLICENSED",
  "private": true,
  "dependencies": {
    "@remotion/cli": "4.0.484",
    "@remotion/transitions": "4.0.484",
    "@remotion/media": "4.0.484",
    "@remotion/google-fonts": "4.0.484",
    "react": "19.2.3",
    "react-dom": "19.2.3",
    "remotion": "4.0.484",
    "clsx": "^2.1.0",
    "culori": "^4.0.0"
  },
  "devDependencies": {
    "@types/react": "19.2.7",
    "@types/culori": "^4.0.0",
    "typescript": "5.9.3"
  },
  "scripts": {
    "dev": "remotion studio",
    "build": "remotion bundle",
    "render": "remotion render Audio2ScenePreview out/video.mp4",
    "upgrade": "remotion upgrade"
  }
}
"""

TSCONFIG_JSON = """{
  "compilerOptions": {
    "target": "ES2018",
    "module": "commonjs",
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true,
    "lib": ["es2015", "dom"],
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "noUnusedLocals": false,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  },
  "include": ["src/**/*.tsx", "src/**/*.ts"],
  "exclude": ["remotion.config.ts", "node_modules", "src/lib/**"]
}
"""

REMOTION_CONFIG_TS = """import { Config } from "@remotion/cli/config";
import path from "node:path";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setConcurrency(1);

Config.overrideWebpackConfig((config) => {
  return {
    ...config,
    resolve: {
      ...config.resolve,
      alias: {
        ...(config.resolve?.alias || {}),
        "@": path.resolve(process.cwd(), "src"),
      },
    },
  };
});
"""

ROOT_TSX = '''import { Composition } from "remotion";
import { MyComposition } from "./Composition";

// Auto-generated by audio2scene
const FPS = 30;
const DURATION_SEC = {duration_sec};
const DURATION_FRAMES = Math.ceil(DURATION_SEC * FPS);
const WIDTH = {width};
const HEIGHT = {height};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Audio2ScenePreview"
        component={MyComposition}
        durationInFrames={DURATION_FRAMES}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
      />
    </>
  );
};
'''

INDEX_TS = '''import { registerRoot } from "remotion";
import { RemotionRoot } from "./Root";

registerRoot(RemotionRoot);
'''

# Composition.tsx is large — kept in a separate function below
COMPOSITION_TSX_TEMPLATE = '''import React, { useEffect, useState } from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { Video } from "@remotion/media";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import type { TransitionPresentation } from "@remotion/transitions";
import type { TransitionPresentationComponentProps } from "@remotion/transitions";

// ─── Types ──────────────────────────────────────────────────────────────────

interface SceneSlice {
  kind: string;
  start: number;
  end: number;
  segment_label: string;
  segment_intensity: number;
  segment_intensity_label: string;
  text: string | null;
  video: string | null;
  image: string | null;
  transition: string;
  transition_duration_frames: number;
}

interface Timeline {
  title: string;
  duration: number;
  tempo: number;
  n_segments: number;
  n_events: number;
  slices: SceneSlice[];
  waveform: number[];
  segments: Array<{
    label: string;
    start: number;
    end: number;
    intensity: number;
    intensity_label: string;
  }>;
}

// ─── Color palette per segment label ────────────────────────────────────────

const LABEL_COLORS: Record<string, string> = {
  Intro: "#60a5fa",
  "Fade In": "#22d3ee",
  "Main Variation A": "#a855f7",
  "Main Variation B": "#ec4899",
  "Main Variation C": "#fb923c",
  "Main Variation D": "#facc15",
  "Fill In": "#4ade80",
  Break: "#94a3b8",
  Ending: "#818cf8",
  "Fade Out": "#2dd4bf",
};

// ─── Custom transitions ─────────────────────────────────────────────────────

const FadePresentation: React.FC<TransitionPresentationComponentProps<Record<string, unknown>>> = ({
  children, presentationProgress, presentationDirection,
}) => {
  const entering = presentationDirection === "entering";
  const opacity = entering ? presentationProgress : 1 - presentationProgress;
  return <AbsoluteFill style={ opacity }>{children}</AbsoluteFill>;
};

const SlidePresentation: React.FC<TransitionPresentationComponentProps<{ direction: string }>> = ({
  children, presentationProgress, presentationDirection, passedProps,
}) => {
  const { direction = "left" } = passedProps;
  const entering = presentationDirection === "entering";
  const p = presentationProgress;
  const offset = entering ? (1 - p) * 100 : p * -100;
  const transform =
    direction === "left" ? `translateX(${offset}%)` :
    direction === "right" ? `translateX(${-offset}%)` :
    direction === "up" ? `translateY(${offset}%)` :
    `translateY(${-offset}%)`;
  return <AbsoluteFill style={ transform }>{children}</AbsoluteFill>;
};

const ZoomPresentation: React.FC<TransitionPresentationComponentProps<{ mode: string }>> = ({
  children, presentationProgress, presentationDirection, passedProps,
}) => {
  const { mode = "in" } = passedProps;
  const entering = presentationDirection === "entering";
  const p = presentationProgress;
  const scale = entering
    ? (mode === "in" ? 1.5 - p * 0.5 : 0.5 + p * 0.5)
    : (mode === "in" ? 1 + p * 0.5 : 1 - p * 0.5);
  const opacity = entering ? p : 1 - p;
  return <AbsoluteFill style={ scale: `${scale}`, opacity, transformOrigin: "center" }>{children}</AbsoluteFill>;
};

const IrisPresentation: React.FC<TransitionPresentationComponentProps<Record<string, unknown>>> = ({
  children, presentationProgress, presentationDirection,
}) => {
  const entering = presentationDirection === "entering";
  const p = presentationProgress;
  const radius = entering ? p * 150 : (1 - p) * 150;
  const clipPath = `circle(${radius}% at 50% 50%)`;
  return <AbsoluteFill style={ clipPath, WebkitClipPath: clipPath }>{children}</AbsoluteFill>;
};

const WhipPanPresentation: React.FC<TransitionPresentationComponentProps<{ direction: string }>> = ({
  children, presentationProgress, presentationDirection, passedProps,
}) => {
  const { direction = "left" } = passedProps;
  const entering = presentationDirection === "entering";
  const p = presentationProgress;
  const offset = entering ? (1 - p) * 80 : p * -80;
  const sign = direction === "left" ? -1 : 1;
  return (
    <AbsoluteFill style={ transform: `translateX(${offset * sign}%)`, filter: `blur(${Math.sin(p * Math.PI) * 8}px)` }>
      {children}
    </AbsoluteFill>
  );
};

function getTransition(name: string): TransitionPresentation<Record<string, unknown>> {
  switch (name) {
    case "fade": return { component: FadePresentation, props: {} };
    case "slideLeft": return { component: SlidePresentation as any, props: { direction: "left" } };
    case "slideRight": return { component: SlidePresentation as any, props: { direction: "right" } };
    case "slideUp": return { component: SlidePresentation as any, props: { direction: "up" } };
    case "slideDown": return { component: SlidePresentation as any, props: { direction: "down" } };
    case "zoomIn": return { component: ZoomPresentation as any, props: { mode: "in" } };
    case "zoomOut": return { component: ZoomPresentation as any, props: { mode: "out" } };
    case "irisWipe": return { component: IrisPresentation, props: {} };
    case "whipPan": return { component: WhipPanPresentation as any, props: { direction: "left" } };
    case "whipPanRight": return { component: WhipPanPresentation as any, props: { direction: "right" } };
    case "pushThrough": return { component: ZoomPresentation as any, props: { mode: "in" } };
    case "focusPull": return { component: FadePresentation, props: {} };
    default: return { component: FadePresentation, props: {} };
  }
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function fmtTime(t: number): string {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

// ─── Title scene ────────────────────────────────────────────────────────────

const TitleScene: React.FC<{ slice: SceneSlice; timeline: Timeline }> = ({ slice, timeline }) => {
  const frame = useCurrentFrame();
  const fadeOut = interpolate(frame, [60, 90], [1, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={ opacity: fadeOut, backgroundColor: "#0a0a0f" }>
      <AbsoluteFill
        style={
          background: "radial-gradient(circle at center, #a855f740 0%, #0a0a0f 70%)",
        }
      />
      <AbsoluteFill
        style={
          display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center", gap: 24,
          fontFamily: "Inter, system-ui, sans-serif",
        }
      >
        <div
          style={
            color: "#a855f7", fontSize: 16, fontWeight: 600,
            letterSpacing: 6, textTransform: "uppercase",
            opacity: interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" }),
          }
        >
          ◆ Now Playing
        </div>
        <div
          style={
            color: "white", fontSize: 64, fontWeight: 800,
            textAlign: "center", maxWidth: "80%",
            opacity: interpolate(frame, [10, 30], [0, 1], { extrapolateRight: "clamp" }),
            transform: `scale(${interpolate(frame, [10, 30], [0.9, 1], { extrapolateRight: "clamp" })})`,
          }
        >
          {slice.text || timeline.title}
        </div>
        <div
          style={
            marginTop: 16, display: "flex", gap: 24,
            color: "#94a3b8", fontSize: 16, fontFamily: "monospace",
            opacity: interpolate(frame, [30, 60], [0, 1], { extrapolateRight: "clamp" }),
          }
        >
          <span style={ color: "#22d3ee" }>{timeline.tempo} BPM</span>
          <span>·</span>
          <span>{fmtTime(timeline.duration)}</span>
          <span>·</span>
          <span>{timeline.n_segments} segments</span>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// ─── Main scene (with video B-roll) ─────────────────────────────────────────

const MainScene: React.FC<{ slice: SceneSlice; timeline: Timeline }> = ({ slice, timeline }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const localTime = slice.start + frame / fps;
  const color = LABEL_COLORS[slice.segment_label] || "#a855f7";

  return (
    <AbsoluteFill style={ backgroundColor: "#0a0a0f" }>
      {/* Video B-roll (if provided) */}
      {slice.video ? (
        <AbsoluteFill>
          <Video
            src={staticFile(`videos/${slice.video}`)}
            style={ width: "100%", height: "100%", objectFit: "cover" }
            muted
          />
          {/* Dark overlay for text readability */}
          <AbsoluteFill style={ backgroundColor: "rgba(0,0,0,0.4)" } />
        </AbsoluteFill>
      ) : (
        <AbsoluteFill
          style={
            background: `radial-gradient(circle at center, ${color}40 0%, #0a0a0f 70%)`,
          }
        />
      )}

      {/* Segment label (top-left) */}
      <div
        style={
          position: "absolute", top: 30, left: 40,
          fontFamily: "Inter, system-ui, sans-serif",
          opacity: interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" }),
        }
      >
        <div
          style={
            color, fontSize: 11, fontWeight: 700,
            letterSpacing: 3, textTransform: "uppercase", marginBottom: 4,
          }
        >
          {slice.kind === "main" ? "Main" : slice.segment_label}
        </div>
        <div
          style={
            color: "white", fontSize: 24, fontWeight: 800,
            textShadow: "0 2px 12px rgba(0,0,0,0.8)",
          }
        >
          {slice.segment_label}
        </div>
        <div
          style={
            marginTop: 6, padding: "3px 10px",
            backgroundColor: `${color}30`, border: `1px solid ${color}`,
            borderRadius: 4, color, fontSize: 10, fontWeight: 700,
            letterSpacing: 1, textTransform: "uppercase", display: "inline-block",
          }
        >
          {slice.segment_intensity_label}
        </div>
      </div>

      {/* Time (top-right) */}
      <div
        style={
          position: "absolute", top: 30, right: 40,
          textAlign: "right", fontFamily: "monospace", color: "white",
          fontSize: 20, fontWeight: 700,
          textShadow: "0 2px 12px rgba(0,0,0,0.8)",
        }
      >
        {fmtTime(localTime)}
        <span style={ color: "#475569", fontSize: 14 }>{` / ${fmtTime(timeline.duration)}`}</span>
      </div>

      {/* Text overlay (if any) */}
      {slice.text && (
        <AbsoluteFill
          style={
            display: "flex", alignItems: "center", justifyContent: "center",
            pointerEvents: "none",
          }
        >
          <div
            style={
              color: "white", fontSize: 48, fontWeight: 800,
              textAlign: "center", maxWidth: "80%",
              textShadow: "0 4px 24px rgba(0,0,0,0.9)",
              fontFamily: "Inter, system-ui, sans-serif",
              opacity: interpolate(frame, [10, 30, 60, 80], [0, 1, 1, 0], { extrapolateRight: "clamp" }),
            }
          >
            {slice.text}
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};

// ─── Break scene (image with Ken Burns) ─────────────────────────────────────

const BreakScene: React.FC<{ slice: SceneSlice; timeline: Timeline }> = ({ slice, timeline }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const localTime = slice.start + frame / fps;
  const sliceDuration = slice.end - slice.start;
  const progress = (frame / fps) / sliceDuration;

  // Ken Burns: slow zoom + pan
  const scale = 1 + progress * 0.15;
  const translateX = progress * 30 - 15;

  return (
    <AbsoluteFill style={ backgroundColor: "#0a0a0f" }>
      {slice.image ? (
        <AbsoluteFill>
          <Img
            src={staticFile(`images/${slice.image}`)}
            style={
              width: "100%", height: "100%", objectFit: "cover",
              transform: `scale(${scale}) translateX(${translateX}px)`,
            }
          />
          <AbsoluteFill style={ backgroundColor: "rgba(0,0,0,0.5)" } />
        </AbsoluteFill>
      ) : (
        <AbsoluteFill
          style={
            background: "radial-gradient(circle at center, #94a3b840 0%, #0a0a0f 70%)",
          }
        />
      )}

      {/* "Break" label */}
      <AbsoluteFill
        style={
          display: "flex", alignItems: "center", justifyContent: "center",
          fontFamily: "Inter, system-ui, sans-serif",
        }
      >
        <div
          style={
            color: "#94a3b8", fontSize: 14, fontWeight: 700,
            letterSpacing: 6, textTransform: "uppercase",
            opacity: interpolate(frame, [0, 15], [0, 0.8], { extrapolateRight: "clamp" }),
          }
        >
          ◆ Break
        </div>
      </AbsoluteFill>

      {slice.text && (
        <AbsoluteFill
          style={
            display: "flex", alignItems: "flex-end", justifyContent: "center",
            paddingBottom: 120, pointerEvents: "none",
          }
        >
          <div
            style={
              color: "white", fontSize: 36, fontWeight: 800,
              textAlign: "center", maxWidth: "80%",
              textShadow: "0 4px 24px rgba(0,0,0,0.9)",
              opacity: interpolate(frame, [10, 30, 60, 80], [0, 1, 1, 0], { extrapolateRight: "clamp" }),
            }
          >
            {slice.text}
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};

// ─── Ending scene ───────────────────────────────────────────────────────────

const EndingScene: React.FC<{ slice: SceneSlice; timeline: Timeline }> = ({ slice, timeline }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sliceDuration = slice.end - slice.start;
  const progress = (frame / fps) / sliceDuration;

  // Fade to black at end
  const fadeToBlack = interpolate(progress, [0.6, 1.0], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={ backgroundColor: "#0a0a0f" }>
      <AbsoluteFill
        style={
          background: "radial-gradient(circle at center, #818cf840 0%, #0a0a0f 70%)",
        }
      />
      <AbsoluteFill
        style={
          display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center", gap: 24,
          fontFamily: "Inter, system-ui, sans-serif",
          opacity: 1 - fadeToBlack,
        }
      >
        <div
          style={
            color: "#818cf8", fontSize: 14, fontWeight: 700,
            letterSpacing: 6, textTransform: "uppercase",
            opacity: interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" }),
          }
        >
          ◆ Outro
        </div>
        <div
          style={
            color: "white", fontSize: 56, fontWeight: 800,
            textAlign: "center", maxWidth: "80%",
            opacity: interpolate(frame, [10, 30], [0, 1], { extrapolateRight: "clamp" }),
          }
        >
          {slice.text || "Thanks for watching"}
        </div>
      </AbsoluteFill>
      <AbsoluteFill style={ backgroundColor: "black", opacity: fadeToBlack } />
    </AbsoluteFill>
  );
};

// ─── Main composition ───────────────────────────────────────────────────────

export const MyComposition: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const [timeline, setTimeline] = useState<Timeline | null>(null);

  useEffect(() => {
    fetch(staticFile("timeline.json"))
      .then((r) => r.json())
      .then(setTimeline)
      .catch(console.error);
  }, []);

  if (!timeline) {
    return (
      <AbsoluteFill
        style={
          backgroundColor: "#0a0a0f", display: "flex",
          alignItems: "center", justifyContent: "center",
          color: "white", fontFamily: "system-ui, sans-serif",
        }
      >
        Loading timeline...
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill style={ backgroundColor: "#0a0a0f", fontFamily: "Inter, system-ui, sans-serif" }>
      <Audio src={staticFile("audio.mp3")} />

      <TransitionSeries>
        {timeline.slices.map((slice, i) => {
          const dur = Math.max(2, Math.round((slice.end - slice.start) * fps));
          const transitionDur = Math.min(slice.transition_duration_frames, dur - 2);
          return (
            <React.Fragment key={i}>
              <TransitionSeries.Sequence durationInFrames={dur}>
                {slice.kind === "title" ? (
                  <TitleScene slice={slice} timeline={timeline} />
                ) : slice.kind === "break" ? (
                  <BreakScene slice={slice} timeline={timeline} />
                ) : slice.kind === "ending" ? (
                  <EndingScene slice={slice} timeline={timeline} />
                ) : (
                  <MainScene slice={slice} timeline={timeline} />
                )}
              </TransitionSeries.Sequence>
              {i < timeline.slices.length - 1 && (
                <TransitionSeries.Transition
                  presentation={getTransition(slice.transition)}
                  timing={linearTiming({ durationInFrames: transitionDur })}
                />
              )}
            </React.Fragment>
          );
        })}
      </TransitionSeries>
    </AbsoluteFill>
  );
};
'''

README_MD = '''# Auto-generated Remotion Project

Generated by `audio2scene generate-remotion`.

## Setup

```bash
npm install
```

## Preview (interactive)

```bash
npx remotion studio
```

## Render to MP4

```bash
npx remotion render Audio2ScenePreview out/video.mp4
```

## What's inside

- `src/Composition.tsx` — data-driven composition (reads `public/timeline.json`)
- `src/Root.tsx` — composition registration (dimensions + duration from audio2scene)
- `public/audio.mp3` — your music
- `public/timeline.json` — audio2scene analysis + content mapping
- `public/videos/` — your B-roll videos
- `public/images/` — your background images

## Customize

Edit `public/timeline.json` to tweak the timeline, then re-render.
'''


# ─── Main generator function ─────────────────────────────────────────────────


def generate_remotion_project(
    data_json_path: str | Path,
    output_dir: str | Path,
    *,
    hop_length: int = 1024,
    min_segment_sec: float = 5.0,
    fps: int = 30,
) -> Path:
    """Generate a complete Remotion project from data.json spec.

    Parameters
    ----------
    data_json_path : path to data.json
    output_dir : where to create the Remotion project
    hop_length, min_segment_sec : audio2scene params
    fps : frames per second for the composition

    Returns
    -------
    Path to the generated project directory.
    """
    data_json_path = Path(data_json_path)
    output_dir = Path(output_dir)

    # 1. Load spec
    spec = DataSpec.from_dict(json.loads(data_json_path.read_text()))

    # Resolve music path relative to data.json
    music_path = data_json_path.parent / spec.music
    if not music_path.exists():
        raise FileNotFoundError(f"Music file not found: {music_path}")

    # 2. Run audio2scene
    print(f"[audio2scene] Analyzing {music_path.name}...")
    y, sr = load_audio(str(music_path))
    features = extract_features(y=y, sr=sr, hop_length=hop_length)
    segments = segment_audio(features, min_segment_sec=min_segment_sec)
    labeled = classify_segments(features, segments)
    events = map_video_events(labeled, features)
    print(f"[audio2scene] {len(labeled)} segments, {len(events)} events, {features.tempo:.1f} BPM")

    # 2b. Apply duration limit if specified in data.json
    # Truncates audio, segments, events, and features to the requested duration.
    # Useful for rendering short previews (e.g. duration: "60s") without full song.
    max_duration = spec.duration
    if max_duration is not None and max_duration < features.duration:
        print(f"[audio2scene] Limiting render to {max_duration:.1f}s (full song: {features.duration:.1f}s)")
        # Truncate audio samples
        y = y[: int(max_duration * sr)]
        # Re-extract features from truncated audio (so duration field is correct)
        features = extract_features(y=y, sr=sr, hop_length=hop_length)
        # Truncate segments: keep those starting before max_duration, clamp end
        truncated_segments: List[Segment] = []
        for seg in segments:
            if seg.start >= max_duration:
                break
            new_end = min(seg.end, max_duration)
            if new_end > seg.start:
                truncated_segments.append(Segment(start=seg.start, end=new_end))
        segments = truncated_segments
        # Re-classify on truncated segments (intensity needs song-level stats from truncated audio)
        labeled = classify_segments(features, segments)
        # Truncate events: keep those before max_duration
        events = [e for e in events if e.time < max_duration]
        print(f"[audio2scene] After truncation: {len(labeled)} segments, {len(events)} events, duration={features.duration:.1f}s")

    # 3. Map content to timeline (text-driven video generator)
    slices = map_content_to_timeline(
        labeled, events, spec, fps=fps,
        total_duration=features.duration,
    )
    print(f"[audio2scene] Mapped {len(slices)} text scenes")

    # 5. Build timeline.json
    width, height = spec.dimensions
    timeline = {
        "title": Path(spec.music).stem,
        "duration": round(features.duration, 3),
        "tempo": round(float(features.tempo), 1),
        "fps": fps,
        "width": width,
        "height": height,
        "font": spec.font,  # Google Font name (e.g. "Inter") or null
        "slices": [asdict(s) for s in slices],
    }

    # 6. Create project structure
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "src").mkdir(exist_ok=True)
    (output_dir / "public").mkdir(exist_ok=True)
    (output_dir / "public" / "videos").mkdir(exist_ok=True)
    (output_dir / "public" / "images").mkdir(exist_ok=True)

    # 7. Write project files
    (output_dir / "package.json").write_text(PACKAGE_JSON)
    (output_dir / "tsconfig.json").write_text(TSCONFIG_JSON)
    (output_dir / "remotion.config.ts").write_text(REMOTION_CONFIG_TS)
    (output_dir / "README.md").write_text(README_MD)

    (output_dir / "src" / "index.ts").write_text(INDEX_TS)
    (output_dir / "src" / "Root.tsx").write_text(
        ROOT_TSX.replace("{duration_sec}", str(features.duration))
        .replace("{width}", str(width))
        .replace("{height}", str(height))
    )
    # Composition.tsx — read from templates/Composition.tsx (clean JSX)
    template_dir = Path(__file__).parent / "templates"
    (output_dir / "src" / "Composition.tsx").write_text(
        (template_dir / "Composition.tsx").read_text()
    )
    # Copy typography components (remocn registry) to output project
    components_src = template_dir / "components" / "remocn"
    components_dst = output_dir / "src" / "components" / "remocn"
    components_dst.mkdir(parents=True, exist_ok=True)
    if components_src.exists():
        for f in components_src.glob("*.tsx"):
            shutil.copy(str(f), str(components_dst / f.name))
    # Copy remocn-ui lib (shared dependency)
    lib_src = template_dir / "lib"
    lib_dst = output_dir / "src" / "lib"
    lib_dst.mkdir(parents=True, exist_ok=True)
    if lib_src.exists():
        for f in lib_src.rglob("*"):
            if f.is_file():
                rel = f.relative_to(lib_src)
                dst = lib_dst / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(str(f), str(dst))

    # 8. Copy assets
    shutil.copy(str(music_path), str(output_dir / "public" / "audio.mp3"))
    (output_dir / "public" / "timeline.json").write_text(
        json.dumps(timeline, indent=2, ensure_ascii=False)
    )

    # Copy videos
    for v in spec.videos:
        v_path = data_json_path.parent / v
        if v_path.exists():
            shutil.copy(str(v_path), str(output_dir / "public" / "videos" / v_path.name))
        else:
            print(f"  [warn] video not found: {v_path}")

    # Copy images
    for img in spec.images:
        img_path = data_json_path.parent / img
        if img_path.exists():
            shutil.copy(str(img_path), str(output_dir / "public" / "images" / img_path.name))
        else:
            print(f"  [warn] image not found: {img_path}")

    # Download/copy logo + symbol (support URL or local path)
    import urllib.request
    def _fetch_asset(url_or_path: str, dest_name: str) -> Optional[str]:
        """Download URL or copy local file to public/assets/. Return filename or None."""
        dest = output_dir / "public" / "assets" / dest_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            if url_or_path.startswith(("http://", "https://")):
                # Download from URL
                req = urllib.request.Request(url_or_path, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    dest.write_bytes(r.read())
                print(f"  [logo/symbol] downloaded: {dest_name} from {url_or_path[:60]}...")
                return dest_name
            else:
                # Local file
                local = data_json_path.parent / url_or_path
                if local.exists():
                    shutil.copy(str(local), str(dest))
                    print(f"  [logo/symbol] copied: {dest_name}")
                    return dest_name
                else:
                    print(f"  [warn] logo/symbol not found: {local}")
                    return None
        except Exception as e:
            print(f"  [warn] failed to fetch {dest_name}: {e}")
            return None

    logo_file = None
    symbol_file = None
    if spec.logo:
        # Determine extension from URL/path
        ext = ".png"
        low = spec.logo.lower()
        if ".svg" in low: ext = ".svg"
        elif ".jpg" in low or ".jpeg" in low: ext = ".jpg"
        elif ".webp" in low: ext = ".webp"
        logo_file = _fetch_asset(spec.logo, f"logo{ext}")
    if spec.symbol:
        ext = ".png"
        low = spec.symbol.lower()
        if ".svg" in low: ext = ".svg"
        elif ".jpg" in low or ".jpeg" in low: ext = ".jpg"
        elif ".webp" in low: ext = ".webp"
        symbol_file = _fetch_asset(spec.symbol, f"symbol{ext}")

    # Update timeline.json dengan logo/symbol info
    timeline["logo"] = logo_file
    timeline["symbol"] = symbol_file
    (output_dir / "public" / "timeline.json").write_text(
        json.dumps(timeline, indent=2, ensure_ascii=False)
    )

    print(f"\n[audio2scene] Project generated at: {output_dir}")
    print(f"\nNext steps:")
    print(f"  cd {output_dir}")
    print(f"  npm install")
    print(f"  npx remotion studio          # interactive preview")
    print(f"  npx remotion render Audio2ScenePreview out/video.mp4")

    return output_dir

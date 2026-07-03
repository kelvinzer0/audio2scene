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
    """User-provided spec from data.json."""
    music: str
    screen: str = "1280:720"     # "W:H"
    text: List[str] = None
    videos: List[str] = None
    images: List[str] = None
    duration: Optional[float] = None  # max render duration in seconds (None = full song)

    @classmethod
    def from_dict(cls, d: dict) -> "DataSpec":
        return cls(
            music=d["music"],
            screen=d.get("screen", "1280:720"),
            text=d.get("text", []) or [],
            videos=d.get("videos", []) or [],
            images=d.get("images", []) or [],
            duration=_parse_duration(d.get("duration")),
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
    """A time slice in the timeline with mapped content."""
    kind: str                       # "title" | "main" | "break" | "ending"
    start: float                    # seconds
    end: float                      # seconds
    segment_label: str = ""
    segment_intensity: float = 0.0
    segment_intensity_label: str = ""
    # Mapped content
    text: Optional[str] = None
    video: Optional[str] = None     # filename in public/videos/
    image: Optional[str] = None     # filename in public/images/
    # Transition into this slice (from previous)
    transition: str = "fade"        # transition name
    transition_duration_frames: int = 14


# ─── Content mapping ─────────────────────────────────────────────────────────


def map_content_to_timeline(
    segments: List[LabeledSegment],
    events: List[VideoEvent],
    spec: DataSpec,
    fps: int = 30,
    min_cut_gap_sec: float = 3.0,
) -> List[SceneSlice]:
    """Map user content (text/videos/images) to song structure.

    Strategy:
    - Title scene (first 3s or until first segment): text[0] + song title
    - Main Variation slices: cycle through videos[] (one per slice)
    - Break segments: cycle through images[] (Ken Burns)
    - Fill In: brief flash overlay (no content)
    - Ending / Fade Out: text[-1]
    - Filtered Cut events inside Main segments → sub-slices with random transitions
    """
    slices: List[SceneSlice] = []
    if not segments:
        return slices

    # Filter Cut events for sub-slicing (3s rule)
    cuts = sorted(
        [e for e in events if e.effect == "Cut" and e.intensity >= 0.05],
        key=lambda e: e.time,
    )
    filtered_cuts: List[VideoEvent] = []
    last_cut_time = -1e9
    for c in cuts:
        if c.time - last_cut_time >= min_cut_gap_sec:
            filtered_cuts.append(c)
            last_cut_time = c.time

    # Available transitions pool
    transitions = [
        "fade", "slideLeft", "slideRight", "slideUp", "slideDown",
        "zoomIn", "zoomOut", "irisWipe", "whipPan", "whipPanRight",
        "pushThrough", "focusPull",
    ]

    def next_transition(seed: int) -> str:
        # Deterministic pick
        idx = (seed * 7 + 3) % len(transitions)
        return transitions[idx]

    # === Title scene (3s or until first segment starts) ===
    title_end = min(3.0, segments[0].start + 0.5)
    if segments[0].start > 0:
        title_end = segments[0].start
    else:
        title_end = 3.0

    if spec.text:
        title_text = spec.text[0]
    else:
        title_text = Path(spec.music).stem

    slices.append(SceneSlice(
        kind="title",
        start=0.0,
        end=title_end,
        text=title_text,
        transition="fade",
        transition_duration_frames=14,
    ))

    # === Per-segment mapping ===
    video_idx = 0
    image_idx = 0
    text_idx = 1 if spec.text else 0  # text[0] used for title
    seed_counter = 1

    for seg_idx, seg in enumerate(segments):
        if seg.label in ("Ending", "Fade Out"):
            # Ending scene: last text + fade out
            ending_text = spec.text[-1] if spec.text and len(spec.text) > 1 else None
            slices.append(SceneSlice(
                kind="ending",
                start=seg.start,
                end=seg.end,
                segment_label=seg.label,
                segment_intensity=seg.intensity,
                segment_intensity_label=seg.intensity_label,
                text=ending_text,
                transition=next_transition(seed_counter),
                transition_duration_frames=18,
            ))
            seed_counter += 1
            continue

        if seg.label == "Break":
            # Break: cycle through images with Ken Burns
            image_file = None
            if spec.images:
                image_file = Path(spec.images[image_idx % len(spec.images)]).name
                image_idx += 1
            slices.append(SceneSlice(
                kind="break",
                start=seg.start,
                end=seg.end,
                segment_label=seg.label,
                segment_intensity=seg.intensity,
                segment_intensity_label=seg.intensity_label,
                image=image_file,
                text=spec.text[text_idx] if text_idx < len(spec.text) else None,
                transition=next_transition(seed_counter),
                transition_duration_frames=16,
            ))
            if text_idx < len(spec.text):
                text_idx += 1
            seed_counter += 1
            continue

        # Main Variation / Fill In / Intro / Fade In: sub-slice by Cut events
        cuts_in_seg = [c for c in filtered_cuts if c.start <= c.time < seg.end and c.time >= seg.start and c.time < seg.end] if False else [c for c in filtered_cuts if seg.start <= c.time < seg.end]

        slice_starts = [seg.start] + [c.time for c in cuts_in_seg]
        slice_ends = [c.time for c in cuts_in_seg] + [seg.end]

        for sub_idx, (s_start, s_end) in enumerate(zip(slice_starts, slice_ends)):
            if s_end - s_start < 0.5:
                continue  # skip too-short slices
            # Pick video (cycle)
            video_file = None
            if spec.videos:
                video_file = Path(spec.videos[video_idx % len(spec.videos)]).name
                video_idx += 1
            # Pick text (cycle, only on first slice of segment)
            slice_text = None
            if sub_idx == 0 and text_idx < len(spec.text):
                slice_text = spec.text[text_idx]
                text_idx += 1

            slices.append(SceneSlice(
                kind="main",
                start=s_start,
                end=s_end,
                segment_label=seg.label,
                segment_intensity=seg.intensity,
                segment_intensity_label=seg.intensity_label,
                video=video_file,
                text=slice_text,
                transition=next_transition(seed_counter),
                transition_duration_frames=14,
            ))
            seed_counter += 1

    return slices


# ─── Project file templates ──────────────────────────────────────────────────


PACKAGE_JSON = """{
  "name": "audio2scene-remotion-project",
  "version": "1.0.0",
  "description": "Auto-generated Remotion project from audio2scene",
  "license": "UNLICENSED",
  "private": true,
  "dependencies": {
    "@remotion/cli": "4.0.484",
    "@remotion/transitions": "4.0.484",
    "@remotion/media": "4.0.484",
    "react": "19.2.3",
    "react-dom": "19.2.3",
    "remotion": "4.0.484"
  },
  "devDependencies": {
    "@types/react": "19.2.7",
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
    "noUnusedLocals": false
  },
  "exclude": ["remotion.config.ts", "node_modules"]
}
"""

REMOTION_CONFIG_TS = """import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setConcurrency(1);
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

    # 3. Compute waveform (200 peaks for visualization)
    import numpy as np
    n_buckets = 200
    bucket_size = max(1, len(y) // n_buckets)
    waveform = []
    for i in range(n_buckets):
        s = i * bucket_size
        e = s + bucket_size
        chunk = y[s:e]
        if chunk.size == 0:
            waveform.append(0.0)
        else:
            waveform.append(float(np.max(np.abs(chunk))))
    peak_max = max(waveform) if waveform else 0.0
    if peak_max > 0:
        waveform = [p / peak_max for p in waveform]

    # 4. Map content to timeline
    slices = map_content_to_timeline(labeled, events, spec, fps=fps)
    print(f"[audio2scene] Mapped {len(slices)} scenes")

    # 5. Build timeline.json
    width, height = spec.dimensions
    timeline = {
        "title": Path(spec.music).stem,
        "duration": round(features.duration, 3),
        "tempo": round(float(features.tempo), 1),
        "n_segments": len(labeled),
        "n_events": len(events),
        "fps": fps,
        "width": width,
        "height": height,
        "slices": [asdict(s) for s in slices],
        "waveform": waveform,
        "segments": [
            {
                "label": s.label,
                "start": round(s.start, 3),
                "end": round(s.end, 3),
                "intensity": round(s.intensity, 3),
                "intensity_label": s.intensity_label,
            }
            for s in labeled
        ],
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
    # Composition.tsx — read from templates/Composition.tsx (clean JSX, no format())
    template_path = Path(__file__).parent / "templates" / "Composition.tsx"
    (output_dir / "src" / "Composition.tsx").write_text(template_path.read_text())

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

    print(f"\n[audio2scene] Project generated at: {output_dir}")
    print(f"\nNext steps:")
    print(f"  cd {output_dir}")
    print(f"  npm install")
    print(f"  npx remotion studio          # interactive preview")
    print(f"  npx remotion render Audio2ScenePreview out/video.mp4")

    return output_dir

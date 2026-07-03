import React, { useEffect, useState } from "react";
import {
  AbsoluteFill,
  Audio,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { TransitionSeries, linearTiming } from "@remotion/transitions";

// remocn components
import { ShaderMeshGradient } from "./components/remocn/shader-mesh-gradient";
import { SoftBlurIn } from "./components/remocn/soft-blur-in";
import { KineticCenterBuild } from "./components/remocn/kinetic-center-build";
import { NumberWheel } from "./components/remocn/number-wheel";

// remocn transitions — only non-shader ones (shader-based crash headless Chrome)
import { whipPan } from "./components/remocn/whip-pan";
import { pushThrough } from "./components/remocn/push-through";
import { focusPull } from "./components/remocn/focus-pull";
import type { TransitionPresentation } from "@remotion/transitions";

// ─── Types ──────────────────────────────────────────────────────────────────

type Effect = "Cut" | "Flash" | "Zoom" | "Glitch" | "Hold" | "Fade In" | "Fade Out" | "Title";
type Source = "beat" | "onset" | "segment_start" | "segment_end";

interface VideoEvent {
  time: number;
  effect: Effect;
  intensity: number;
  segment_label: string;
  duration: number;
  source: Source;
}

interface Segment {
  label: string;
  start: number;
  end: number;
  confidence: number;
  intensity: number;
  intensity_label: string;
  duration: number;
}

interface SongData {
  title: string;
  duration: number;
  tempo: number;
  n_segments: number;
  n_beats: number;
  n_onsets: number;
  n_events: number;
  events_summary: { n_events: number; by_effect: Record<string, number>; density_per_sec: number };
  segments: Segment[];
  events: VideoEvent[];
  waveform: number[];
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

const EFFECT_COLORS: Record<Effect, string> = {
  Cut: "#94a3b8",
  Flash: "#facc15",
  Zoom: "#22d3ee",
  Glitch: "#ef4444",
  Hold: "#3b82f6",
  "Fade In": "#4ade80",
  "Fade Out": "#2dd4bf",
  Title: "#a855f7",
};

function paletteForLabel(label: string): string[] {
  const base = LABEL_COLORS[label] || "#a855f7";
  return ["#0a0a14", base + "80", base, base + "40"];
}

// ─── Transition pool ────────────────────────────────────────────────────────
// Mix of remocn non-shader transitions + custom CSS-based transitions.
// Shader-based transitions (grain-dissolve, wave-wipe, ripple-zoom, warp-dissolve,
// swirl-dissolve, dither-dissolve, perlin-dissolve, smoke-dissolve) are excluded
// because WebGL shaders crash headless Chrome during batch rendering.

type TransitionFactory = (props?: Record<string, unknown>) => TransitionPresentation<Record<string, unknown>>;

interface TransitionDef {
  name: string;
  factory: TransitionFactory;
  defaultDurationFrames: number;
  props?: Record<string, unknown>;
}

const TRANSITIONS: TransitionDef[] = [
  // remocn non-shader transitions (3)
  { name: "whipPan",       factory: whipPan as TransitionFactory,        defaultDurationFrames: 14, props: { direction: "left", blur: 12 } },
  { name: "whipPanRight",  factory: whipPan as TransitionFactory,        defaultDurationFrames: 14, props: { direction: "right", blur: 12 } },
  { name: "pushThrough",   factory: pushThrough as TransitionFactory,    defaultDurationFrames: 18 },
  { name: "focusPull",     factory: focusPull as TransitionFactory,      defaultDurationFrames: 16 },
  // Custom CSS-based transitions (8) — slide / fade / zoom / wipe variants
  { name: "fade",          factory: () => customFade(),                  defaultDurationFrames: 14 },
  { name: "slideLeft",     factory: () => customSlide("left"),           defaultDurationFrames: 14 },
  { name: "slideRight",    factory: () => customSlide("right"),          defaultDurationFrames: 14 },
  { name: "slideUp",       factory: () => customSlide("up"),             defaultDurationFrames: 14 },
  { name: "slideDown",     factory: () => customSlide("down"),           defaultDurationFrames: 14 },
  { name: "zoomIn",        factory: () => customZoom("in"),              defaultDurationFrames: 16 },
  { name: "zoomOut",       factory: () => customZoom("out"),             defaultDurationFrames: 16 },
  { name: "irisWipe",      factory: () => customIris(),                  defaultDurationFrames: 18 },
];

// Custom CSS-based transitions — defined via TransitionPresentation component
import type { TransitionPresentationComponentProps } from "@remotion/transitions";

const FadePresentation: React.FC<TransitionPresentationComponentProps<Record<string, unknown>>> = ({
  children,
  presentationProgress,
  presentationDirection,
}) => {
  const entering = presentationDirection === "entering";
  const opacity = entering ? presentationProgress : 1 - presentationProgress;
  return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
};

function customFade(): TransitionPresentation<Record<string, unknown>> {
  return { component: FadePresentation, props: {} };
}

const SlidePresentation: React.FC<TransitionPresentationComponentProps<{ direction: "left" | "right" | "up" | "down" }>> = ({
  children,
  presentationProgress,
  presentationDirection,
  passedProps,
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
  return <AbsoluteFill style={{ transform }}>{children}</AbsoluteFill>;
};

function customSlide(direction: "left" | "right" | "up" | "down"): TransitionPresentation<Record<string, unknown>> {
  return { component: SlidePresentation as React.FC<TransitionPresentationComponentProps<Record<string, unknown>>>, props: { direction } };
}

const ZoomPresentation: React.FC<TransitionPresentationComponentProps<{ mode: "in" | "out" }>> = ({
  children,
  presentationProgress,
  presentationDirection,
  passedProps,
}) => {
  const { mode = "in" } = passedProps;
  const entering = presentationDirection === "entering";
  const p = presentationProgress;
  const scale = entering
    ? (mode === "in" ? 1.5 - p * 0.5 : 0.5 + p * 0.5)
    : (mode === "in" ? 1 + p * 0.5 : 1 - p * 0.5);
  const opacity = entering ? p : 1 - p;
  return (
    <AbsoluteFill style={{ scale: `${scale}`, opacity, transformOrigin: "center" }}>
      {children}
    </AbsoluteFill>
  );
};

function customZoom(mode: "in" | "out"): TransitionPresentation<Record<string, unknown>> {
  return { component: ZoomPresentation as React.FC<TransitionPresentationComponentProps<Record<string, unknown>>>, props: { mode } };
}

const IrisPresentation: React.FC<TransitionPresentationComponentProps<Record<string, unknown>>> = ({
  children,
  presentationProgress,
  presentationDirection,
}) => {
  const entering = presentationDirection === "entering";
  const p = presentationProgress;
  // Clip-path circle that grows from 0 to 100% for entering, shrinks for exiting
  const radius = entering ? p * 150 : (1 - p) * 150;
  const clipPath = `circle(${radius}% at 50% 50%)`;
  return (
    <AbsoluteFill style={{ clipPath, WebkitClipPath: clipPath }}>
      {children}
    </AbsoluteFill>
  );
};

function customIris(): TransitionPresentation<Record<string, unknown>> {
  return { component: IrisPresentation, props: {} };
}

// Deterministic pick — seed by event index so renders are reproducible
// Simple hash-based PRNG (no external dep)
function seededRandom(seed: string): number {
  let h = 0;
  for (let i = 0; i < seed.length; i++) {
    h = (h * 31 + seed.charCodeAt(i)) | 0;
  }
  // Map to [0, 1)
  return Math.abs(h % 10000) / 10000;
}

function pickTransition(seed: number): TransitionPresentation<Record<string, unknown>> {
  const idx = Math.floor(seededRandom(`transition-${seed}`) * TRANSITIONS.length);
  const def = TRANSITIONS[idx];
  return def.factory(def.props);
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function fmtTime(t: number): string {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

// Filter Cut events: keep only strong cuts, at least minGapSec apart.
// Default 3.0s — at most 1 cut-driven transition every 3 seconds, otherwise
// transitions pile up and the video feels chaotic.
function filterCutsForTransitions(
  events: VideoEvent[],
  minGapSec = 3.0,
  minIntensity = 0.05,
): VideoEvent[] {
  const cuts = events
    .filter((e) => e.effect === "Cut" && e.intensity >= minIntensity)
    .sort((a, b) => a.time - b.time);
  const kept: VideoEvent[] = [];
  let lastTime = -Infinity;
  for (const c of cuts) {
    if (c.time - lastTime >= minGapSec) {
      kept.push(c);
      lastTime = c.time;
    }
  }
  return kept;
}

// ─── Build sub-scene list ───────────────────────────────────────────────────
// Each sub-scene is a time slice within a segment.
// Between sub-scenes, a random remocn transition fires (replacing the "Cut").

interface SubScene {
  kind: "title" | "segment-slice";
  start: number;        // absolute time in seconds
  end: number;          // absolute time in seconds
  segment?: Segment;
  segmentIndex?: number;
  sliceIndex?: number;  // index of this slice within the segment (for transition seeding)
}

function buildSubScenes(song: SongData, fps: number): SubScene[] {
  const out: SubScene[] = [];
  const titleEvent = song.events.find((e) => e.effect === "Title");
  const titleDur = titleEvent ? titleEvent.duration : 3.0;
  out.push({ kind: "title", start: 0, end: titleDur });

  // Cuts that will trigger transitions
  const transitionCuts = filterCutsForTransitions(song.events);

  let segIdx = 0;
  for (const seg of song.segments) {
    // Cuts that fall inside this segment
    const cutsInSeg = transitionCuts.filter((c) => c.time >= seg.start && c.time < seg.end);
    let sliceStart = seg.start;
    let sliceIdx = 0;
    for (const c of cutsInSeg) {
      out.push({
        kind: "segment-slice",
        start: sliceStart,
        end: c.time,
        segment: seg,
        segmentIndex: segIdx,
        sliceIndex: sliceIdx,
      });
      sliceStart = c.time;
      sliceIdx++;
    }
    // last slice of this segment
    out.push({
      kind: "segment-slice",
      start: sliceStart,
      end: seg.end,
      segment: seg,
      segmentIndex: segIdx,
      sliceIndex: sliceIdx,
    });
    segIdx++;
  }
  return out;
}

// ─── Title scene ────────────────────────────────────────────────────────────

const TitleScene: React.FC<{ song: SongData }> = ({ song }) => {
  const frame = useCurrentFrame();
  const fadeOut = interpolate(frame, [60, 90], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ opacity: fadeOut }}>
      <ShaderMeshGradient
        speed={0.4}
        colors={["#0a0a14", "#a855f780", "#22d3ee", "#a855f740"]}
        distortion={0.7}
        swirl={0.2}
      />
      <AbsoluteFill
        style={{
          background: "radial-gradient(circle at center, transparent 20%, rgba(0,0,0,0.7) 100%)",
        }}
      />
      <AbsoluteFill
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 24,
        }}
      >
        <div
          style={{
            color: "#a855f7",
            fontSize: 16,
            fontWeight: 600,
            letterSpacing: 6,
            textTransform: "uppercase",
            opacity: interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" }),
          }}
        >
          ◆ Audio2Scene Preview
        </div>
        <SoftBlurIn
          text={song.title}
          fontSize={72}
          color="white"
          fontWeight={800}
          blur={20}
          speed={1}
        />
        <div
          style={{
            marginTop: 32,
            display: "flex",
            gap: 32,
            color: "#94a3b8",
            fontSize: 18,
            fontFamily: "monospace",
            opacity: interpolate(frame, [30, 60], [0, 1], { extrapolateRight: "clamp" }),
          }}
        >
          <span style={{ color: "#22d3ee" }}>{song.tempo} BPM</span>
          <span>·</span>
          <span>{fmtTime(song.duration)}</span>
          <span>·</span>
          <span>{song.n_events} events</span>
          <span>·</span>
          <span>{song.n_segments} segments</span>
        </div>
        <div
          style={{
            marginTop: 24,
            padding: "10px 28px",
            border: "2px solid #22d3ee",
            color: "#22d3ee",
            fontFamily: "Inter, system-ui, sans-serif",
            fontSize: 14,
            fontWeight: 700,
            letterSpacing: 3,
            textTransform: "uppercase",
            opacity: interpolate(frame, [45, 75], [0, 1], { extrapolateRight: "clamp" }),
          }}
        >
          v0.4.0 · 11 remocn transitions on every Cut
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// ─── Segment slice scene ────────────────────────────────────────────────────

interface SegmentSliceProps {
  song: SongData;
  sub: SubScene;
}

const SegmentSlice: React.FC<SegmentSliceProps> = ({ song, sub }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const segment = sub.segment!;
  const localTime = sub.start + frame / fps;

  // Events within this slice
  const sliceEvents = song.events.filter(
    (e) => e.time >= sub.start && e.time < sub.end && e.effect !== "Cut" && e.effect !== "Title"
  );

  // Active effect (Flash / Glitch / Zoom / Hold)
  const flashEvent = sliceEvents.find(
    (e) => e.effect === "Flash" && localTime >= e.time && localTime < e.time + 0.1
  );
  const glitchEvent = sliceEvents.find(
    (e) => e.effect === "Glitch" && localTime >= e.time && localTime < e.time + 1.0
  );
  const zoomEvent = sliceEvents.find(
    (e) => e.effect === "Zoom" && localTime >= e.time && localTime < e.time + e.duration
  );
  const holdEvent = sliceEvents.find(
    (e) => e.effect === "Hold" && localTime >= e.time && localTime < e.time + e.duration
  );

  const zoomProgress = zoomEvent
    ? (localTime - zoomEvent.time) / zoomEvent.duration
    : 0;
  const zoomScale = zoomEvent ? 1 + zoomEvent.intensity * 0.3 * zoomProgress : 1;
  const colors = paletteForLabel(segment.label);

  // Active effect indicator
  let activeEffect: Effect | null = null;
  let effectIntensity = 0;
  if (flashEvent) { activeEffect = "Flash"; effectIntensity = flashEvent.intensity; }
  else if (glitchEvent) { activeEffect = "Glitch"; effectIntensity = glitchEvent.intensity; }
  else if (zoomEvent) { activeEffect = "Zoom"; effectIntensity = zoomEvent.intensity; }
  else if (holdEvent) { activeEffect = "Hold"; effectIntensity = holdEvent.intensity; }

  // First 50 frames of slice: kinetic label entrance (only if slice is first in segment)
  const showKinetic = (sub.sliceIndex === 0) && frame < 50;

  return (
    <AbsoluteFill>
      {/* Shader background with optional zoom */}
      <AbsoluteFill style={{ scale: `${zoomScale}` }}>
        <ShaderMeshGradient
          speed={0.3 + segment.intensity * 0.5}
          colors={colors}
          distortion={0.5 + segment.intensity * 0.4}
          swirl={0.1 + segment.intensity * 0.2}
        />
      </AbsoluteFill>

      {/* Hold overlay (darken during Break) */}
      {holdEvent && (
        <AbsoluteFill style={{ backgroundColor: "black", opacity: 0.3, pointerEvents: "none" }} />
      )}

      {/* Vignette */}
      <AbsoluteFill
        style={{
          background: "radial-gradient(circle at center, transparent 30%, rgba(0,0,0,0.6) 100%)",
          pointerEvents: "none",
        }}
      />

      {/* Glitch effect */}
      {glitchEvent && (
        <AbsoluteFill
          style={{
            boxShadow: `inset ${Math.sin(frame * 3) * 15 * glitchEvent.intensity}px 0 0 #ef444488, inset ${-Math.sin(frame * 3) * 15 * glitchEvent.intensity}px 0 0 #22d3ee88`,
            pointerEvents: "none",
          }}
        >
          <div style={{
            position: "absolute", top: "30%", left: 0, right: 0, height: 6,
            backgroundColor: "#ef4444", opacity: 0.7 * glitchEvent.intensity,
            transform: `translateX(${Math.sin(frame * 4) * 30}px)`,
          }} />
          <div style={{
            position: "absolute", top: "60%", left: 0, right: 0, height: 8,
            backgroundColor: "#22d3ee", opacity: 0.5 * glitchEvent.intensity,
            transform: `translateX(${-Math.sin(frame * 4) * 30}px)`,
          }} />
        </AbsoluteFill>
      )}

      {/* Flash overlay */}
      {flashEvent && (
        <AbsoluteFill
          style={{
            backgroundColor: "white",
            opacity: flashEvent.intensity * 0.85,
            pointerEvents: "none",
          }}
        />
      )}

      {/* Kinetic label entrance (only at slice 0 of a segment) */}
      {showKinetic && (
        <AbsoluteFill
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            pointerEvents: "none",
          }}
        >
          <KineticCenterBuild
            text={segment.label}
            fontSize={88}
            color="white"
            fontWeight={800}
            speed={1}
          />
        </AbsoluteFill>
      )}

      {/* Persistent UI overlays (fade in after kinetic) */}
      <AbsoluteFill
        style={{
          opacity: showKinetic
            ? interpolate(frame, [40, 60], [0, 1], { extrapolateRight: "clamp" })
            : 1,
        }}
      >
        {/* Top-left: segment label + intensity */}
        <div
          style={{
            position: "absolute",
            top: 40,
            left: 60,
            fontFamily: "Inter, system-ui, sans-serif",
          }}
        >
          <div
            style={{
              color: LABEL_COLORS[segment.label] || "#a855f7",
              fontSize: 12,
              fontWeight: 700,
              letterSpacing: 3,
              textTransform: "uppercase",
              marginBottom: 6,
            }}
          >
            Scene {(sub.segmentIndex ?? 0) + 1} · Slice {(sub.sliceIndex ?? 0) + 1}
          </div>
          <div
            style={{
              color: "white",
              fontSize: 32,
              fontWeight: 800,
              textShadow: "0 2px 12px rgba(0,0,0,0.6)",
            }}
          >
            {segment.label}
          </div>
          <div style={{ marginTop: 10, display: "flex", gap: 12, alignItems: "center" }}>
            <div
              style={{
                padding: "5px 12px",
                backgroundColor: `${LABEL_COLORS[segment.label] || "#a855f7"}30`,
                border: `1px solid ${LABEL_COLORS[segment.label] || "#a855f7"}`,
                borderRadius: 6,
                color: LABEL_COLORS[segment.label] || "#a855f7",
                fontSize: 12,
                fontWeight: 700,
                letterSpacing: 1,
                textTransform: "uppercase",
              }}
            >
              {segment.intensity_label}
            </div>
            <div style={{ color: "#94a3b8", fontSize: 13, fontFamily: "monospace" }}>
              intensity {(segment.intensity * 100).toFixed(0)}%
            </div>
          </div>
        </div>

        {/* Top-right: time + tempo */}
        <div
          style={{
            position: "absolute",
            top: 40,
            right: 60,
            textAlign: "right",
            fontFamily: "Inter, system-ui, sans-serif",
          }}
        >
          <div
            style={{
              color: "white",
              fontSize: 28,
              fontWeight: 800,
              fontFamily: "monospace",
              textShadow: "0 2px 12px rgba(0,0,0,0.6)",
            }}
          >
            {fmtTime(localTime)}{" "}
            <span style={{ color: "#475569", fontSize: 18 }}>/ {fmtTime(song.duration)}</span>
          </div>
          <div style={{ color: "#22d3ee", fontSize: 14, fontWeight: 700, marginTop: 4 }}>
            {song.tempo} BPM
          </div>
        </div>

        {/* Active effect indicator */}
        {activeEffect && (
          <div
            style={{
              position: "absolute",
              bottom: 180,
              left: "50%",
              transform: "translateX(-50%)",
              padding: "10px 28px",
              backgroundColor: `${EFFECT_COLORS[activeEffect]}30`,
              border: `2px solid ${EFFECT_COLORS[activeEffect]}`,
              borderRadius: 8,
              color: "white",
              fontFamily: "Inter, system-ui, sans-serif",
              fontSize: 16,
              fontWeight: 700,
              letterSpacing: 4,
              textTransform: "uppercase",
              boxShadow: `0 0 24px ${EFFECT_COLORS[activeEffect]}80`,
            }}
          >
            {activeEffect}
            <span style={{ marginLeft: 14, color: EFFECT_COLORS[activeEffect], fontSize: 13 }}>
              {(effectIntensity * 100).toFixed(0)}%
            </span>
          </div>
        )}

        {/* Waveform */}
        <WaveformViz
          waveform={song.waveform}
          currentTime={localTime}
          duration={song.duration}
        />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// ─── Waveform visualization ─────────────────────────────────────────────────

const WaveformViz: React.FC<{ waveform: number[]; currentTime: number; duration: number }> = ({
  waveform,
  currentTime,
  duration,
}) => {
  const progress = currentTime / duration;
  const N = waveform.length;
  return (
    <div
      style={{
        position: "absolute",
        bottom: 80,
        left: 60,
        right: 60,
        height: 60,
        display: "flex",
        alignItems: "center",
        gap: 2,
        opacity: 0.8,
      }}
    >
      {waveform.map((v, i) => {
        const isPast = i / N < progress;
        const distFromPlayhead = Math.abs(i / N - progress);
        const isNear = distFromPlayhead < 0.02;
        return (
          <div
            key={i}
            style={{
              flex: 1,
              height: `${v * 100}%`,
              backgroundColor: isNear ? "white" : isPast ? "#22d3ee" : "#475569",
              borderRadius: 1,
              minHeight: 2,
              transform: isNear ? "scaleY(1.2)" : "scaleY(1)",
            }}
          />
        );
      })}
    </div>
  );
};

// ─── Timeline progress bar ──────────────────────────────────────────────────

const Timeline: React.FC<{ segments: Segment[]; currentTime: number; duration: number; sub: SubScene | null }> = ({
  segments,
  currentTime,
  duration,
  sub,
}) => {
  const progress = currentTime / duration;
  const width = 1160;
  return (
    <div style={{ position: "absolute", bottom: 30, left: 60, width, height: 30 }}>
      <div
        style={{
          position: "absolute",
          top: 12,
          left: 0,
          right: 0,
          height: 4,
          backgroundColor: "#1e293b",
          borderRadius: 2,
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 12,
          left: 0,
          width: `${progress * 100}%`,
          height: 4,
          backgroundColor: "#22d3ee",
          borderRadius: 2,
          boxShadow: "0 0 8px #22d3ee",
        }}
      />
      {segments.map((seg, i) => {
        const left = (seg.start / duration) * width;
        const segWidth = ((seg.end - seg.start) / duration) * width;
        return (
          <div
            key={`tl-${i}`}
            style={{
              position: "absolute",
              top: 6,
              left,
              width: segWidth,
              height: 4,
              backgroundColor: LABEL_COLORS[seg.label] || "#a855f7",
              opacity: 0.5,
            }}
          />
        );
      })}
      {/* Current slice marker */}
      {sub && sub.kind === "segment-slice" && (
        <div
          style={{
            position: "absolute",
            top: 0,
            left: (sub.start / duration) * width,
            width: Math.max(2, ((sub.end - sub.start) / duration) * width),
            height: 30,
            border: "1px solid white",
            opacity: 0.4,
            pointerEvents: "none",
          }}
        />
      )}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: progress * width,
          width: 2,
          height: 30,
          backgroundColor: "white",
          boxShadow: "0 0 8px white",
        }}
      />
    </div>
  );
};

// ─── Main composition ───────────────────────────────────────────────────────

export const MyComposition: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const [song, setSong] = useState<SongData | null>(null);

  useEffect(() => {
    fetch(staticFile("song.json"))
      .then((r) => r.json())
      .then(setSong)
      .catch(console.error);
  }, []);

  if (!song) {
    return (
      <AbsoluteFill
        style={{
          backgroundColor: "#0a0a0f",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "white",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        Loading song data...
      </AbsoluteFill>
    );
  }

  const currentTime = frame / fps;
  const subScenes = buildSubScenes(song, fps);

  // Find fade in/out events
  const fadeInEvent = song.events.find((e) => e.effect === "Fade In");
  const fadeOutEvent = song.events.find((e) => e.effect === "Fade Out");

  let fadeInProgress = 1;
  if (fadeInEvent) {
    const fadeEnd = fadeInEvent.time + fadeInEvent.duration;
    if (currentTime >= fadeInEvent.time && currentTime < fadeEnd) {
      fadeInProgress = (currentTime - fadeInEvent.time) / fadeInEvent.duration;
    }
  }

  let fadeOutProgress = 0;
  if (fadeOutEvent) {
    const fadeEnd = fadeOutEvent.time + fadeOutEvent.duration;
    if (currentTime >= fadeOutEvent.time && currentTime < fadeEnd) {
      fadeOutProgress = (currentTime - fadeOutEvent.time) / fadeOutEvent.duration;
    } else if (currentTime >= fadeEnd) {
      fadeOutProgress = 1;
    }
  }

  // Find current sub-scene for timeline marker
  let currentSub: SubScene | null = null;
  for (const sub of subScenes) {
    if (currentTime >= sub.start && currentTime < sub.end) {
      currentSub = sub;
      break;
    }
  }

  // Count transitions (sub-scenes - 1)
  const nTransitions = Math.max(0, subScenes.length - 1);

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0a0f", fontFamily: "Inter, system-ui, sans-serif" }}>
      <Audio src={staticFile("audio.mp3")} />

      <TransitionSeries>
        {subScenes.map((sub, i) => {
          // Transition duration for boundary i (between sub i and i+1)
          const transitionDur = i < subScenes.length - 1
            ? Math.min(18, Math.max(8, Math.round(((subScenes[i + 1].end - subScenes[i + 1].start) * fps) * 0.3)))
            : 0;
          // Sequence duration must be > transition duration (both sides)
          // Pad if needed
          const rawDur = Math.max(1, Math.round((sub.end - sub.start) * fps));
          const prevTransitionDur = i > 0
            ? Math.min(18, Math.max(8, Math.round(((subScenes[i].end - subScenes[i].start) * fps) * 0.3)))
            : 0;
          const minDur = Math.max(transitionDur, prevTransitionDur) + 2;
          const dur = Math.max(rawDur, minDur);
          return (
            <React.Fragment key={i}>
              <TransitionSeries.Sequence durationInFrames={dur}>
                {sub.kind === "title" ? (
                  <TitleScene song={song} />
                ) : (
                  <SegmentSlice song={song} sub={sub} />
                )}
              </TransitionSeries.Sequence>
              {i < subScenes.length - 1 && (
                <TransitionSeries.Transition
                  presentation={pickTransition(i)}
                  timing={linearTiming({ durationInFrames: transitionDur })}
                />
              )}
            </React.Fragment>
          );
        })}
      </TransitionSeries>

      {/* Fade in/out overlays */}
      <AbsoluteFill
        style={{
          backgroundColor: "black",
          opacity: fadeInProgress < 1 ? 1 - fadeInProgress : 0,
          pointerEvents: "none",
        }}
      />
      <AbsoluteFill
        style={{
          backgroundColor: "black",
          opacity: fadeOutProgress,
          pointerEvents: "none",
        }}
      />

      {/* Persistent timeline */}
      <Timeline
        segments={song.segments}
        currentTime={currentTime}
        duration={song.duration}
        sub={currentSub}
      />

      {/* Top-center brand mark */}
      <div
        style={{
          position: "absolute",
          top: 16,
          left: "50%",
          transform: "translateX(-50%)",
          color: "#94a3b8",
          fontFamily: "Inter, system-ui, sans-serif",
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: 4,
          textTransform: "uppercase",
          opacity: 0.7,
        }}
      >
        audio2scene × remocn · {nTransitions} transitions across {song.n_segments} segments
      </div>
    </AbsoluteFill>
  );
};

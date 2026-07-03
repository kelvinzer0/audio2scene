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
import { ShaderMeshGradient } from "./components/remocn/shader-mesh-gradient";
import { SoftBlurIn } from "./components/remocn/soft-blur-in";
import { KineticCenterBuild } from "./components/remocn/kinetic-center-build";
import { NumberWheel } from "./components/remocn/number-wheel";
import { whipPan } from "./components/remocn/whip-pan";

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

// Build a 4-color palette for ShaderMeshGradient based on segment label
function paletteForLabel(label: string): string[] {
  const base = LABEL_COLORS[label] || "#a855f7";
  // Build variations: dark, base, base lighten, accent
  return [
    "#0a0a14",
    base + "80",  // 50% opacity
    base,
    base + "40",  // 25% opacity
  ];
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function findSegment(segments: Segment[], t: number): Segment | null {
  for (const seg of segments) {
    if (t >= seg.start && t < seg.end) return seg;
  }
  return segments.length > 0 ? segments[segments.length - 1] : null;
}

function findActiveEffect(events: VideoEvent[], t: number, windowSec = 0.15): { effect: Effect | null; intensity: number } {
  let best: VideoEvent | null = null;
  for (const ev of events) {
    if (ev.time <= t && ev.time > t - windowSec) {
      if (!best || ev.intensity > best.intensity) best = ev;
    }
  }
  if (best) return { effect: best.effect, intensity: best.intensity };
  return { effect: null, intensity: 0 };
}

function fmtTime(t: number): string {
  const m = Math.floor(t / 60);
  const s = Math.floor(t % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

// ─── Scene: one per segment, with whip-pan transitions between ──────────────

interface SceneProps {
  segment: Segment;
  song: SongData;
  segmentIndex: number;
  isLast: boolean;
}

const Scene: React.FC<SceneProps> = ({ segment, song, segmentIndex }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Local frame: 0 at segment start
  const localFrame = frame;
  const localTime = localFrame / fps;

  // Filter events that belong to this segment
  const segmentEvents = song.events.filter(
    (e) => e.time >= segment.start && e.time < segment.end
  );

  // Find current active effect within this scene
  const { effect: activeEffect, intensity: effectIntensity } = findActiveEffect(
    segmentEvents,
    segment.start + localTime
  );

  // Flash state (100ms window)
  const flashEvent = segmentEvents.find(
    (e) => e.effect === "Flash" && localTime >= e.time - segment.start && localTime < e.time - segment.start + 0.1
  );

  // Zoom event (build-up)
  const zoomEvent = segmentEvents.find(
    (e) => e.effect === "Zoom" && localTime >= e.time - segment.start && localTime < e.time - segment.start + e.duration
  );
  const zoomProgress = zoomEvent
    ? (localTime - (zoomEvent.time - segment.start)) / zoomEvent.duration
    : 0;

  // Glitch event (1s)
  const glitchEvent = segmentEvents.find(
    (e) => e.effect === "Glitch" && localTime >= e.time - segment.start && localTime < e.time - segment.start + 1.0
  );

  const colors = paletteForLabel(segment.label);

  // Zoom scale
  const zoomScale = zoomEvent ? 1 + zoomEvent.intensity * 0.3 * zoomProgress : 1;

  return (
    <AbsoluteFill>
      {/* Animated shader background — colors change per segment */}
      <AbsoluteFill style={{ scale: `${zoomScale}` }}>
        <ShaderMeshGradient
          speed={0.3 + segment.intensity * 0.5}
          colors={colors}
          distortion={0.5 + segment.intensity * 0.4}
          swirl={0.1 + segment.intensity * 0.2}
        />
      </AbsoluteFill>

      {/* Vignette */}
      <AbsoluteFill
        style={{
          background:
            "radial-gradient(circle at center, transparent 30%, rgba(0,0,0,0.6) 100%)",
          pointerEvents: "none",
        }}
      />

      {/* Glitch effect (chromatic aberration + slice) */}
      {glitchEvent && (
        <AbsoluteFill
          style={{
            boxShadow: `inset ${Math.sin(localFrame * 3) * 15 * glitchEvent.intensity}px 0 0 #ef444488, inset ${-Math.sin(localFrame * 3) * 15 * glitchEvent.intensity}px 0 0 #22d3ee88`,
            pointerEvents: "none",
          }}
        >
          <div
            style={{
              position: "absolute",
              top: "30%",
              left: 0,
              right: 0,
              height: 6,
              backgroundColor: "#ef4444",
              opacity: 0.7 * glitchEvent.intensity,
              transform: `translateX(${Math.sin(localFrame * 4) * 30}px)`,
            }}
          />
          <div
            style={{
              position: "absolute",
              top: "60%",
              left: 0,
              right: 0,
              height: 8,
              backgroundColor: "#22d3ee",
              opacity: 0.5 * glitchEvent.intensity,
              transform: `translateX(${-Math.sin(localFrame * 4) * 30}px)`,
            }}
          />
        </AbsoluteFill>
      )}

      {/* Flash overlay (white flash) */}
      {flashEvent && (
        <AbsoluteFill
          style={{
            backgroundColor: "white",
            opacity: flashEvent.intensity * 0.85,
            pointerEvents: "none",
          }}
        />
      )}

      {/* Segment label — kinetic center build (entrance only, first 60 frames) */}
      {localFrame < 60 && (
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

      {/* Persistent UI overlays — fade in after kinetic build completes */}
      {localFrame >= 60 && (
        <AbsoluteFill style={{ opacity: interpolate(localFrame, [60, 80], [0, 1], { extrapolateRight: "clamp" }) }}>
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
              Scene {segmentIndex + 1}
            </div>
            <div
              style={{
                color: "white",
                fontSize: 36,
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
              <div
                style={{
                  color: "#94a3b8",
                  fontSize: 13,
                  fontFamily: "monospace",
                }}
              >
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
                fontSize: 32,
                fontWeight: 800,
                fontFamily: "monospace",
                textShadow: "0 2px 12px rgba(0,0,0,0.6)",
              }}
            >
              {fmtTime(segment.start + localTime)}{" "}
              <span style={{ color: "#475569", fontSize: 20 }}>
                / {fmtTime(song.duration)}
              </span>
            </div>
            <div
              style={{
                color: "#22d3ee",
                fontSize: 14,
                fontWeight: 700,
                marginTop: 4,
              }}
            >
              {song.tempo} BPM
            </div>
          </div>

          {/* Center: stats grid with number-wheels */}
          <div
            style={{
              position: "absolute",
              top: "50%",
              left: "50%",
              transform: "translate(-50%, -50%)",
              display: "flex",
              gap: 80,
              opacity: 0.85,
            }}
          >
            <div style={{ textAlign: "center" }}>
              <NumberWheel
                from={0}
                to={Math.floor(segment.intensity * 100)}
                fontSize={56}
                color="white"
                speed={1}
              />
              <div
                style={{
                  color: "#94a3b8",
                  fontSize: 11,
                  letterSpacing: 2,
                  textTransform: "uppercase",
                  marginTop: 8,
                  fontFamily: "Inter, system-ui, sans-serif",
                }}
              >
                Intensity %
              </div>
            </div>
            <div style={{ textAlign: "center" }}>
              <NumberWheel
                from={0}
                to={segmentEvents.filter((e) => e.effect === "Cut").length}
                fontSize={56}
                color="#94a3b8"
                speed={1}
              />
              <div
                style={{
                  color: "#94a3b8",
                  fontSize: 11,
                  letterSpacing: 2,
                  textTransform: "uppercase",
                  marginTop: 8,
                  fontFamily: "Inter, system-ui, sans-serif",
                }}
              >
                Cut Events
              </div>
            </div>
            <div style={{ textAlign: "center" }}>
              <NumberWheel
                from={0}
                to={segmentEvents.filter((e) => e.effect === "Flash").length}
                fontSize={56}
                color="#facc15"
                speed={1}
              />
              <div
                style={{
                  color: "#94a3b8",
                  fontSize: 11,
                  letterSpacing: 2,
                  textTransform: "uppercase",
                  marginTop: 8,
                  fontFamily: "Inter, system-ui, sans-serif",
                }}
              >
                Flash Events
              </div>
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

          {/* Bottom: waveform */}
          <WaveformViz
            waveform={song.waveform}
            currentTime={segment.start + localTime}
            duration={song.duration}
          />
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};

// ─── Title scene (first 3 seconds) ──────────────────────────────────────────

const TitleScene: React.FC<{ song: SongData }> = ({ song }) => {
  const frame = useCurrentFrame();

  // Fade out at end (last 30 frames of title duration = 90 frames total)
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
          background:
            "radial-gradient(circle at center, transparent 20%, rgba(0,0,0,0.7) 100%)",
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
        {/* "NOW PLAYING" eyebrow */}
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

        {/* Song title with soft blur in */}
        <SoftBlurIn
          text={song.title}
          fontSize={72}
          color="white"
          fontWeight={800}
          blur={20}
          speed={1}
        />

        {/* Subtitle: stats line */}
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

        {/* Brand chip */}
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
          v0.4.0 · Beat + Onset + Intensity → Effect Mapping
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// ─── Waveform visualization (bottom strip) ──────────────────────────────────

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

const Timeline: React.FC<{ segments: Segment[]; currentTime: number; duration: number }> = ({
  segments,
  currentTime,
  duration,
}) => {
  const progress = currentTime / duration;
  const width = 1160;

  return (
    <div
      style={{
        position: "absolute",
        bottom: 30,
        left: 60,
        width,
        height: 30,
      }}
    >
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

  // Find fade in/out events
  const fadeInEvent = song.events.find((e) => e.effect === "Fade In");
  const fadeOutEvent = song.events.find((e) => e.effect === "Fade Out");
  const titleEvent = song.events.find((e) => e.effect === "Title");

  // Fade overlay state
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

  // Build scene list with transitions for TransitionSeries
  // First scene = title (3s = 90 frames), then each segment as a scene
  // NOTE: compute synchronously (no useMemo) because hooks can't be after early return
  const titleEventForScenes = song?.events.find((e) => e.effect === "Title");
  const scenes: Array<{ type: "title" | "scene"; durationInFrames: number; segment?: Segment }> = [];
  if (song) {
    const titleFrames = titleEventForScenes ? Math.round(titleEventForScenes.duration * fps) : 90;
    scenes.push({ type: "title", durationInFrames: titleFrames });
    for (const seg of song.segments) {
      scenes.push({
        type: "scene",
        durationInFrames: Math.max(1, Math.round((seg.end - seg.start) * fps)),
        segment: seg,
      });
    }
  }

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0a0f", fontFamily: "Inter, system-ui, sans-serif" }}>
      <Audio src={staticFile("audio.mp3")} />

      {/* TransitionSeries drives scene transitions with whip-pan between segments */}
      <TransitionSeries>
        {scenes.map((scene, i) => (
          <React.Fragment key={i}>
            <TransitionSeries.Sequence durationInFrames={scene.durationInFrames}>
              {scene.type === "title" ? (
                <TitleSceneWrapper song={song} startFrame={0} />
              ) : scene.segment ? (
                <SceneWrapper song={song} segment={scene.segment} segmentIndex={i - 1} />
              ) : null}
            </TransitionSeries.Sequence>
            {/* Whip-pan transition between scenes (except after last) */}
            {i < scenes.length - 1 && (
              <TransitionSeries.Transition
                presentation={whipPan({ direction: i % 2 === 0 ? "left" : "right", blur: 18 })}
                timing={linearTiming({ durationInFrames: 12 })}
              />
            )}
          </React.Fragment>
        ))}
      </TransitionSeries>

      {/* Fade in/out overlays — always on top */}
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

      {/* Persistent timeline at bottom (always visible) */}
      <Timeline
        segments={song.segments}
        currentTime={currentTime}
        duration={song.duration}
      />

      {/* Top-center: brand mark */}
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
        audio2scene × remocn · Remotion Preview
      </div>
    </AbsoluteFill>
  );
};

// ─── Wrappers (need to track local frame within Sequence) ───────────────────

const TitleSceneWrapper: React.FC<{ song: SongData; startFrame: number }> = ({ song }) => {
  // Inside TransitionSeries.Sequence, useCurrentFrame() returns local frame (0 at sequence start)
  return <TitleScene song={song} />;
};

const SceneWrapper: React.FC<{ song: SongData; segment: Segment; segmentIndex: number }> = ({
  song,
  segment,
  segmentIndex,
}) => {
  // Inside TransitionSeries.Sequence, useCurrentFrame() returns local frame
  return <Scene segment={segment} song={song} segmentIndex={segmentIndex} isLast={segmentIndex === song.segments.length - 1} />;
};

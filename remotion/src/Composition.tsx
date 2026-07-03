import React, { useEffect, useState } from "react";
import {
  AbsoluteFill,
  Audio,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

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

// ─── Effect color palette (match HTML preview) ──────────────────────────────

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

// ─── Scene background — gradient that changes per segment ───────────────────

const SceneBackground: React.FC<{ segment: Segment | null; intensity: number }> = ({ segment, intensity }) => {
  const baseColor = segment ? LABEL_COLORS[segment.label] || "#a855f7" : "#1a1a2e";
  // Brightness scaled by intensity (0.5..1.0)
  const brightness = 0.4 + intensity * 0.6;

  return (
    <AbsoluteFill
      style={{
        background: `radial-gradient(circle at 50% 50%, ${baseColor}40 0%, #0a0a0f 70%)`,
        filter: `brightness(${brightness})`,
        transition: "background 0.2s ease-out",
      }}
    />
  );
};

// ─── Waveform bar visualization (uses pre-computed peaks) ────────────────────

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
        bottom: 100,
        left: 60,
        right: 60,
        height: 80,
        display: "flex",
        alignItems: "flex-end",
        gap: 2,
        opacity: 0.7,
      }}
    >
      {waveform.map((v, i) => {
        const isPast = i / N < progress;
        return (
          <div
            key={i}
            style={{
              flex: 1,
              height: `${v * 100}%`,
              backgroundColor: isPast ? "#22d3ee" : "#475569",
              borderRadius: 1,
              minHeight: 2,
            }}
          />
        );
      })}
    </div>
  );
};

// ─── Timeline progress bar with event ticks ─────────────────────────────────

const Timeline: React.FC<{ events: VideoEvent[]; currentTime: number; duration: number; segments: Segment[] }> = ({
  events,
  currentTime,
  duration,
  segments,
}) => {
  const progress = currentTime / duration;
  const width = 1160; // 1280 - 60*2

  return (
    <div
      style={{
        position: "absolute",
        bottom: 30,
        left: 60,
        width,
        height: 50,
      }}
    >
      {/* Track */}
      <div
        style={{
          position: "absolute",
          top: 24,
          left: 0,
          right: 0,
          height: 4,
          backgroundColor: "#1e293b",
          borderRadius: 2,
        }}
      />
      {/* Filled progress */}
      <div
        style={{
          position: "absolute",
          top: 24,
          left: 0,
          width: `${progress * 100}%`,
          height: 4,
          backgroundColor: "#22d3ee",
          borderRadius: 2,
        }}
      />
      {/* Segment markers as colored bars */}
      {segments.map((seg, i) => {
        const left = (seg.start / duration) * width;
        const segWidth = ((seg.end - seg.start) / duration) * width;
        return (
          <div
            key={`seg-${i}`}
            style={{
              position: "absolute",
              top: 18,
              left,
              width: segWidth,
              height: 4,
              backgroundColor: LABEL_COLORS[seg.label] || "#a855f7",
              opacity: 0.6,
            }}
          />
        );
      })}
      {/* Event ticks */}
      {events.map((ev, i) => {
        const x = (ev.time / duration) * width;
        const color = EFFECT_COLORS[ev.effect];
        const isStrong = ev.effect === "Flash" || ev.effect === "Glitch" || ev.effect === "Title";
        return (
          <div
            key={`ev-${i}`}
            style={{
              position: "absolute",
              top: isStrong ? 8 : 14,
              left: x,
              width: isStrong ? 3 : 1,
              height: isStrong ? 24 : 16,
              backgroundColor: color,
              opacity: isStrong ? 1 : 0.5,
            }}
          />
        );
      })}
      {/* Playhead */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: progress * width,
          width: 2,
          height: 50,
          backgroundColor: "#ffffff",
          boxShadow: "0 0 8px #22d3ee",
        }}
      />
    </div>
  );
};

// ─── Effect overlays ────────────────────────────────────────────────────────

const FlashOverlay: React.FC<{ active: boolean; intensity: number }> = ({ active, intensity }) => {
  if (!active) return null;
  return (
    <AbsoluteFill
      style={{
        backgroundColor: "white",
        opacity: intensity * 0.9,
        pointerEvents: "none",
      }}
    />
  );
};

const ZoomEffect: React.FC<{ active: boolean; progress: number; intensity: number }> = ({
  active,
  progress,
  intensity,
}) => {
  if (!active) return null;
  const scale = 1 + intensity * 0.3 * progress;
  return (
    <AbsoluteFill
      style={{
        scale: `${scale}`,
        transformOrigin: "center",
        pointerEvents: "none",
      }}
    />
  );
};
void ZoomEffect; // exported for future use; currently inlined in main composition

const GlitchEffect: React.FC<{ active: boolean; intensity: number }> = ({ active, intensity }) => {
  const frame = useCurrentFrame();
  if (!active) return null;
  // Chromatic aberration + horizontal slice
  const offset = Math.sin(frame * 2) * 10 * intensity;
  return (
    <AbsoluteFill
      style={{
        backgroundColor: "transparent",
        boxShadow: `inset ${offset}px 0 0 #ef444488, inset ${-offset}px 0 0 #22d3ee88`,
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          position: "absolute",
          top: "30%",
          left: 0,
          right: 0,
          height: 4,
          backgroundColor: "#ef4444",
          opacity: 0.6 * intensity,
          transform: `translateX(${offset * 2}px)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          top: "60%",
          left: 0,
          right: 0,
          height: 6,
          backgroundColor: "#22d3ee",
          opacity: 0.5 * intensity,
          transform: `translateX(${-offset * 2}px)`,
        }}
      />
    </AbsoluteFill>
  );
};

const FadeOverlay: React.FC<{ type: "in" | "out"; active: boolean; progress: number }> = ({
  type,
  active,
  progress,
}) => {
  if (!active) return null;
  // progress 0..1 over fade duration
  const opacity = type === "in" ? 1 - progress : progress;
  return (
    <AbsoluteFill
      style={{
        backgroundColor: "black",
        opacity,
        pointerEvents: "none",
      }}
    />
  );
};

const TitleCard: React.FC<{ active: boolean; progress: number; songTitle: string }> = ({
  active,
  progress,
  songTitle,
}) => {
  if (!active) return null;
  // Fade in/out: 0..0.3 fade in, 0.7..1 fade out
  let opacity = 1;
  if (progress < 0.3) opacity = progress / 0.3;
  else if (progress > 0.7) opacity = (1 - progress) / 0.3;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "rgba(0,0,0,0.85)",
        opacity,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexDirection: "column",
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          color: "#a855f7",
          fontSize: 24,
          fontFamily: "Inter, system-ui, sans-serif",
          fontWeight: 300,
          letterSpacing: 4,
          marginBottom: 16,
        }}
      >
        NOW PLAYING
      </div>
      <div
        style={{
          color: "white",
          fontSize: 56,
          fontFamily: "Inter, system-ui, sans-serif",
          fontWeight: 700,
          textAlign: "center",
          maxWidth: 800,
        }}
      >
        {songTitle}
      </div>
      <div
        style={{
          marginTop: 24,
          padding: "8px 24px",
          border: "2px solid #22d3ee",
          color: "#22d3ee",
          fontFamily: "Inter, system-ui, sans-serif",
          fontSize: 16,
          fontWeight: 600,
          letterSpacing: 2,
        }}
      >
        AUDIO2SCENE
      </div>
    </AbsoluteFill>
  );
};

// ─── Current segment label (top-left) ───────────────────────────────────────

const SegmentLabel: React.FC<{ segment: Segment | null; intensity: number }> = ({ segment, intensity }) => {
  if (!segment) return null;
  const color = LABEL_COLORS[segment.label] || "#a855f7";

  return (
    <div
      style={{
        position: "absolute",
        top: 30,
        left: 60,
        fontFamily: "Inter, system-ui, sans-serif",
      }}
    >
      <div
        style={{
          color: color,
          fontSize: 14,
          fontWeight: 600,
          letterSpacing: 2,
          marginBottom: 4,
          textTransform: "uppercase",
        }}
      >
        Segment
      </div>
      <div
        style={{
          color: "white",
          fontSize: 32,
          fontWeight: 700,
        }}
      >
        {segment.label}
      </div>
      <div
        style={{
          marginTop: 8,
          display: "flex",
          gap: 12,
          alignItems: "center",
        }}
      >
        <div
          style={{
            padding: "4px 10px",
            backgroundColor: `${color}30`,
            border: `1px solid ${color}`,
            borderRadius: 4,
            color: color,
            fontSize: 12,
            fontWeight: 600,
            letterSpacing: 1,
            textTransform: "uppercase",
          }}
        >
          {segment.intensity_label}
        </div>
        <div
          style={{
            color: "#94a3b8",
            fontSize: 12,
            fontFamily: "monospace",
          }}
        >
          intensity {(intensity * 100).toFixed(0)}%
        </div>
      </div>
    </div>
  );
};

// ─── Top-right stats ────────────────────────────────────────────────────────

const StatsPanel: React.FC<{ song: SongData; currentTime: number }> = ({ song, currentTime }) => {
  const mins = Math.floor(currentTime / 60);
  const secs = Math.floor(currentTime % 60);
  const totalMins = Math.floor(song.duration / 60);
  const totalSecs = Math.floor(song.duration % 60);

  return (
    <div
      style={{
        position: "absolute",
        top: 30,
        right: 60,
        textAlign: "right",
        fontFamily: "Inter, system-ui, sans-serif",
      }}
    >
      <div
        style={{
          color: "white",
          fontSize: 28,
          fontWeight: 700,
          fontFamily: "monospace",
        }}
      >
        {mins}:{secs.toString().padStart(2, "0")}{" "}
        <span style={{ color: "#475569", fontSize: 18 }}>
          / {totalMins}:{totalSecs.toString().padStart(2, "0")}
        </span>
      </div>
      <div
        style={{
          color: "#22d3ee",
          fontSize: 14,
          fontWeight: 600,
          marginTop: 4,
        }}
      >
        {song.tempo} BPM
      </div>
      <div
        style={{
          marginTop: 8,
          color: "#94a3b8",
          fontSize: 12,
        }}
      >
        {song.n_beats} beats · {song.n_onsets} onsets · {song.n_events} events
      </div>
    </div>
  );
};

// ─── Active effect indicator (center-bottom) ────────────────────────────────

const ActiveEffectIndicator: React.FC<{ effect: Effect | null; intensity: number }> = ({
  effect,
  intensity,
}) => {
  if (!effect) return null;
  const color = EFFECT_COLORS[effect];

  return (
    <div
      style={{
        position: "absolute",
        bottom: 200,
        left: "50%",
        transform: "translateX(-50%)",
        padding: "12px 32px",
        backgroundColor: `${color}30`,
        border: `2px solid ${color}`,
        borderRadius: 8,
        color: "white",
        fontFamily: "Inter, system-ui, sans-serif",
        fontSize: 20,
        fontWeight: 700,
        letterSpacing: 4,
        textTransform: "uppercase",
        boxShadow: `0 0 20px ${color}80`,
      }}
    >
      {effect}
      <span style={{ marginLeft: 16, color, fontSize: 14 }}>
        {(intensity * 100).toFixed(0)}%
      </span>
    </div>
  );
};

// ─── Helper: find active segment at time t ──────────────────────────────────

function findSegment(segments: Segment[], t: number): Segment | null {
  for (const seg of segments) {
    if (t >= seg.start && t < seg.end) return seg;
  }
  return segments.length > 0 ? segments[segments.length - 1] : null;
}

// ─── Helper: find active effect at time t (within 100ms window) ─────────────

function findActiveEffect(events: VideoEvent[], t: number, windowSec = 0.15): { effect: Effect | null; intensity: number } {
  // Look for the most recent event within the window
  let best: VideoEvent | null = null;
  for (const ev of events) {
    if (ev.time <= t && ev.time > t - windowSec) {
      if (!best || ev.intensity > best.intensity) best = ev;
    }
  }
  if (best) return { effect: best.effect, intensity: best.intensity };
  return { effect: null, intensity: 0 };
}

// ─── Main composition ───────────────────────────────────────────────────────

export const MyComposition: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const [song, setSong] = useState<SongData | null>(null);

  // Load song data
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
  const segment = findSegment(song.segments, currentTime);
  const { effect: activeEffect, intensity: effectIntensity } = findActiveEffect(song.events, currentTime);

  // Find active fade/title events
  const fadeInEvent = song.events.find((e) => e.effect === "Fade In");
  const fadeOutEvent = song.events.find((e) => e.effect === "Fade Out");
  const titleEvent = song.events.find((e) => e.effect === "Title");

  // Fade state
  let fadeInProgress = 1; // 1 = no fade visible (fully transparent overlay)
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

  // Title state
  let titleProgress = 0;
  let titleActive = false;
  if (titleEvent) {
    const titleEnd = titleEvent.time + titleEvent.duration;
    if (currentTime >= titleEvent.time && currentTime < titleEnd) {
      titleActive = true;
      titleProgress = (currentTime - titleEvent.time) / titleEvent.duration;
    }
  }

  // Zoom effect (find current Zoom event if any)
  const zoomEvent = song.events.find(
    (e) => e.effect === "Zoom" && currentTime >= e.time && currentTime < e.time + e.duration
  );
  const zoomProgress = zoomEvent
    ? (currentTime - zoomEvent.time) / zoomEvent.duration
    : 0;

  // Glitch event (active for 1s)
  const glitchEvent = song.events.find(
    (e) => e.effect === "Glitch" && currentTime >= e.time && currentTime < e.time + 1.0
  );

  // Hold event (active for duration)
  const holdEvent = song.events.find(
    (e) => e.effect === "Hold" && currentTime >= e.time && currentTime < e.time + e.duration
  );

  // Active flash (within 100ms of a Flash event)
  const flashEvent = song.events.find(
    (e) => e.effect === "Flash" && currentTime >= e.time && currentTime < e.time + 0.1
  );

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0a0f", fontFamily: "Inter, system-ui, sans-serif" }}>
      {/* Audio track */}
      <Audio src={staticFile("audio.mp3")} />

      {/* Scene background (changes per segment) */}
      <SceneBackground segment={segment} intensity={segment?.intensity || 0.5} />

      {/* Hold overlay — darkens slightly during Break */}
      {holdEvent && (
        <AbsoluteFill
          style={{
            backgroundColor: "black",
            opacity: 0.3,
            pointerEvents: "none",
          }}
        />
      )}

      {/* Zoom effect (applied to inner content) */}
      <AbsoluteFill
        style={{
          scale: zoomEvent
            ? `${1 + (zoomEvent.intensity * 0.3 * zoomProgress)}`
            : "1",
          transformOrigin: "center",
        }}
      >
        {/* Center "scene" — large visual that reacts to events */}
        <AbsoluteFill
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            pointerEvents: "none",
          }}
        >
          <div
            style={{
              width: 400,
              height: 400,
              borderRadius: 200,
              background: segment
                ? `radial-gradient(circle, ${LABEL_COLORS[segment.label]}80 0%, transparent 70%)`
                : "radial-gradient(circle, #a855f780 0%, transparent 70%)",
              filter: `blur(${flashEvent ? "20px" : "0px"})`,
              opacity: 0.8,
              scale: `${1 + (flashEvent ? 0.2 : 0) + (segment?.intensity ?? 0.5) * 0.3}`,
              transition: "all 0.1s ease-out",
            }}
          />
        </AbsoluteFill>
      </AbsoluteFill>

      {/* Glitch effect overlay */}
      <GlitchEffect active={!!glitchEvent} intensity={glitchEvent?.intensity || 0} />

      {/* Flash overlay (white flash on strong beats/onsets) */}
      <FlashOverlay active={!!flashEvent} intensity={flashEvent?.intensity || 0} />

      {/* Title card overlay */}
      <TitleCard
        active={titleActive}
        progress={titleProgress}
        songTitle={song.title}
      />

      {/* Fade in/out overlays */}
      <FadeOverlay type="in" active={fadeInProgress < 1} progress={fadeInProgress} />
      <FadeOverlay type="out" active={fadeOutProgress > 0} progress={fadeOutProgress} />

      {/* UI overlays */}
      <SegmentLabel segment={segment} intensity={segment?.intensity || 0} />
      <StatsPanel song={song} currentTime={currentTime} />
      <ActiveEffectIndicator effect={activeEffect} intensity={effectIntensity} />

      {/* Bottom: waveform + timeline */}
      <WaveformViz waveform={song.waveform} currentTime={currentTime} duration={song.duration} />
      <Timeline
        events={song.events}
        currentTime={currentTime}
        duration={song.duration}
        segments={song.segments}
      />

      {/* Top-center: project title */}
      <div
        style={{
          position: "absolute",
          top: 30,
          left: "50%",
          transform: "translateX(-50%)",
          color: "#94a3b8",
          fontFamily: "Inter, system-ui, sans-serif",
          fontSize: 14,
          fontWeight: 600,
          letterSpacing: 4,
          textTransform: "uppercase",
        }}
      >
        audio2scene → Remotion Preview
      </div>
    </AbsoluteFill>
  );
};

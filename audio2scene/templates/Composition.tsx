import React, { useEffect, useState } from "react";
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
  return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
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
  return <AbsoluteFill style={{ transform }}>{children}</AbsoluteFill>;
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
  return <AbsoluteFill style={{ scale: `${scale}`, opacity, transformOrigin: "center" }}>{children}</AbsoluteFill>;
};

const IrisPresentation: React.FC<TransitionPresentationComponentProps<Record<string, unknown>>> = ({
  children, presentationProgress, presentationDirection,
}) => {
  const entering = presentationDirection === "entering";
  const p = presentationProgress;
  const radius = entering ? p * 150 : (1 - p) * 150;
  const clipPath = `circle(${radius}% at 50% 50%)`;
  return <AbsoluteFill style={{ clipPath, WebkitClipPath: clipPath }}>{children}</AbsoluteFill>;
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
    <AbsoluteFill style={{ transform: `translateX(${offset * sign}%)`, filter: `blur(${Math.sin(p * Math.PI) * 8}px)` }}>
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
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ opacity: fadeOut, backgroundColor: "#0a0a0f" }}>
      <AbsoluteFill
        style={{
          background: "radial-gradient(circle at center, #a855f740 0%, #0a0a0f 70%)",
        }}
      />
      <AbsoluteFill
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 24,
          fontFamily: "Inter, system-ui, sans-serif",
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
          ◆ Now Playing
        </div>
        <div
          style={{
            color: "white",
            fontSize: 64,
            fontWeight: 800,
            textAlign: "center",
            maxWidth: "80%",
            opacity: interpolate(frame, [10, 30], [0, 1], { extrapolateRight: "clamp" }),
            transform: `scale(${interpolate(frame, [10, 30], [0.9, 1], { extrapolateRight: "clamp" })})`,
          }}
        >
          {slice.text || timeline.title}
        </div>
        <div
          style={{
            marginTop: 16,
            display: "flex",
            gap: 24,
            color: "#94a3b8",
            fontSize: 16,
            fontFamily: "monospace",
            opacity: interpolate(frame, [30, 60], [0, 1], { extrapolateRight: "clamp" }),
          }}
        >
          <span style={{ color: "#22d3ee" }}>{timeline.tempo} BPM</span>
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
    <AbsoluteFill style={{ backgroundColor: "#0a0a0f" }}>
      {slice.video ? (
        <AbsoluteFill>
          <Video
            src={staticFile(`videos/${slice.video}`)}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
            muted
          />
          <AbsoluteFill style={{ backgroundColor: "rgba(0,0,0,0.4)" }} />
        </AbsoluteFill>
      ) : (
        <AbsoluteFill
          style={{
            background: `radial-gradient(circle at center, ${color}40 0%, #0a0a0f 70%)`,
          }}
        />
      )}

      <div
        style={{
          position: "absolute",
          top: 30,
          left: 40,
          fontFamily: "Inter, system-ui, sans-serif",
          opacity: interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" }),
        }}
      >
        <div
          style={{
            color,
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: 3,
            textTransform: "uppercase",
            marginBottom: 4,
          }}
        >
          {slice.kind === "main" ? "Main" : slice.segment_label}
        </div>
        <div
          style={{
            color: "white",
            fontSize: 24,
            fontWeight: 800,
            textShadow: "0 2px 12px rgba(0,0,0,0.8)",
          }}
        >
          {slice.segment_label}
        </div>
        <div
          style={{
            marginTop: 6,
            padding: "3px 10px",
            backgroundColor: `${color}30`,
            border: `1px solid ${color}`,
            borderRadius: 4,
            color,
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: 1,
            textTransform: "uppercase",
            display: "inline-block",
          }}
        >
          {slice.segment_intensity_label}
        </div>
      </div>

      <div
        style={{
          position: "absolute",
          top: 30,
          right: 40,
          textAlign: "right",
          fontFamily: "monospace",
          color: "white",
          fontSize: 20,
          fontWeight: 700,
          textShadow: "0 2px 12px rgba(0,0,0,0.8)",
        }}
      >
        {fmtTime(localTime)}
        <span style={{ color: "#475569", fontSize: 14 }}>{` / ${fmtTime(timeline.duration)}`}</span>
      </div>

      {slice.text && (
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
              color: "white",
              fontSize: 48,
              fontWeight: 800,
              textAlign: "center",
              maxWidth: "80%",
              textShadow: "0 4px 24px rgba(0,0,0,0.9)",
              fontFamily: "Inter, system-ui, sans-serif",
              opacity: interpolate(frame, [10, 30, 60, 80], [0, 1, 1, 0], {
                extrapolateRight: "clamp",
              }),
            }}
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
  const sliceDuration = slice.end - slice.start;
  const progress = (frame / fps) / sliceDuration;

  const scale = 1 + progress * 0.15;
  const translateX = progress * 30 - 15;

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0a0f" }}>
      {slice.image ? (
        <AbsoluteFill>
          <Img
            src={staticFile(`images/${slice.image}`)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              transform: `scale(${scale}) translateX(${translateX}px)`,
            }}
          />
          <AbsoluteFill style={{ backgroundColor: "rgba(0,0,0,0.5)" }} />
        </AbsoluteFill>
      ) : (
        <AbsoluteFill
          style={{
            background: "radial-gradient(circle at center, #94a3b840 0%, #0a0a0f 70%)",
          }}
        />
      )}

      <AbsoluteFill
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "Inter, system-ui, sans-serif",
        }}
      >
        <div
          style={{
            color: "#94a3b8",
            fontSize: 14,
            fontWeight: 700,
            letterSpacing: 6,
            textTransform: "uppercase",
            opacity: interpolate(frame, [0, 15], [0, 0.8], { extrapolateRight: "clamp" }),
          }}
        >
          ◆ Break
        </div>
      </AbsoluteFill>

      {slice.text && (
        <AbsoluteFill
          style={{
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "center",
            paddingBottom: 120,
            pointerEvents: "none",
          }}
        >
          <div
            style={{
              color: "white",
              fontSize: 36,
              fontWeight: 800,
              textAlign: "center",
              maxWidth: "80%",
              textShadow: "0 4px 24px rgba(0,0,0,0.9)",
              opacity: interpolate(frame, [10, 30, 60, 80], [0, 1, 1, 0], {
                extrapolateRight: "clamp",
              }),
            }}
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

  const fadeToBlack = interpolate(progress, [0.6, 1.0], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0a0f" }}>
      <AbsoluteFill
        style={{
          background: "radial-gradient(circle at center, #818cf840 0%, #0a0a0f 70%)",
        }}
      />
      <AbsoluteFill
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 24,
          fontFamily: "Inter, system-ui, sans-serif",
          opacity: 1 - fadeToBlack,
        }}
      >
        <div
          style={{
            color: "#818cf8",
            fontSize: 14,
            fontWeight: 700,
            letterSpacing: 6,
            textTransform: "uppercase",
            opacity: interpolate(frame, [0, 15], [0, 1], { extrapolateRight: "clamp" }),
          }}
        >
          ◆ Outro
        </div>
        <div
          style={{
            color: "white",
            fontSize: 56,
            fontWeight: 800,
            textAlign: "center",
            maxWidth: "80%",
            opacity: interpolate(frame, [10, 30], [0, 1], { extrapolateRight: "clamp" }),
          }}
        >
          {slice.text || "Thanks for watching"}
        </div>
      </AbsoluteFill>
      <AbsoluteFill style={{ backgroundColor: "black", opacity: fadeToBlack }} />
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
        style={{
          backgroundColor: "#0a0a0f",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "white",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        Loading timeline...
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill
      style={{ backgroundColor: "#0a0a0f", fontFamily: "Inter, system-ui, sans-serif" }}
    >
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

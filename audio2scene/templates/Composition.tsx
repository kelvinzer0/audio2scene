import React, { useEffect, useState } from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  Easing,
} from "remotion";
import { Video } from "@remotion/media";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import type { TransitionPresentation } from "@remotion/transitions";
import type { TransitionPresentationComponentProps } from "@remotion/transitions";

// ─── Typography components (from remocn registry) ───────────────────────────
import { SoftBlurIn } from "./components/remocn/soft-blur-in";
import { PerCharacterRise } from "./components/remocn/per-character-rise";
import { BottomUpLetters } from "./components/remocn/bottom-up-letters";
import { TopDownLetters } from "./components/remocn/top-down-letters";
import { SpringScaleIn } from "./components/remocn/spring-scale-in";
import { MicroScaleFade } from "./components/remocn/micro-scale-fade";
import { ScaleDownFade } from "./components/remocn/scale-down-fade";
import { BlurOutUp } from "./components/remocn/blur-out-up";
import { FocusBlurResolve } from "./components/remocn/focus-blur-resolve";
import { LineByLineSlide } from "./components/remocn/line-by-line-slide";
import { PerWordCrossfade } from "./components/remocn/per-word-crossfade";
import { FadeThrough } from "./components/remocn/fade-through";
import { SharedAxisY } from "./components/remocn/shared-axis-y";
import { SharedAxisZ } from "./components/remocn/shared-axis-z";
import { ShortSlideRight } from "./components/remocn/short-slide-right";
import { KineticCenterBuild } from "./components/remocn/kinetic-center-build";
import { ShortSlideDown } from "./components/remocn/short-slide-down";
import { StaggeredFadeUp } from "./components/remocn/staggered-fade-up";
import { MaskRevealUp } from "./components/remocn/mask-reveal-up";
import { TrackingIn } from "./components/remocn/tracking-in";
import { InlineHighlight } from "./components/remocn/inline-highlight";
import { MarkerHighlight } from "./components/remocn/marker-highlight";
import { ShimmerSweep } from "./components/remocn/shimmer-sweep";
import { Typewriter } from "./components/remocn/typewriter";
import { SlotMachineRoll } from "./components/remocn/slot-machine-roll";
import { NumberWheel } from "./components/remocn/number-wheel";
import { RollingNumber } from "./components/remocn/rolling-number";
import { InfiniteMarquee } from "./components/remocn/infinite-marquee";
import { PerspectiveMarquee } from "./components/remocn/perspective-marquee";
import { MatrixDecode } from "./components/remocn/matrix-decode";
import { RGBGlitchText } from "./components/remocn/rgb-glitch-text";

// ─── Types ──────────────────────────────────────────────────────────────────

interface SceneSlice {
  kind: string;            // "text" | "video" | "image" (background type)
  start: number;
  end: number;
  text: string | null;
  effect: string;          // typography effect name
  video: string | null;
  image: string | null;
  transition: string;
  transition_duration_frames: number;
  segment_label: string;
  segment_intensity: number;
  segment_intensity_label: string;
}

interface Timeline {
  title: string;
  duration: number;
  tempo: number;
  fps: number;
  width: number;
  height: number;
  font: string | null;
  slices: SceneSlice[];
}

// ─── Typography renderer — picks component by effect name ───────────────────

const TYPOGRAPHY_PROPS = {
  fontSize: 96,
  color: "#ffffff",
  fontWeight: 800,
};

function renderTypography(effect: string, text: string, fontFamily: string) {
  const baseProps = {
    ...TYPOGRAPHY_PROPS,
    className: "",
    style: { fontFamily },
  };

  // Components that take a single `text` prop
  switch (effect) {
    case "soft-blur-in":         return <SoftBlurIn {...baseProps} text={text} />;
    case "per-character-rise":   return <PerCharacterRise {...baseProps} text={text} />;
    case "bottom-up-letters":    return <BottomUpLetters {...baseProps} text={text} />;
    case "top-down-letters":     return <TopDownLetters {...baseProps} text={text} />;
    case "spring-scale-in":      return <SpringScaleIn {...baseProps} text={text} />;
    case "micro-scale-fade":     return <MicroScaleFade {...baseProps} text={text} />;
    case "scale-down-fade":      return <ScaleDownFade {...baseProps} text={text} />;
    case "blur-out-up":          return <BlurOutUp {...baseProps} text={text} />;
    case "focus-blur-resolve":   return <FocusBlurResolve {...baseProps} text={text} />;
    case "line-by-line-slide":   return <LineByLineSlide {...baseProps} text={text} />;
    case "short-slide-right":    return <ShortSlideRight {...baseProps} text={text} />;
    case "kinetic-center-build": return <KineticCenterBuild {...baseProps} text={text} />;
    case "short-slide-down":     return <ShortSlideDown {...baseProps} text={text} />;
    case "staggered-fade-up":    return <StaggeredFadeUp {...baseProps} text={text} />;
    case "mask-reveal-up":       return <MaskRevealUp {...baseProps} text={text} />;
    case "tracking-in":          return <TrackingIn {...baseProps} text={text} />;
    case "shimmer-sweep":        return <ShimmerSweep {...baseProps} text={text} />;
    case "typewriter":           return <Typewriter {...baseProps} text={text} />;
    case "slot-machine-roll":    return <SlotMachineRoll {...baseProps} from={text} to={text} />;
    case "infinite-marquee":     return <InfiniteMarquee {...baseProps} text={text} />;
    case "perspective-marquee":  return <PerspectiveMarquee {...baseProps} items={[text]} />;
    case "matrix-decode":        return <MatrixDecode {...baseProps} text={text} />;
    case "rgb-glitch-text":      return <RGBGlitchText {...baseProps} text={text} />;
    // Transition-style components: need fromText + toText. Use same text for both
    // so the component still animates (fade between identical strings = entrance animation).
    case "per-word-crossfade":   return <PerWordCrossfade {...baseProps} fromText={text} toText={text} />;
    case "fade-through":         return <FadeThrough {...baseProps} fromText={text} toText={text} />;
    case "shared-axis-y":        return <SharedAxisY {...baseProps} fromText={text} toText={text} />;
    case "shared-axis-z":        return <SharedAxisZ {...baseProps} fromText={text} toText={text} />;
    // Number-based components: render text via SoftBlurIn fallback (these need numeric `to` prop)
    case "number-wheel":
    case "rolling-number":       return <SoftBlurIn {...baseProps} text={text} />;
    // Highlight components: need before/highlight/after — split text at first space
    case "inline-highlight": {
      const parts = text.split(" ");
      if (parts.length >= 2) {
        const highlight = parts[0];
        const before = "";
        const after = parts.slice(1).join(" ");
        return <InlineHighlight {...baseProps} before={before} highlight={highlight} after={after} />;
      }
      return <SoftBlurIn {...baseProps} text={text} />;
    }
    case "marker-highlight": {
      const parts = text.split(" ");
      if (parts.length >= 2) {
        const highlight = parts[0];
        const after = parts.slice(1).join(" ");
        return <MarkerHighlight {...baseProps} highlight={highlight} after={after} />;
      }
      return <SoftBlurIn {...baseProps} text={text} />;
    }
    default:                     return <SoftBlurIn {...baseProps} text={text} />;
  }
}

// ─── Scene transitions (CSS-based, no WebGL) ────────────────────────────────

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

// ─── Background renderer (video / image / gradient) ─────────────────────────

const Background: React.FC<{ slice: SceneSlice }> = ({ slice }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  if (slice.video) {
    return (
      <AbsoluteFill>
        <Video
          src={staticFile(`videos/${slice.video}`)}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
          muted
        />
        <AbsoluteFill style={{ backgroundColor: "rgba(0,0,0,0.55)" }} />
      </AbsoluteFill>
    );
  }

  if (slice.image) {
    // Ken Burns: slow zoom + pan
    const sliceDuration = slice.end - slice.start;
    const progress = (frame / fps) / Math.max(0.1, sliceDuration);
    const scale = 1 + progress * 0.15;
    const translateX = progress * 30 - 15;
    return (
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
        <AbsoluteFill style={{ backgroundColor: "rgba(0,0,0,0.55)" }} />
      </AbsoluteFill>
    );
  }

  // Gradient fallback
  const gradients = [
    "radial-gradient(circle at 30% 30%, #a855f740 0%, #0a0a0f 70%)",
    "radial-gradient(circle at 70% 70%, #22d3ee40 0%, #0a0a0f 70%)",
    "radial-gradient(circle at 50% 50%, #ec489940 0%, #0a0a0f 70%)",
    "radial-gradient(circle at 20% 80%, #facc1540 0%, #0a0a0f 70%)",
    "radial-gradient(circle at 80% 20%, #4ade8040 0%, #0a0a0f 70%)",
  ];
  const gradient = gradients[Math.floor(slice.start) % gradients.length];
  return <AbsoluteFill style={{ background: gradient }} />;
};

// ─── Scene renderer ─────────────────────────────────────────────────────────

const Scene: React.FC<{ slice: SceneSlice; timeline: Timeline }> = ({ slice, timeline }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sliceDuration = slice.end - slice.start;

  // Font family — use Google Font if specified, else system font
  const fontFamily = timeline.font
    ? `'${timeline.font}', system-ui, sans-serif`
    : "system-ui, sans-serif";

  // Fade out near end of slice (last 10 frames)
  const fadeOut = interpolate(
    frame,
    [Math.max(0, sliceDuration * fps - 10), sliceDuration * fps],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0a0f" }}>
      <Background slice={slice} />

      {slice.text && (
        <AbsoluteFill
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            opacity: fadeOut,
            pointerEvents: "none",
          }}
        >
          <div style={{ fontFamily }}>
            {renderTypography(slice.effect, slice.text, fontFamily)}
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};

// ─── Main composition ───────────────────────────────────────────────────────

export const MyComposition: React.FC = () => {
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
    <AbsoluteFill style={{ backgroundColor: "#0a0a0f" }}>
      <Audio src={staticFile("audio.mp3")} />

      <TransitionSeries>
        {timeline.slices.map((slice, i) => {
          const dur = Math.max(2, Math.round((slice.end - slice.start) * fps));
          const transitionDur = Math.min(slice.transition_duration_frames, dur - 2);
          return (
            <React.Fragment key={i}>
              <TransitionSeries.Sequence durationInFrames={dur}>
                <Scene slice={slice} timeline={timeline} />
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

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
  random,
} from "remotion";
import { Video } from "@remotion/media";
import { TransitionSeries, linearTiming } from "@remotion/transitions";
import type { TransitionPresentation } from "@remotion/transitions";
import type { TransitionPresentationComponentProps } from "@remotion/transitions";
import { loadFont } from "@remotion/google-fonts/Inter";

// Load font once at module level
const { fontFamily: LOADED_FONT } = loadFont();

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
import { InfiniteBentoPan } from "./components/remocn/infinite-bento-pan";

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
  logo: string | null;      // logo filename in public/assets/
  symbol: string | null;    // symbol filename in public/assets/
  slices: SceneSlice[];
}

// ─── Typography renderer — picks component by effect name ───────────────────

const TYPOGRAPHY_PROPS = {
  fontSize: 96,
  color: "#ffffff",           // white text for dark background
  fontWeight: 800,
  // Dark theme overrides for highlight components
  baseColor: "#ffffff",       // base text color (for marker/inline highlight)
  highlightedTextColor: "#0a0a0f",  // dark text on highlighted (marker) area
  markerColor: "#facc15",     // yellow marker
  highlightColor: "#22d3ee",  // cyan highlight for inline
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
        // Add leading space to "after" so there's a gap between highlight and after text
        return <MarkerHighlight {...baseProps} highlight={highlight} after={` ${after}`} />;
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

// ─── remocn transitions (imported from registry) ────────────────────────────
import { whipPan } from "./components/remocn/whip-pan";
import { pushThrough } from "./components/remocn/push-through";
import { focusPull } from "./components/remocn/focus-pull";

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
    // remocn transitions (standard shadcn components)
    case "whipPan": return whipPan({ direction: "left", blur: 12 }) as any;
    case "whipPanRight": return whipPan({ direction: "right", blur: 12 }) as any;
    case "pushThrough": return pushThrough() as any;
    case "focusPull": return focusPull() as any;
    default: return { component: FadePresentation, props: {} };
  }
}

// ─── Background renderer (video / image / gradient) ─────────────────────────

// ─── Enhanced Ken Burns image animation (4 patterns) ────────────────────────

const KEN_BURNS_PATTERNS = [
  // Pattern 0: Zoom in + pan right
  (p: number) => ({ scale: 1.15 + p * 0.2, x: p * 40 - 20, y: 0 }),
  // Pattern 1: Zoom out + pan left
  (p: number) => ({ scale: 1.4 - p * 0.2, x: -(p * 40 - 20), y: 0 }),
  // Pattern 2: Zoom in + pan up
  (p: number) => ({ scale: 1.15 + p * 0.2, x: 0, y: -(p * 30 - 15) }),
  // Pattern 3: Zoom in + diagonal pan
  (p: number) => ({ scale: 1.2 + p * 0.15, x: p * 30 - 15, y: p * 20 - 10 }),
];

/**
 * BlurFill wrapper — eliminates black spots in portrait mode.
 * Renders the media TWICE:
 *   1. Background layer: scaled to fill entire frame + heavy blur (covers gaps)
 *   2. Foreground layer: objectFit cover (the actual visible media)
 * This ensures NO black bars even when source aspect ratio differs from output.
 */
const BlurFillVideo: React.FC<{ src: string; scale?: string }> = ({ src, scale = "1.1" }) => {
  return (
    <>
      {/* Blurred background fill — covers any black gaps */}
      <Video
        src={src}
        style={{
          position: "absolute",
          width: "100%",
          height: "100%",
          objectFit: "cover",
          scale: "1.5",
          transform: "scale(1.5)",
          filter: "blur(40px) brightness(0.4)",
          zIndex: 0,
        }}
        muted
        loop
      />
      {/* Foreground — actual visible video */}
      <Video
        src={src}
        style={{
          position: "absolute",
          width: "100%",
          height: "100%",
          objectFit: "cover",
          scale,
          zIndex: 1,
        }}
        muted
        loop
      />
    </>
  );
};

const BlurFillImage: React.FC<{ src: string; transform?: string }> = ({ src, transform }) => {
  return (
    <>
      {/* Blurred background fill */}
      <Img
        src={src}
        style={{
          position: "absolute",
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: "scale(1.5)",
          filter: "blur(40px) brightness(0.4)",
          zIndex: 0,
        }}
      />
      {/* Foreground */}
      <Img
        src={src}
        style={{
          position: "absolute",
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: transform || "scale(1.15)",
          zIndex: 1,
        }}
      />
    </>
  );
};

const Background: React.FC<{ slice: SceneSlice; sceneIndex?: number }> = ({ slice, sceneIndex = 0 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Alternate: even scenes → video, odd scenes → image (if both available)
  const useVideo = sceneIndex % 2 === 0;

  if (slice.video && useVideo) {
    return (
      <AbsoluteFill style={{ overflow: "hidden" }}>
        <BlurFillVideo src={staticFile(`videos/${slice.video}`)} scale="1.1" />
        <AbsoluteFill style={{ backgroundColor: "rgba(0,0,0,0.55)" }} />
      </AbsoluteFill>
    );
  }

  if (slice.image) {
    // Enhanced Ken Burns: pick pattern based on scene index
    const sliceDuration = slice.end - slice.start;
    const progress = (frame / fps) / Math.max(0.1, sliceDuration);
    const patternIdx = sceneIndex % KEN_BURNS_PATTERNS.length;
    const anim = KEN_BURNS_PATTERNS[patternIdx](progress);
    return (
      <AbsoluteFill style={{ overflow: "hidden" }}>
        <BlurFillImage
          src={staticFile(`images/${slice.image}`)}
          transform={`scale(${anim.scale}) translate(${anim.x}px, ${anim.y}px)`}
        />
        {/* Subtle parallax glow overlay for "alive" feel */}
        <AbsoluteFill
          style={{
            zIndex: 2,
            background: `linear-gradient(${135 + progress * 90}deg, rgba(168,85,247,0.15) 0%, rgba(0,0,0,0.5) 50%, rgba(34,211,238,0.1) 100%)`,
          }}
        />
      </AbsoluteFill>
    );
  }

  // Fallback: video if image not available but video is
  if (slice.video) {
    return (
      <AbsoluteFill style={{ overflow: "hidden" }}>
        <BlurFillVideo src={staticFile(`videos/${slice.video}`)} scale="1.1" />
        <AbsoluteFill style={{ backgroundColor: "rgba(0,0,0,0.55)" }} />
      </AbsoluteFill>
    );
  }

  // Infinite Bento Pan fallback (animated, no black spots)
  return (
    <AbsoluteFill style={{ overflow: "hidden", backgroundColor: "#0a0a0f" }}>
      <InfiniteBentoPan panSpeed={0.5} accentColor="#a855f7" />
      <AbsoluteFill style={{ backgroundColor: "rgba(0,0,0,0.3)" }} />
    </AbsoluteFill>
  );
};

// ─── Intro scene (logo animation) ───────────────────────────────────────────

const IntroScene: React.FC<{ slice: SceneSlice; timeline: Timeline }> = ({ slice, timeline }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sliceDuration = slice.end - slice.start;

  // Logo animation: scale from 0.5 → 1.0 + fade in (first 30 frames)
  // Hold (30 to 60), then fade out (last 20 frames)
  const logoScale = interpolate(frame, [0, 30], [0.5, 1.0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const logoOpacity = interpolate(
    frame,
    [0, 15, sliceDuration * fps - 20, sliceDuration * fps],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  // Glow pulse
  const glowIntensity = interpolate(
    Math.sin(frame * 0.1),
    [-1, 1],
    [0.3, 0.7]
  );

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0a0f" }}>
      {/* Animated gradient background */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at center, rgba(168, 85, 247, ${glowIntensity * 0.4}) 0%, #0a0a0f 70%)`,
        }}
      />

      {/* Logo (if provided) */}
      {timeline.logo && (
        <AbsoluteFill
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            opacity: logoOpacity,
            pointerEvents: "none",
          }}
        >
          <Img
            src={staticFile(`assets/${timeline.logo}`)}
            style={{
              maxWidth: "40%",
              maxHeight: "40%",
              objectFit: "contain",
              transform: `scale(${logoScale})`,
              filter: `drop-shadow(0 0 ${20 * glowIntensity}px rgba(168, 85, 247, ${glowIntensity}))`,
            }}
          />
        </AbsoluteFill>
      )}

      {/* Title text below logo — ONLY if no logo provided */}
      {!timeline.logo && slice.text && (
        <AbsoluteFill
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: timeline.logo ? "flex-end" : "center",
            paddingBottom: timeline.logo ? "15%" : 0,
            opacity: interpolate(frame, [20, 40], [0, 1], { extrapolateRight: "clamp" }),
            pointerEvents: "none",
          }}
        >
          <div
            style={{
              fontFamily: timeline.font
                ? `'${timeline.font}', system-ui, sans-serif`
                : "system-ui, sans-serif",
              color: "white",
              fontSize: 48,
              fontWeight: 800,
              textAlign: "center",
              textShadow: "0 4px 24px rgba(0,0,0,0.9)",
            }}
          >
            {slice.text}
          </div>
        </AbsoluteFill>
      )}

      {/* Symbol watermark (bottom-right) */}
      {timeline.symbol && (
        <AbsoluteFill style={{ pointerEvents: "none" }}>
          <Img
            src={staticFile(`assets/${timeline.symbol}`)}
            style={{
              position: "absolute",
              bottom: 30,
              right: 30,
              width: 60,
              height: 60,
              objectFit: "contain",
              opacity: interpolate(frame, [10, 30], [0, 0.6], { extrapolateRight: "clamp" }),
              filter: "drop-shadow(0 2px 8px rgba(0,0,0,0.5))",
            }}
          />
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};

// ─── Scene renderer ─────────────────────────────────────────────────────────

const Scene: React.FC<{ slice: SceneSlice; timeline: Timeline; sceneIndex?: number }> = ({ slice, timeline, sceneIndex = 0 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sliceDuration = slice.end - slice.start;

  // Font family — use loaded Google Font
  const fontFamily = LOADED_FONT || "system-ui, sans-serif";

  // Fade out near end of slice (last 10 frames)
  const fadeOut = interpolate(
    frame,
    [Math.max(0, sliceDuration * fps - 10), sliceDuration * fps],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0a0f" }}>
      <Background slice={slice} sceneIndex={sceneIndex} />

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

      {/* Symbol watermark (persist across all scenes) */}
      {timeline.symbol && (
        <Img
          src={staticFile(`assets/${timeline.symbol}`)}
          style={{
            position: "absolute",
            bottom: 20,
            right: 20,
            width: 40,
            height: 40,
            objectFit: "contain",
            opacity: 0.5,
            filter: "drop-shadow(0 2px 8px rgba(0,0,0,0.5))",
            zIndex: 100,
          }}
        />
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

  // Audio fade out: last 3 seconds always fade to 0
  const fadeOutStartFrame = Math.max(0, Math.round((timeline.duration - 3) * fps));
  const fadeOutEndFrame = Math.round(timeline.duration * fps);

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0a0f" }}>
      <Audio
        src={staticFile("audio.mp3")}
        volume={(frame: number) => {
          if (frame < fadeOutStartFrame) return 1;
          if (frame >= fadeOutEndFrame) return 0;
          return 1 - (frame - fadeOutStartFrame) / (fadeOutEndFrame - fadeOutStartFrame);
        }}
      />

      <TransitionSeries>
        {timeline.slices.map((slice, i) => {
          const dur = Math.max(2, Math.round((slice.end - slice.start) * fps));
          const transitionDur = Math.min(slice.transition_duration_frames, dur - 2);
          // Use IntroScene for first scene if logo is provided
          const isFirst = i === 0;
          const useIntro = isFirst && timeline.logo;
          return (
            <React.Fragment key={i}>
              <TransitionSeries.Sequence durationInFrames={dur}>
                {useIntro ? (
                  <IntroScene slice={slice} timeline={timeline} />
                ) : (
                  <Scene slice={slice} timeline={timeline} sceneIndex={i} />
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

import "./index.css";
import { Composition } from "remotion";
import { MyComposition } from "./Composition";

// DEMI - HomeBody: 141.793s @ 30fps = 4254 frames
const FPS = 30;
const DURATION_SEC = 141.793;
const DURATION_FRAMES = Math.ceil(DURATION_SEC * FPS);

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Audio2ScenePreview"
        component={MyComposition}
        durationInFrames={DURATION_FRAMES}
        fps={FPS}
        width={1280}
        height={720}
      />
    </>
  );
};

import { Composition } from "remotion";
import { Demo, DEMO_DURATION, FPS } from "./Demo";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="demo"
      component={Demo}
      durationInFrames={DEMO_DURATION}
      fps={FPS}
      width={1280}
      height={720}
    />
  );
};

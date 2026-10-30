import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/inter/800.css";
import "@fontsource/inter/400-italic.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/600.css";
import React, { useEffect, useState } from "react";
import { AbsoluteFill, Composition, Sequence, continueRender, delayRender, interpolate, useCurrentFrame } from "remotion";
import { SB, TOTAL_FRAMES, sceneFrames } from "./data";
import { Background } from "./components/Background";
import { Shell } from "./components/Shell";
import { LayoutProbe } from "./components/Probe";
import { Hook } from "./scenes/Hook";
import { Problem } from "./scenes/Problem";
import { Ask } from "./scenes/Ask";
import { Screen } from "./scenes/Screen";
import { Switch } from "./scenes/Switch";
import { Disagree } from "./scenes/Disagree";
import { How } from "./scenes/How";
import { Results } from "./scenes/Results";
import { Close } from "./scenes/Close";

/** Scene id in storyboard.json -> component. Add a scene: add it to the storyboard, then here. */
export const SCENES: Record<string, React.FC<{ dur: number }>> = {
  hook: Hook,
  problem: Problem,
  ask: Ask,
  screen: Screen,
  switch: Switch,
  disagree: Disagree,
  how: How,
  results: Results,
  close: Close,
};

const useFonts = () => {
  const [handle] = useState(() => delayRender("fonts"));
  useEffect(() => {
    const specs = ["400 20px Inter", "500 20px Inter", "600 20px Inter", "700 20px Inter", "800 20px Inter", "italic 400 20px Inter", "400 20px 'JetBrains Mono'", "600 20px 'JetBrains Mono'"];
    Promise.all(specs.map((s) => document.fonts.load(s)))
      .then(() => document.fonts.ready)
      .finally(() => continueRender(handle));
  }, [handle]);
};

export const Main: React.FC<{ check?: boolean }> = ({ check }) => {
  useFonts();
  const f = useCurrentFrame();
  const dis = SB.scenes.find((s) => s.id === "disagree");
  const warm = dis ? interpolate(f, [dis.start * SB.fps, dis.start * SB.fps + 30, dis.end * SB.fps - 30, dis.end * SB.fps], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 0;
  return (
    <AbsoluteFill style={{ background: "#081013" }}>
      <Background warm={warm} />
      {SB.scenes.map((s) => {
        const C = SCENES[s.id];
        const { from, dur } = sceneFrames(s);
        if (!C) return null;
        return (
          <Sequence key={s.id} from={from} durationInFrames={dur} name={s.id}>
            <Shell dur={dur} id={s.id} exit={s.id !== "close"}>
              <C dur={dur} />
            </Shell>
          </Sequence>
        );
      })}
      {check ? <LayoutProbe /> : null}
    </AbsoluteFill>
  );
};

export const RemotionRoot: React.FC = () => (
  <Composition
    id="SecondLook"
    component={Main}
    durationInFrames={TOTAL_FRAMES}
    fps={SB.fps}
    width={SB.width}
    height={SB.height}
    defaultProps={{ check: false }}
  />
);

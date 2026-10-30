import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { expoOut, inOut } from "../lib";

/** Scene wrapper: soft focus-pull in, gentle push-out at the end. Scene timings come from storyboard.json. */
export const Shell: React.FC<{ dur: number; children: React.ReactNode; exit?: boolean; id: string }> = ({
  dur,
  children,
  exit = true,
  id,
}) => {
  const f = useCurrentFrame();
  const inT = interpolate(f, [0, 16], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: expoOut });
  const outT = exit ? interpolate(f, [dur - 12, dur], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: inOut }) : 0;
  const opacity = inT * (1 - outT);
  const scale = 1.025 - 0.025 * inT - 0.02 * outT;
  const blur = (1 - inT) * 10 + outT * 8;
  return (
    <AbsoluteFill data-scene={id} style={{ opacity, transform: `scale(${scale})`, filter: blur > 0.05 ? `blur(${blur}px)` : undefined }}>
      {children}
    </AbsoluteFill>
  );
};

import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { M } from "../data";
import { C } from "../theme";
import { NUM_WORDS, lerp, rand, spr, tween } from "../lib";
import { LetterCard } from "../components/Letter";
import { Chip } from "../components/Bits";
import { Kicker, Words } from "../components/Text";

export const Hook: React.FC<{ dur: number }> = () => {
  const f = useCurrentFrame();
  const docs: any[] = M.documents;
  const n = docs.length;
  const fan = tween(f, 128, 46);
  const roles = Object.values(M.roles).map((r: any) => r.title);
  return (
    <AbsoluteFill>
      {/* letters: fall into a pile, then fan out */}
      <div style={{ position: "absolute", left: 1370, top: 520, perspective: 1600 }}>
        <div style={{ transformStyle: "preserve-3d", transform: `rotateX(${lerp(22, 8, fan)}deg) rotateZ(${lerp(-8, 0, fan)}deg)` }}>
          {docs.map((d, i) => {
            const s = spr(f, 4 + i * 7, 90, 14);
            const c = i - (n - 1) / 2;
            const pileX = i * 5 - 18;
            const pileY = -i * 6;
            const pileR = (rand(i + 2) - 0.5) * 12;
            const fanX = c * 78;
            const fanY = c * c * 7 - 20;
            const fanR = c * 5.5;
            const x = lerp(pileX, fanX, fan);
            const y = lerp(pileY, fanY, fan) - (1 - s) * 700;
            const r = lerp(pileR, fanR, fan) + (1 - s) * (rand(i) - 0.5) * 50;
            return (
              <div
                key={d.id}
                style={{
                  position: "absolute",
                  left: x - 100,
                  top: y - 135,
                  transform: `rotate(${r}deg) translateZ(${i * 4}px)`,
                  opacity: Math.min(1, s * 2),
                  transformOrigin: "50% 120%",
                }}
              >
                <LetterCard date={d.date} title={d.title_en} seed={i + 1} />
              </div>
            );
          })}
        </div>
      </div>

      <div style={{ position: "absolute", left: 140, top: 300, width: 820 }}>
        <Kicker text="One patient · eight letters" at={6} />
        <div style={{ height: 34 }} />
        <Words text={`${NUM_WORDS[n] ?? n} letters.`} at={14} size={118} out={118} />
        <Words text="One patient." at={30} size={118} color={C.muted} out={120} />
      </div>
      <div style={{ position: "absolute", left: 140, top: 360, width: 720 }}>
        <Words text="Every doctor needs different facts." at={138} size={84} accent={["different"]} />
        <div style={{ display: "flex", gap: 14, marginTop: 44, flexWrap: "wrap" }}>
          {roles.map((r, i) => (
            <Chip key={r} at={172 + i * 7} tone={i === 0 ? "teal" : "plain"}>
              {r}
            </Chip>
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};

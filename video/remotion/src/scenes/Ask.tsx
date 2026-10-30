import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { M } from "../data";
import { C, FONT, MONO } from "../theme";
import { dmy, spr, tween } from "../lib";
import { Glass } from "../components/Bits";
import { Kicker, Words } from "../components/Text";

/** Split the typed sentence into the parts the parser picks up (role word, task phrase, date). */
const segments = (text: string) => {
  const role = text.split(/[,:]/)[0];
  const rest = text.slice(role.length);
  const date = /\d{1,2} [A-Z][a-z]+ \d{4}/.exec(rest);
  const taskM = /pre-operative check|tumour board|diabetes|night/i.exec(rest);
  const marks: { s: number; e: number; k: number }[] = [{ s: 0, e: role.length, k: 0 }];
  if (taskM) marks.push({ s: role.length + taskM.index, e: role.length + taskM.index + taskM[0].length, k: 1 });
  if (date) marks.push({ s: role.length + date.index, e: role.length + date.index + date[0].length, k: 2 });
  return marks;
};

export const Ask: React.FC<{ dur: number }> = () => {
  const f = useCurrentFrame();
  const A = M.ask;
  const text: string = A.text;
  const T0 = 22;
  const CPF = 0.62; // characters per frame
  const typed = Math.max(0, Math.min(text.length, Math.floor((f - T0) * CPF)));
  const doneAt = T0 + Math.ceil(text.length / CPF);
  const press = doneAt + 10;
  const pressS = interpolate(f, [press, press + 4, press + 12], [1, 0.94, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const marks = segments(text);
  const markAt = press + 14;
  const cursorOn = Math.floor(f / 15) % 2 === 0 || f < doneAt;

  // render typed text with underline sweeps on recognised parts
  const pieces: React.ReactNode[] = [];
  let pos = 0;
  for (const m of marks) {
    if (m.s > pos) pieces.push(<span key={`p${pos}`}>{text.slice(pos, Math.min(m.s, typed))}</span>);
    if (m.s < typed) {
      const sw = tween(f, markAt + m.k * 12, 22);
      pieces.push(
        <span
          key={`m${m.s}`}
          style={{
            backgroundImage: `linear-gradient(rgba(20,163,148,0.35), rgba(20,163,148,0.35))`,
            backgroundSize: `${sw * 100}% 100%`,
            backgroundRepeat: "no-repeat",
            borderRadius: 6,
            WebkitBoxDecorationBreak: "clone",
            boxDecorationBreak: "clone",
            boxShadow: sw > 0 ? `inset 0 -3px 0 rgba(94,234,212,${sw})` : undefined,
            color: sw > 0.5 ? C.ink : undefined,
          }}
        >
          {text.slice(m.s, Math.min(m.e, typed))}
        </span>,
      );
    }
    pos = m.e;
  }
  if (pos < typed) pieces.push(<span key="tail">{text.slice(pos, typed)}</span>);

  const out = [
    { k: "Role", v: A.role.replace(/_/g, " ").replace(/^./, (c: string) => c.toUpperCase()) },
    { k: "Task", v: A.task },
    { k: "As of", v: dmy(A.as_of) },
  ];
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: 140, top: 120 }}>
        <Kicker text="Ask in one sentence" at={0} />
        <div style={{ height: 26 }} />
        <Words text="Who are you, and what are you doing?" at={4} size={60} color={C.ink2} weight={600} />
      </div>
      <div style={{ position: "absolute", left: 140, top: 340, width: 1640 }}>
        <Glass style={{ minHeight: 124, display: "flex", alignItems: "center", padding: "22px 22px 22px 40px", gap: 24, borderRadius: 26, boxShadow: `0 40px 100px rgba(0,0,0,.5), 0 0 0 ${f > press ? 2 : 0}px rgba(94,234,212,.35)` }}>
          <div style={{ flex: 1, fontSize: 42, fontWeight: 500, color: C.ink2, lineHeight: 1.4, minHeight: 118, letterSpacing: "-0.01em" }}>
            {pieces}
            <span style={{ display: "inline-block", width: 3, height: 44, marginLeft: 3, verticalAlign: "middle", background: C.tealHi, opacity: cursorOn ? 1 : 0 }} />
          </div>
          <div
            style={{
              flex: "none",
              padding: "22px 32px",
              borderRadius: 18,
              background: C.teal,
              fontSize: 26,
              fontWeight: 600,
              color: "#fff",
              transform: `scale(${pressS})`,
              boxShadow: f > press ? `0 0 40px rgba(20,163,148,.6)` : "none",
            }}
          >
            Build briefing
          </div>
        </Glass>
      </div>
      {/* what was understood */}
      <div style={{ position: "absolute", left: 140, top: 560, width: 1640, display: "flex", gap: 24, alignItems: "flex-start" }}>
        {out.map((o, i) => {
          const s = spr(f, markAt + 22 + i * 12, 120, 16);
          return (
            <div key={o.k} style={{ flex: i === 1 ? 1.6 : 1, opacity: s, transform: `translateY(${(1 - s) * -60}px)` }}>
              <div style={{ margin: "0 auto", width: 2, height: 46 * s, background: `linear-gradient(${C.tealHi}, transparent)` }} />
              <Glass style={{ padding: "24px 30px" }}>
                <div style={{ fontFamily: MONO, fontSize: 17, letterSpacing: "0.18em", textTransform: "uppercase", color: C.tealHi }}>{o.k}</div>
                <div style={{ fontSize: 34, fontWeight: 600, marginTop: 10, letterSpacing: "-0.01em" }}>{o.v}</div>
              </Glass>
            </div>
          );
        })}
      </div>
      <div style={{ position: "absolute", left: 140, top: 840, width: 1640, fontFamily: FONT }}>
        <Words text={`${A.needs} needs from the rulebook. The app never sees the questions.`} at={markAt + 70} size={40} weight={500} color={C.ink2} accent={[String(A.needs)]} stagger={2} />
        <div style={{ marginTop: 18, fontFamily: MONO, fontSize: 20, color: C.muted, opacity: tween(f, markAt + 96, 20) }}>
          briefing built in {Math.round(A.ms)} ms · rule-based, no AI call
        </div>
      </div>
    </AbsoluteFill>
  );
};

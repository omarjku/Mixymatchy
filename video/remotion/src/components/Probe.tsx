import { useEffect, useState } from "react";
import { continueRender, delayRender, useCurrentFrame } from "remotion";
import { SAFE } from "../theme";

/**
 * Layout check (only with inputProps {check: true}): measures every visible text run and logs
 * "LAYOUT {json}" to the browser console, which video/scripts/check_visual.mjs collects.
 *   offsafe  text outside the 5% title-safe area
 *   clipped  text cut off by an overflow:hidden ancestor (ignored for the masked rise animation)
 */
export const LayoutProbe = () => {
  const frame = useCurrentFrame();
  const [handle] = useState(() => delayRender("layout-probe"));
  useEffect(() => {
    const id = requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        const issues: any[] = [];
        const W = 1920;
        const H = 1080;
        const opacityOf = (el: Element | null) => {
          let o = 1;
          while (el && el instanceof HTMLElement) {
            o *= parseFloat(getComputedStyle(el).opacity || "1");
            el = el.parentElement;
          }
          return o;
        };
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let n: Node | null;
        let texts = 0;
        while ((n = walker.nextNode())) {
          const t = (n.textContent || "").trim();
          if (!t) continue;
          const el = n.parentElement;
          if (!el || el.closest("[data-decor]")) continue;
          if (opacityOf(el) < 0.35) continue;
          const r = document.createRange();
          r.selectNodeContents(n);
          const rects = Array.from(r.getClientRects()).filter((x) => x.width > 0 && x.height > 0);
          if (!rects.length) continue;
          texts++;
          const scene = el.closest("[data-scene]")?.getAttribute("data-scene");
          for (const b of rects) {
            if (b.left < SAFE.x - 1 || b.top < SAFE.y - 1 || b.right > W - SAFE.x + 1 || b.bottom > H - SAFE.y + 1) {
              issues.push({ kind: "offsafe", scene, text: t.slice(0, 60), box: [b.left, b.top, b.right, b.bottom].map(Math.round) });
              break;
            }
          }
          // clipping by an overflow-hidden ancestor
          let a = el.parentElement;
          while (a && a !== document.body) {
            const cs = getComputedStyle(a);
            if ((cs.overflow === "hidden" || cs.overflowX === "hidden") && !a.hasAttribute("data-mask")) {
              const ab = a.getBoundingClientRect();
              const tb = rects[rects.length - 1];
              if (tb.right > ab.right + 2 || rects[0].left < ab.left - 2) {
                issues.push({ kind: "clipped", scene, text: t.slice(0, 60) });
              }
              break;
            }
            a = a.parentElement;
          }
        }
        console.log("LAYOUT " + JSON.stringify({ frame, texts, issues }));
        continueRender(handle);
      }),
    );
    return () => cancelAnimationFrame(id);
  }, [frame, handle]);
  return null;
};

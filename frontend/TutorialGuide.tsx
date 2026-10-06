import React, { RefObject, useEffect, useRef, useState } from "react";
import { tutorialSteps } from "./tutorial";

type Box = { left: number; top: number; width: number; height: number };
export function Tutorial({
  step,
  run,
  root,
  move,
  exit,
}: {
  step: number;
  run: number;
  root: RefObject<HTMLDivElement | null>;
  move: (step: number) => void;
  exit: () => void;
}) {
  const panel = useRef<HTMLElement>(null);
  const [box, setBox] = useState<Box | null>(null);
  const [cursor, setCursor] = useState({ x: 28, y: 100 });
  const [phase, setPhase] = useState("Preparing demonstration");
  const [moving, setMoving] = useState(true);
  const [pulse, setPulse] = useState(false);
  const [failed, setFailed] = useState(false);
  const [reduced, setReduced] = useState(false);
  const item = tutorialSteps[step];
  useEffect(() => {
    const media = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(media?.matches ?? false);
    update();
    media?.addEventListener("change", update);
    return () => media?.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    panel.current?.focus();
    function key(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        exit();
      }
      if (event.key !== "Tab") return;
      const controls = Array.from(
        panel.current?.querySelectorAll<HTMLElement>(
          "button:not([disabled])",
        ) || [],
      );
      const first = controls[0],
        last = controls.at(-1);
      if (
        event.shiftKey &&
        (document.activeElement === first ||
          document.activeElement === panel.current)
      ) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [exit]);
  useEffect(() => {
    const cancel = new AbortController();
    let target: HTMLElement | null = null;
    const wait = (ms: number) =>
      new Promise<void>((resolve) => {
        const timer = setTimeout(done, ms);
        function done() {
          clearTimeout(timer);
          cancel.signal.removeEventListener("abort", done);
          resolve();
        }
        cancel.signal.addEventListener("abort", done, { once: true });
      });
    const locate = (selector: string) =>
      root.current?.querySelector<HTMLElement>(selector) || null;
    const measure = () => {
      if (!target || !target.isConnected) {
        setBox(null);
        return;
      }
      const rect = target.getBoundingClientRect();
      const bottom = Math.min(rect.bottom, innerHeight - 8);
      const top = Math.max(8, rect.top);
      setBox(
        bottom > top
          ? {
              left: Math.max(5, rect.left - 5),
              top,
              width: Math.min(rect.width + 10, innerWidth - 10),
              height: bottom - top,
            }
          : null,
      );
    };
    const reveal = (element: HTMLElement) => {
      element.scrollIntoView({
        block: "center",
        inline: "nearest",
        behavior: "instant",
      });
      if (!element.closest(".sidebar")) {
        const rect = element.getBoundingClientRect();
        const head = root.current
          ?.querySelector(".sidebar")
          ?.getBoundingClientRect();
        const top =
          innerWidth <= 800 ? Math.min(head?.height || 0, 150) + 16 : 32;
        window.scrollBy({ top: rect.top - top, behavior: "instant" });
      }
    };
    const description = panel.current?.querySelector("#tutorial-description");
    if (description) description.scrollTop = 0;
    setMoving(true);
    setFailed(false);
    setPulse(false);
    setBox(null);
    setPhase("Preparing demonstration");
    async function demonstrate() {
      await wait(80);
      if (cancel.signal.aborted) return;
      target = locate(item.target);
      if (!target) {
        setFailed(true);
        setMoving(false);
        setPhase(
          "This step could not locate its control. Replay the step or exit and restart.",
        );
        return;
      }
      reveal(target);
      await wait(80);
      if (cancel.signal.aborted) return;
      measure();
      const rect = target.getBoundingClientRect();

      setCursor({
        x: Math.max(
          12,
          Math.min(innerWidth - 24, rect.left + Math.min(rect.width / 2, 110)),
        ),
        y: Math.max(
          12,
          Math.min(innerHeight - 24, rect.top + Math.min(rect.height / 2, 24)),
        ),
      });
      setPhase(
        item.click ? "Moving to the control" : "Showing the relevant area",
      );
      await wait(reduced ? 40 : 650);
      if (cancel.signal.aborted) return;
      if (item.click) {
        setPulse(true);
        setPhase("Clicked: " + item.action);
        target.click();
        await wait(reduced ? 40 : 350);
        if (cancel.signal.aborted) return;
      } else setPhase("Highlighted: " + item.action);
      target = locate(item.after || item.target);
      if (target) {
        reveal(target);
        measure();
      }
      setMoving(false);
    }
    void demonstrate();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      cancel.abort();
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [step, run, reduced]);
  return (
    <div className={"tutorial-overlay" + (reduced ? " reduced-motion" : "")}>
      <div className="tutorial-shield" aria-hidden="true" />
      {box && (
        <div className="tutorial-highlight" style={box} aria-hidden="true" />
      )}
      <div
        className={"tutorial-cursor" + (pulse ? " clicked" : "")}
        style={{ transform: `translate(${cursor.x}px, ${cursor.y}px)` }}
        aria-hidden="true"
      >
        <svg width="28" height="34" viewBox="0 0 28 34">
          <path
            d="M3 2v25l7-7 5 11 5-3-5-10h10Z"
            fill="#fff"
            stroke="#183f35"
            strokeWidth="2"
          />
        </svg>
        <span className="click-ring" />
      </div>
      <section
        ref={panel}
        className="tutorial-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="tutorial-title"
        aria-describedby="tutorial-description"
        tabIndex={-1}
      >
        <div className="tutorial-meta">
          <span className="eyebrow">
            BEGINNER TUTORIAL · {step + 1} / {tutorialSteps.length}
          </span>
          <button className="text-button" onClick={exit}>
            Exit tutorial
          </button>
        </div>
        <progress
          aria-label="Tutorial progress"
          value={step + 1}
          max={tutorialSteps.length}
        />
        <h2 id="tutorial-title">{item.title}</h2>
        <div id="tutorial-description">
          <p className="tutorial-goal">{item.goal}</p>
          <p>{item.explanation}</p>
          <p className="tutorial-takeaway">{item.takeaway}</p>
        </div>
        <div className="tutorial-controls">
          <span className="tutorial-status" role="status" aria-live="polite">
            {phase}
          </span>
          <div className="actions">
            <button
              className="button subtle"
              onClick={() => move(step)}
              disabled={moving && !failed}
            >
              Replay step
            </button>
            <button
              className="button"
              onClick={() => move(step - 1)}
              disabled={step === 0}
            >
              Back
            </button>
            <button
              className="button primary"
              disabled={moving || failed}
              onClick={() =>
                step === tutorialSteps.length - 1 ? exit() : move(step + 1)
              }
            >
              {step === tutorialSteps.length - 1 ? "Finish tutorial" : "Next"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

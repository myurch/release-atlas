import React, {
  useEffect,
  useLayoutEffect,
  useId,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { help, helpLabels } from "./help-content";
import { HelpRect, placeHelp } from "./help-layout";

export function HelpHint({ topic, label }: { topic: string; label?: string }) {
  return (
    <button
      type="button"
      className="help-hint"
      data-help={topic}
      data-help-trigger="true"
      aria-label={"About " + (label || help[topic]?.title || topic)}
    >
      ?
    </button>
  );
}
function topicFor(target: HTMLElement): string | undefined {
  if (target.dataset.help) return target.dataset.help;
  const fieldLabel = (target as HTMLInputElement).labels?.[0]?.cloneNode(
    true,
  ) as HTMLElement | undefined;
  fieldLabel
    ?.querySelectorAll("input,textarea,select,button")
    .forEach((child) => child.remove());
  const label =
    target.getAttribute("aria-label") ||
    fieldLabel?.textContent ||
    target.textContent ||
    "";
  const clean = label.replace(/[↗→]/g, "").replace(/\s+/g, " ").trim();
  if (helpLabels[clean]) return helpLabels[clean];
  if (target.matches(".citation")) return "citation";
  if (target.matches(".source-link,.source-item")) return "Sources";
  if (target.matches(".evidence-card,.attention-row")) return "Evidence";
  if (target.matches(".topic")) return "topics";
  if (target.matches(".graph-row")) return "graphNode";
  if (target.matches(".workspace-choice")) return "workspaces";
  return undefined;
}
export function ContextHelp({ enabled = true }: { enabled?: boolean }) {
  const id = useId();
  const popup = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<{
    key: string;
    x: number;
    y: number;
    anchor: HelpRect;
    group: HelpRect;
  } | null>(null);
  useLayoutEffect(() => {
    if (!tip || !popup.current) return;
    const rect = popup.current.getBoundingClientRect();
    const position = placeHelp(
      tip.anchor,
      tip.group,
      rect.width,
      rect.height,
      innerWidth,
      innerHeight,
    );
    if (
      Math.abs(position.x - tip.x) > 0.5 ||
      Math.abs(position.y - tip.y) > 0.5
    )
      setTip({ ...tip, ...position });
  }, [tip]);
  useEffect(() => {
    if (!enabled) {
      setTip(null);
      return;
    }
    let timer: ReturnType<typeof setTimeout>;
    let active: HTMLElement | null = null;
    let previous = "";
    const close = () => {
      clearTimeout(timer);
      if (active) {
        if (previous) active.setAttribute("aria-describedby", previous);
        else active.removeAttribute("aria-describedby");
      }
      active = null;
      setTip(null);
    };
    const show = (target: HTMLElement, key: string) => {
      close();
      if (
        !help[key] ||
        !target.isConnected ||
        target.closest("[inert],[hidden]")
      )
        return;
      const r = target.getBoundingClientRect();
      active = target;
      previous = target.getAttribute("aria-describedby") || "";
      target.setAttribute(
        "aria-describedby",
        [previous, id].filter(Boolean).join(" "),
      );
      const form = target.matches("input,textarea,select")
        ? target.closest("form")
        : null;
      const group = form?.getBoundingClientRect() || r;
      setTip({
        key,
        anchor: { left: r.left, right: r.right, top: r.top, bottom: r.bottom },
        group: {
          left: group.left,
          right: group.right,
          top: group.top,
          bottom: group.bottom,
        },
        x: r.left,
        y: r.bottom + 12,
      });
    };
    const enter = (event: Event) => {
      if (
        !(event.target instanceof Element) ||
        popup.current?.contains(event.target)
      )
        return;
      const target = event.target.closest<HTMLElement>(
        "[data-help],button,a,input,textarea,select,summary",
      );
      if (!target || target === active || target.closest("[data-no-help]"))
        return;
      const key = topicFor(target);
      close();
      if (key)
        timer = setTimeout(
          () => show(target, key),
          event.type === "focusin" ? 180 : 550,
        );
    };
    const leave = (event: Event) => {
      const related = (event as PointerEvent).relatedTarget as Node | null;
      if (
        related &&
        (popup.current?.contains(related) || active?.contains(related))
      )
        return;
      clearTimeout(timer);
      timer = setTimeout(close, 180);
    };
    const click = (event: MouseEvent) => {
      const target = (event.target as Element).closest<HTMLElement>(
        "[data-help-trigger]",
      );
      if (target) {
        if (active === target) close();
        else show(target, target.dataset.help!);
      } else if (!popup.current?.contains(event.target as Node)) close();
    };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape" && active) {
        event.stopImmediatePropagation();
        close();
      }
    };
    const stay = (event: PointerEvent) => {
      if (popup.current?.contains(event.target as Node)) clearTimeout(timer);
    };
    document.addEventListener("pointerover", enter);
    document.addEventListener("pointerover", stay);
    document.addEventListener("focusin", enter);
    document.addEventListener("pointerout", leave);
    document.addEventListener("focusout", leave);
    document.addEventListener("click", click);
    document.addEventListener("input", close);
    document.addEventListener("keydown", key, true);
    const scroll = (e: Event) => {
      if (!popup.current?.contains(e.target as Node)) close();
    };
    window.addEventListener("scroll", scroll, true);
    window.addEventListener("resize", close);
    return () => {
      close();
      document.removeEventListener("pointerover", enter);
      document.removeEventListener("pointerover", stay);
      document.removeEventListener("focusin", enter);
      document.removeEventListener("pointerout", leave);
      document.removeEventListener("focusout", leave);
      document.removeEventListener("click", click);
      document.removeEventListener("input", close);
      document.removeEventListener("keydown", key, true);
      window.removeEventListener("scroll", scroll, true);
      window.removeEventListener("resize", close);
    };
  }, [enabled, id]);
  if (!tip) return null;
  const content = help[tip.key];
  return createPortal(
    <div
      id={id}
      role="tooltip"
      ref={popup}
      className="context-tooltip"
      style={{
        left: tip.x,
        top: tip.y,
      }}
    >
      <strong>{content.title}</strong>
      <p>{content.what}</p>
      <div>
        <span>WHY IT MATTERS</span>
        <p>{content.why}</p>
      </div>
    </div>,
    document.body,
  );
}

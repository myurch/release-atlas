export type HelpRect = {
  left: number;
  right: number;
  top: number;
  bottom: number;
};
export function placeHelp(
  anchor: HelpRect,
  group: HelpRect,
  width: number,
  height: number,
  viewportWidth: number,
  viewportHeight: number,
) {
  const gap = 12;
  let x: number, y: number;
  // Keep form help beside the whole form, away from its next input or submit action.
  if (group.right + gap + width <= viewportWidth - gap) {
    x = group.right + gap;
    y = anchor.top;
  } else if (group.left - gap - width >= gap) {
    x = group.left - gap - width;
    y = anchor.top;
  } else {
    x = (anchor.left + anchor.right - width) / 2;
    y =
      anchor.top - gap - height >= gap
        ? anchor.top - gap - height
        : anchor.bottom + gap;
  }
  return {
    x: Math.max(gap, Math.min(x, viewportWidth - width - gap)),
    y: Math.max(gap, Math.min(y, viewportHeight - height - gap)),
  };
}

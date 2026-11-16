// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";

/** Inspect the visible Fred tooltip, then leave the trigger so hints cannot leak between assertions. */
export function readTooltip(target: Element | null | undefined): string {
  if (!target) throw new Error("Tooltip trigger not found");
  if (target.hasAttribute("title")) throw new Error("Native title tooltip still present");
  act(() => target.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));
  const ids = (target.getAttribute("aria-describedby") ?? "").split(" ");
  const panel = ids.map((id) => document.getElementById(id)).find((node) => node?.getAttribute("role") === "tooltip");
  if (!panel) throw new Error("Fred tooltip did not open");
  const text = panel.textContent ?? "";
  act(() => target.dispatchEvent(new MouseEvent("mouseout", { bubbles: true, relatedTarget: document.body })));
  return text;
}

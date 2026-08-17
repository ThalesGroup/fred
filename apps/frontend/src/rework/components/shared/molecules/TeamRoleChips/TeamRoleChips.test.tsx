// @vitest-environment happy-dom
// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Coverage: the two things this component has to get right for a team admin
// who does not already know the role model — (a) a member holding no elevated
// role still reads as a Member rather than as three inactive pills, and (b)
// every badge, including the ones the actor may not administer, can explain
// itself on hover. Hover is driven via `mouseover` because React delegates
// onMouseEnter from that bubbling event (see Tooltip.test.tsx).

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { UserTeamRelation } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import TeamRoleChips from "./TeamRoleChips.tsx";

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

function renderChips(props: Partial<React.ComponentProps<typeof TeamRoleChips>> = {}) {
  const onToggle = props.onToggle ?? vi.fn();
  act(() => {
    root.render(<TeamRoleChips heldRoles={[]} onToggle={onToggle} {...props} />);
  });
  return onToggle;
}

function toggleFor(role: UserTeamRelation): HTMLButtonElement | undefined {
  return Array.from(container.querySelectorAll("button")).find((b) => b.textContent === `rework.teamRoles.${role}`);
}

// Matched on the CSS-module class, not on "a span whose text is Member": the
// Tooltip wrapper is itself a span with the same textContent and comes first in
// the DOM, so a text-only lookup silently returns the wrapper and every
// assertion below about the badge's own tag/attributes passes vacuously.
function baselineBadge(): HTMLElement {
  const el = Array.from(container.querySelectorAll("*")).find((e) =>
    /(^|\s|_)baselineChip/.test(e.className.toString()),
  );
  if (!el) throw new Error("baseline Member badge not found");
  return el as HTMLElement;
}

// Hovers, reads the portaled panel, then un-hovers. The un-hover matters:
// only one badge can be hovered at a time in the real UI, but nothing tears
// the portal down for us, so leaving it mounted would make the next `hover`
// in the same test read the *previous* badge's panel.
function hover(el: Element): string {
  act(() => {
    el.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
  });
  const text = document.querySelector('[role="tooltip"]')?.textContent ?? "";
  act(() => {
    el.dispatchEvent(new MouseEvent("mouseout", { bubbles: true, relatedTarget: document.body }));
  });
  return text;
}

describe("TeamRoleChips — the implicit Member baseline", () => {
  it("shows a Member badge even when the person holds no elevated role", () => {
    renderChips({ heldRoles: [] });

    expect(baselineBadge()).not.toBeNull();
    expect(toggleFor("team_admin")?.getAttribute("aria-pressed")).toBe("false");
    expect(toggleFor("team_editor")?.getAttribute("aria-pressed")).toBe("false");
    expect(toggleFor("team_analyst")?.getAttribute("aria-pressed")).toBe("false");
  });

  it("keeps showing the Member badge alongside an elevated role", () => {
    renderChips({ heldRoles: ["team_admin"] });

    expect(baselineBadge()).not.toBeNull();
    expect(toggleFor("team_admin")?.getAttribute("aria-pressed")).toBe("true");
  });

  // The API refuses to revoke a member's last relation, and `team_member` is
  // implied by every elevated role — so offering it as a toggle would promise
  // an action that cannot happen.
  it("renders the Member baseline as a non-button that cannot be toggled", () => {
    const onToggle = renderChips({ heldRoles: [] });

    const badge = baselineBadge();
    expect(badge.tagName).toBe("SPAN");
    expect(badge.getAttribute("aria-pressed")).toBeNull();

    act(() => {
      badge.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });
    expect(onToggle).not.toHaveBeenCalled();
  });
});

describe("TeamRoleChips — role descriptions", () => {
  it("describes each elevated role on hover", () => {
    renderChips({ heldRoles: [] });

    for (const role of ["team_admin", "team_editor", "team_analyst"] as UserTeamRelation[]) {
      const chip = toggleFor(role);
      expect(chip).toBeDefined();
      expect(hover(chip!)).toContain(`rework.teamRoles.descriptions.${role}`);
    }
  });

  it("describes the Member baseline on hover too", () => {
    renderChips({ heldRoles: [] });

    expect(hover(baselineBadge())).toContain("rework.teamRoles.descriptions.team_member");
  });

  it("adds a warning to the Analyst description, and only to that one", () => {
    renderChips({ heldRoles: [] });

    expect(hover(toggleFor("team_analyst")!)).toContain("rework.teamRoles.warnings.team_analyst");

    // Each negative is paired with a positive on the same panel: `hover()`
    // returns "" when no tooltip opened at all, which would let a broken
    // tooltip satisfy `not.toContain` and report this as "only Analyst warns".
    for (const role of ["team_admin", "team_editor"] as UserTeamRelation[]) {
      const panel = hover(toggleFor(role)!);
      expect(panel).toContain(`rework.teamRoles.descriptions.${role}`);
      expect(panel).not.toContain("rework.teamRoles.warnings");
    }
  });

  // A chip the actor cannot administer is marked `aria-disabled` rather than
  // `disabled`, precisely so it keeps explaining itself: a truly `disabled`
  // button leaves the tab order and fires no pointer events, which would deny
  // the description to the reader least able to act on the role.
  it("still explains a role the actor is not allowed to administer", () => {
    const onToggle = renderChips({ heldRoles: [], canAdminister: () => false });

    const chip = toggleFor("team_analyst")!;
    expect(chip.getAttribute("aria-disabled")).toBe("true");
    expect(chip.disabled).toBe(false);
    expect(hover(chip)).toContain("rework.teamRoles.descriptions.team_analyst");

    // Still inert — the guard lives in the click handler, not in the DOM.
    act(() => {
      chip.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });
    expect(onToggle).not.toHaveBeenCalled();
  });

  // The counterpart to the hover path: keyboard users reach the description by
  // tabbing, which only works because the chip stays focusable.
  it("explains a non-administrable role on keyboard focus as well", () => {
    renderChips({ heldRoles: [], canAdminister: () => false });

    const chip = toggleFor("team_analyst")!;
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
      chip.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    });
    expect(document.querySelector('[role="tooltip"]')?.textContent).toContain(
      "rework.teamRoles.descriptions.team_analyst",
    );
  });
});

describe("TeamRoleChips — toggling", () => {
  it("reports the role and its current held state to the caller", () => {
    const onToggle = renderChips({ heldRoles: ["team_editor"] });

    act(() => {
      toggleFor("team_editor")!.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });
    expect(onToggle).toHaveBeenCalledWith("team_editor", true);

    act(() => {
      toggleFor("team_admin")!.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });
    expect(onToggle).toHaveBeenCalledWith("team_admin", false);
  });
});

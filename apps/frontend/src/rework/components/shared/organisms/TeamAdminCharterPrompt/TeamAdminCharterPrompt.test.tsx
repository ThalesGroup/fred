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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TeamAdminCharterStatus } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  status: undefined as TeamAdminCharterStatus | undefined,
  accept: vi.fn(() => Promise.resolve()),
  endReached: undefined as (() => void) | undefined,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements.ts", () => ({
  useTeamAdminCharterStatusQuery: () => ({ data: h.status }),
  useAcceptTeamAdminCharterMutation: () => [h.accept, { isLoading: false }],
}));

vi.mock("@shared/molecules/TeamAdminCharterContent/TeamAdminCharterContent.tsx", () => ({
  default: ({ onEndReached }: { onEndReached: () => void }) => {
    h.endReached = onEndReached;
    return "charter";
  },
}));

import TeamAdminCharterPrompt from "./TeamAdminCharterPrompt.tsx";

let container: HTMLDivElement;
let root: Root;

function render() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<TeamAdminCharterPrompt />);
  });
}

function dialog(): Element | null {
  return document.body.querySelector('[role="dialog"]');
}

function button(label: string): HTMLButtonElement {
  const match = Array.from(document.body.querySelectorAll("button")).find((b) => b.textContent?.includes(label));
  if (!match) throw new Error(`No button labelled ${label}`);
  return match;
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  h.status = undefined;
  h.endReached = undefined;
  h.accept.mockClear();
});

describe("TeamAdminCharterPrompt", () => {
  it("asks a pending admin to accept once the end of the charter is reached", () => {
    h.status = { required: true, accepted_at: null };
    render();
    const accept = button("rework.teamAdminCharter.accept");

    expect(dialog()).not.toBeNull();
    expect(accept.disabled).toBe(true);

    act(() => h.endReached?.());
    expect(accept.disabled).toBe(false);

    act(() => accept.click());
    expect(h.accept).toHaveBeenCalledTimes(1);
  });

  it("closes on Later without recording anything", () => {
    h.status = { required: true, accepted_at: null };
    render();

    act(() => button("rework.teamAdminCharter.later").click());

    expect(dialog()).toBeNull();
    expect(h.accept).not.toHaveBeenCalled();
  });

  it("stays closed when nothing is pending", () => {
    h.status = { required: false, accepted_at: "2026-09-14T10:00:00Z" };
    render();

    expect(dialog()).toBeNull();
  });
});

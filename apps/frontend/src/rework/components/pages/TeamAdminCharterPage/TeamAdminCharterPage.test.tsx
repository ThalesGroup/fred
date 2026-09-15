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

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  accept: vi.fn(() => Promise.resolve()),
  endReached: undefined as (() => void) | undefined,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements.ts", () => ({
  useAcceptTeamAdminCharterMutation: () => [h.accept, { isLoading: false }],
}));

vi.mock("@shared/molecules/TeamAdminCharterContent/TeamAdminCharterContent.tsx", () => ({
  default: ({ onEndReached }: { onEndReached: () => void }) => {
    h.endReached = onEndReached;
    return "charter";
  },
}));

import TeamAdminCharterPage from "./TeamAdminCharterPage.tsx";

let container: HTMLDivElement;
let root: Root;

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  h.accept.mockClear();
  h.endReached = undefined;
});

describe("TeamAdminCharterPage", () => {
  it("accepts the charter once its end has been reached", () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(<TeamAdminCharterPage />);
    });
    const accept = container.querySelector("button") as HTMLButtonElement;

    expect(accept.disabled).toBe(true);
    act(() => h.endReached?.());
    expect(accept.disabled).toBe(false);

    act(() => accept.click());
    expect(h.accept).toHaveBeenCalledTimes(1);
  });
});

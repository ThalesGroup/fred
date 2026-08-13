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

// The notice is silent at rest and speaks only over the limit, so what matters
// is the *transition*, not any single snapshot: the polite live region has to
// already be in the accessibility tree when the message appears (an inserted
// live region is not announced), and it has to empty out again — with its id
// intact — when the draft comes back under the limit, so the field's
// `aria-describedby` never dangles. A static render cannot show any of that;
// these tests drive it through real mounts with `createRoot` + `act`, the
// repo's idiom (no @testing-library/react here).

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CharacterLimitNotice } from "./CharacterLimitNotice";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) =>
      values ? `${key}:${values.used ?? ""}:${values.limit ?? ""}` : key,
    i18n: { language: "en" },
  }),
}));

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function render(count: number | undefined, limit: number | undefined) {
  act(() => {
    root.render(<CharacterLimitNotice id="notice" count={count} limit={limit} />);
  });
}

function liveRegion(): HTMLElement | null {
  return container.querySelector("[aria-live]");
}

describe("CharacterLimitNotice", () => {
  it("stays mounted and silent while the value is within the limit", () => {
    render(5, 5);

    expect(container.querySelector("#notice")).not.toBeNull();
    expect(liveRegion()?.textContent).toBe("");
    expect(container.textContent).toBe("");
  });

  it("fills the already-mounted live region when the value crosses the limit", () => {
    render(5, 5);
    const regionBefore = liveRegion();

    render(6, 5);

    // Same node, new text: the announcement the change relies on. A region
    // created together with its text is the pattern screen readers skip.
    expect(liveRegion()).toBe(regionBefore);
    expect(liveRegion()?.textContent).toBe("chatbot.errors.chatInputTooLong::5");
    expect(container.textContent).toContain("chatbot.characterCounter:6:5");
  });

  it("keeps the count out of the live region so typing does not re-announce", () => {
    render(6, 5);

    expect(liveRegion()?.textContent).not.toContain("chatbot.characterCounter");
  });

  it("empties without unmounting when the value comes back under the limit", () => {
    render(6, 5);

    render(5, 5);

    expect(container.querySelector("#notice")).not.toBeNull();
    expect(container.textContent).toBe("");
  });

  it("renders nothing when the runtime publishes no limit", () => {
    render(6, undefined);

    expect(container.innerHTML).toBe("");
  });
});

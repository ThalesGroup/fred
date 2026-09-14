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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

type Entries = Array<{ isIntersecting: boolean }>;

const h = vi.hoisted(() => ({
  markdown: "# Charter",
  notify: undefined as ((entries: Entries) => void) | undefined,
  observed: 0,
}));

vi.mock("@hooks/useLegalMarkdown.ts", () => ({ useLegalMarkdown: () => h.markdown }));
vi.mock("@shared/molecules/MarkdownRenderer/MarkdownRenderer", () => ({
  MarkdownRenderer: ({ text }: { text: string }) => <div>{text}</div>,
}));

import TeamAdminCharterContent from "./TeamAdminCharterContent.tsx";

class FakeIntersectionObserver {
  constructor(callback: (entries: Entries) => void) {
    h.notify = callback;
  }
  observe() {
    h.observed += 1;
  }
  disconnect() {}
  unobserve() {}
}

let container: HTMLDivElement;
let root: Root;

function render(onEndReached: () => void) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<TeamAdminCharterContent onEndReached={onEndReached} />);
  });
}

beforeEach(() => {
  vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  vi.unstubAllGlobals();
  h.markdown = "# Charter";
  h.notify = undefined;
  h.observed = 0;
});

describe("TeamAdminCharterContent", () => {
  it("reports the end of the charter once it becomes visible", () => {
    const onEndReached = vi.fn();
    render(onEndReached);

    act(() => h.notify?.([{ isIntersecting: false }]));
    expect(onEndReached).not.toHaveBeenCalled();

    act(() => h.notify?.([{ isIntersecting: true }]));
    expect(onEndReached).toHaveBeenCalledTimes(1);
  });

  it("waits for the charter text before watching its end", () => {
    h.markdown = "";
    render(vi.fn());

    expect(h.observed).toBe(0);
  });
});

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
import { TokenUsageBadge } from "./TokenUsageBadge.tsx";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
  }),
}));

let container: HTMLDivElement;
let root: Root;

function render(ui: React.ReactElement) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(ui);
  });
}

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

describe("TokenUsageBadge — CACHE-01", () => {
  it("shows the cache segment when cache_read_tokens is present and > 0", () => {
    render(
      <TokenUsageBadge
        usage={{ input_tokens: 1000, output_tokens: 200, total_tokens: 1200, cache_read_tokens: 800 }}
      />,
    );

    expect(container.textContent).toContain("⚡800");
  });

  it("omits the cache segment when cache_read_tokens is 0", () => {
    render(<TokenUsageBadge usage={{ input_tokens: 50, output_tokens: 10, total_tokens: 60, cache_read_tokens: 0 }} />);

    expect(container.textContent).not.toContain("⚡");
  });

  it("omits the cache segment when cache_read_tokens is undefined (provider doesn't report it)", () => {
    render(<TokenUsageBadge usage={{ input_tokens: 50, output_tokens: 10, total_tokens: 60 }} />);

    expect(container.textContent).not.toContain("⚡");
  });
});

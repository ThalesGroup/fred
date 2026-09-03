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

let mockLanguage = "en";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
    i18n: {
      get language() {
        return mockLanguage;
      },
    },
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
  mockLanguage = "en";
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

// #2403: the arrows must group against the UI language, not the browser's.
// A bare `toLocaleString()` disagreed with the header — which goes through
// i18next's `{{count, number}}` — for anyone whose browser language differed
// from their Fred language ("↑19,424" under "Total : 20 007 tokens").
describe("TokenUsageBadge — thousands grouping follows the UI language", () => {
  it("groups the arrows with the active i18n language, not the browser's", () => {
    mockLanguage = "fr";
    render(<TokenUsageBadge usage={{ input_tokens: 19424, output_tokens: 632, total_tokens: 20056 }} />);

    // French groups with U+202F (narrow no-break space), never a comma.
    expect(container.textContent).toContain(`↑${(19424).toLocaleString("fr")}`);
    expect(container.textContent).not.toContain("19,424");
  });

  it("groups them with the English separator when the UI is English", () => {
    mockLanguage = "en";
    render(<TokenUsageBadge usage={{ input_tokens: 19424, output_tokens: 632, total_tokens: 20056 }} />);

    expect(container.textContent).toContain("↑19,424");
  });

  it("shows in and out only — the total belongs to the header", () => {
    render(<TokenUsageBadge usage={{ input_tokens: 2709, output_tokens: 427, total_tokens: 3136 }} />);

    expect(container.textContent).toBe("↑2,709·↓427");
    expect(container.textContent).not.toContain("3,136");
  });
});

// The arrows are the only label the figures get, and ↑/↓ alone is ambiguous
// about which way the tokens travelled — each carries the spelled-out count.
describe("TokenUsageBadge — arrows name their direction on hover", () => {
  it("titles the up arrow as tokens sent and the down arrow as tokens received", () => {
    render(<TokenUsageBadge usage={{ input_tokens: 2709, output_tokens: 427, total_tokens: 3136 }} />);

    const titles = [...container.querySelectorAll("[title]")].map((el) => el.getAttribute("title"));
    expect(titles).toContain('chatbot.conversationTokenUsage.sent {"count":2709}');
    expect(titles).toContain('chatbot.conversationTokenUsage.received {"count":427}');
  });
});

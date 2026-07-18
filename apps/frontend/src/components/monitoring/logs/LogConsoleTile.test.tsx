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

// Regression coverage for issue #2009: LogConsoleTile must render explicit
// loading/error/empty states (previously only "empty" was handled — loading
// and error were silently blank), and the category filter (closed field,
// replacing the dead "agentic" service toggle) must reach the query body.

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

const postQuery = vi.fn(() => ({ catch: () => {} }));
let mockQueryState: {
  data?: { events: unknown[] };
  isLoading: boolean;
  isError: boolean;
} = { data: { events: [] }, isLoading: false, isError: false };

vi.mock("../../../slices/knowledgeFlow/knowledgeFlowOpenApi", () => ({
  useQueryLogsKnowledgeFlowV1LogsQueryPostMutation: () => [postQuery, mockQueryState],
}));

import { LogConsoleTile } from "./LogConsoleTile";

function render(): string {
  return renderToStaticMarkup(
    <LogConsoleTile start={new Date("2026-01-01T00:00:00Z")} end={new Date("2026-01-01T01:00:00Z")} />,
  );
}

describe("LogConsoleTile states", () => {
  it("renders the loading state", () => {
    mockQueryState = { data: undefined, isLoading: true, isError: false };
    expect(render()).toContain("logs.loading");
  });

  it("renders the error state", () => {
    mockQueryState = { data: undefined, isLoading: false, isError: true };
    expect(render()).toContain("logs.error");
  });

  it("renders the empty state when the query succeeds with no events", () => {
    mockQueryState = { data: { events: [] }, isLoading: false, isError: false };
    expect(render()).toContain("logs.empty");
  });

  it("renders log rows when events are present", () => {
    mockQueryState = {
      data: {
        events: [
          {
            ts: 1700000000,
            level: "INFO",
            logger: "app",
            file: "a.py",
            line: 1,
            msg: "hello",
            category: "application",
          },
        ],
      },
      isLoading: false,
      isError: false,
    };
    const html = render();
    expect(html).not.toContain("logs.empty");
    expect(html).toContain("hello");
  });

  it("does not offer the dead agentic service option", () => {
    mockQueryState = { data: { events: [] }, isLoading: false, isError: false };
    const html = render();
    expect(html).not.toContain("Agentic");
  });
});

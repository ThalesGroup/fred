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

// The forget approval card names the note, looked up by the id the gate holds.

import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, options?: { content?: string }) => `${key}:${options?.content ?? ""}` }),
}));
vi.mock("./useChatAgentScope", () => ({ useChatAgentScope: () => ({ spaceId: "space", agentInstanceId: "agent" }) }));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useAgentMemoryQuery: () => ({ currentData: { notes: [{ note_id: "n-1", content: "Reports in English" }] } }),
}));

const { MemoryForgetReview } = await import("./MemoryForgetReview");

const render = (preview: string) =>
  renderToStaticMarkup(<MemoryForgetReview call={{ args_preview: preview } as never} />);

it("shows the note the agent wants to forget", () => {
  expect(render('{"note_id": "n-1"}')).toContain("capability.memory.approval.forget:Reports in English");
});

it("shows nothing for an unknown note or unreadable arguments", () => {
  expect(render('{"note_id": "n-9"}')).toBe("");
  expect(render("not json")).toBe("");
});

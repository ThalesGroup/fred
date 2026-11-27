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

// The chat card undoes a remembered note with the person's own call, and says
// when a note is already gone.

import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { MemoryNotePartData } from "./types";

const state = vi.hoisted(() => ({
  notes: [] as { note_id: string; forgotten_at: string | null }[],
  forget: vi.fn(),
  edit: vi.fn(),
  showError: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, options?: { content?: string }) => `${key}${options?.content ?? ""}` }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: state.showError }) }));
vi.mock("./useChatAgentScope", () => ({ useChatAgentScope: () => ({ spaceId: "space", agentInstanceId: "agent" }) }));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useAgentMemoryQuery: () => ({ currentData: { notes: state.notes } }),
  useForgetAgentMemoryNoteMutation: () => [state.forget, { isLoading: false }],
  useEditAgentMemoryNoteMutation: () => [state.edit, { isLoading: false }],
}));

const { MemoryNoteCard } = await import("./MemoryNoteCard");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: ReturnType<typeof createRoot>;

const part = (action: MemoryNotePartData["action"], previous_content?: string): MemoryNotePartData => ({
  type: "memory_note",
  note_id: "n-1",
  content: "short format",
  action,
  previous_content,
});

const render = (note: MemoryNotePartData) =>
  act(() => root.render(<MemoryNoteCard part={note as unknown as Parameters<typeof MemoryNoteCard>[0]["part"]} />));

beforeEach(() => {
  container = document.createElement("div");
  root = createRoot(container);
  state.notes = [];
  state.forget.mockReset();
  state.edit.mockReset();
  state.showError.mockReset();
});
afterEach(() => act(() => root.unmount()));

it("undoes a remembered note, then says it is removed and focuses that status", async () => {
  state.forget.mockReturnValue({ unwrap: () => Promise.resolve() });
  document.body.appendChild(container);
  render(part("remembered"));
  expect(container.textContent).toContain("capability.memory.card.rememberedshort format");
  const undo = container.querySelector("button")!;
  await act(async () => undo.click());
  expect(state.forget).toHaveBeenCalledWith({ spaceId: "space", agentInstanceId: "agent", noteId: "n-1" });
  expect(container.textContent).toContain("capability.memory.card.removed");
  expect(container.querySelector("button")).toBeNull();
  expect(document.activeElement).toBe(container.querySelector('[role="status"]'));
  container.remove();
});

it("keeps the undo offered and reports a failed undo", async () => {
  state.forget.mockReturnValue({ unwrap: () => Promise.reject(new Error("403")) });
  render(part("remembered"));
  await act(async () => container.querySelector("button")!.click());
  expect(state.showError).toHaveBeenCalledWith({ summary: "capability.memory.card.undoFailed" });
  expect(container.querySelector("button")).not.toBeNull();
});

it("offers no undo for a note already removed elsewhere", () => {
  state.notes = [{ note_id: "n-1", forgotten_at: "2026-11-26T10:00:00Z" }];
  render(part("remembered"));
  expect(container.textContent).toContain("capability.memory.card.removed");
  expect(container.querySelector("button")).toBeNull();
});

it("shows a forgotten note without any action", () => {
  render(part("forgotten"));
  expect(container.textContent).toContain("capability.memory.card.forgottenshort format");
  expect(container.querySelector("button")).toBeNull();
});

it("puts an edited note back to its previous text, then says the change is undone", async () => {
  state.edit.mockReturnValue({ unwrap: () => Promise.resolve() });
  render(part("edited", "long format"));
  expect(container.textContent).toContain("capability.memory.card.editedshort format");
  await act(async () => container.querySelector("button")!.click());
  expect(state.edit).toHaveBeenCalledWith({
    spaceId: "space",
    agentInstanceId: "agent",
    noteId: "n-1",
    rememberAgentMemoryNoteRequest: { content: "long format" },
  });
  expect(state.forget).not.toHaveBeenCalled();
  expect(container.textContent).toContain("capability.memory.card.editUndone");
  expect(container.querySelector("button")).toBeNull();
});

it("reports a failed edit undo and keeps it offered", async () => {
  state.edit.mockReturnValue({ unwrap: () => Promise.reject(new Error("409")) });
  render(part("edited", "long format"));
  await act(async () => container.querySelector("button")!.click());
  expect(state.showError).toHaveBeenCalledWith({ summary: "capability.memory.card.editUndoFailed" });
  expect(container.querySelector("button")).not.toBeNull();
});

it("offers no undo for an edited note that is no longer active", () => {
  state.notes = [{ note_id: "n-1", forgotten_at: "2026-11-26T10:00:00Z" }];
  render(part("edited", "long format"));
  expect(container.textContent).toContain("capability.memory.card.editedshort format");
  expect(container.querySelector("button")).toBeNull();
});

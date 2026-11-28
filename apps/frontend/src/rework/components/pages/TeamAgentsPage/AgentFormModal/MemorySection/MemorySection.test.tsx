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

// Editors see the active notes and their history, remove, add and edit notes live.

import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const note = (
  id: string,
  content: string,
  forgottenAt: string | null = null,
  revision: { revises?: string; originAt?: string } = {},
) => ({
  note_id: id,
  content,
  created_by: "u-1",
  created_by_name: "Alice",
  created_session_id: null,
  created_at: "2026-11-20T10:00:00Z",
  revises_note_id: revision.revises ?? null,
  origin_created_at: revision.originAt ?? "2026-11-20T10:00:00Z",
  forgotten_by: forgottenAt ? "u-2" : null,
  forgotten_by_name: forgottenAt ? "Bob" : null,
  forgotten_at: forgottenAt,
});

const state = vi.hoisted(() => ({
  notes: [] as unknown[],
  remember: vi.fn(),
  forget: vi.fn(),
  edit: vi.fn(),
  showError: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, options?: { user?: string }) => `${key}${options?.user ?? ""}` }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: state.showError }) }));
vi.mock("../../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useAgentMemoryQuery: () => ({ currentData: { notes: state.notes }, isLoading: false, isError: false }),
  useRememberAgentMemoryNoteMutation: () => [state.remember, { isLoading: false }],
  useForgetAgentMemoryNoteMutation: () => [state.forget, { isLoading: false }],
  useEditAgentMemoryNoteMutation: () => [state.edit, { isLoading: false }],
}));

const { MemorySection } = await import("./MemorySection");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: ReturnType<typeof createRoot>;

const render = () => act(() => root.render(<MemorySection spaceId="space" agentInstanceId="agent" />));
const buttonNamed = (name: string) =>
  [...container.querySelectorAll("button")].find(
    (button) => button.getAttribute("aria-label") === name || button.textContent?.includes(name),
  )!;
const type = (value: string) =>
  act(() => {
    const field = container.querySelector("textarea")!;
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(field, value);
    field.dispatchEvent(new Event("input", { bubbles: true }));
  });

beforeEach(() => {
  container = document.createElement("div");
  root = createRoot(container);
  state.notes = [];
  for (const mock of [state.remember, state.forget, state.edit, state.showError]) mock.mockReset();
});
afterEach(() => act(() => root.unmount()));

it("says the memory is empty in plain words", () => {
  render();
  expect(container.textContent).toContain("capability.memory.manage.empty");
});

it("lists active notes, removes one, and keeps removed notes in the history", async () => {
  state.notes = [note("n-1", "short format"), note("n-2", "old choice", "2026-11-21T10:00:00Z")];
  state.forget.mockReturnValue({ unwrap: () => Promise.resolve() });
  render();
  const list = container.querySelector("ul")!;
  expect(list.textContent).toContain("short format");
  expect(list.textContent).toContain("capability.memory.manage.addedByAlice");
  expect(list.textContent).not.toContain("old choice");

  await act(async () => buttonNamed("capability.memory.manage.remove").click());
  expect(state.forget).toHaveBeenCalledWith({ spaceId: "space", agentInstanceId: "agent", noteId: "n-1" });

  await act(async () => buttonNamed("capability.memory.manage.history").click());
  expect(container.textContent).toContain("old choice");
  expect(container.textContent).toContain("capability.memory.manage.removedByBob");
});

it("adds a trimmed note and reports a full memory", async () => {
  state.remember.mockReturnValueOnce({ unwrap: () => Promise.resolve() });
  render();
  type("  weekly report on Monday  ");
  await act(async () => buttonNamed("capability.memory.manage.add").click());
  expect(state.remember).toHaveBeenCalledWith({
    spaceId: "space",
    agentInstanceId: "agent",
    rememberAgentMemoryNoteRequest: { content: "weekly report on Monday" },
  });

  state.remember.mockReturnValueOnce({ unwrap: () => Promise.reject({ status: 409, data: { code: "memory_full" } }) });
  type("one more");
  await act(async () => buttonNamed("capability.memory.manage.add").click());
  expect(state.showError).toHaveBeenCalledWith({ summary: "capability.memory.manage.full" });
});

it("edits a note in one call and keeps the server order", async () => {
  state.notes = [
    note("n-3", "short format, revised", null, { revises: "n-2", originAt: "2026-11-19T10:00:00Z" }),
    note("n-1", "TSN means networking"),
  ];
  state.edit.mockReturnValue({ unwrap: () => Promise.resolve(state.notes[0]) });
  document.body.appendChild(container);
  render();
  const items = [...container.querySelectorAll("ul li")].map((item) => item.textContent);
  expect(items[0]).toContain("short format, revised");
  expect(items[0]).toContain("capability.memory.manage.editedByAlice");
  expect(items[1]).toContain("capability.memory.manage.addedByAlice");

  await act(async () => buttonNamed("capability.memory.manage.edit").click());
  const field = container.querySelector("li textarea") as HTMLTextAreaElement;
  expect(field.value).toBe("short format, revised");
  expect(document.activeElement).toBe(field);
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(field, " short answers ");
    field.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await act(async () => buttonNamed("capability.memory.manage.save").click());
  expect(state.edit).toHaveBeenCalledTimes(1);
  expect(state.edit).toHaveBeenCalledWith({
    spaceId: "space",
    agentInstanceId: "agent",
    noteId: "n-3",
    rememberAgentMemoryNoteRequest: { content: "short answers" },
  });
  expect(state.remember).not.toHaveBeenCalled();
  expect(state.forget).not.toHaveBeenCalled();
  expect(container.querySelector("li textarea")).toBeNull();
  expect(document.activeElement).toBe(noteButton("n-3", "edit"));
  container.remove();
});

const noteButton = (id: string, action: "edit" | "remove") =>
  container.querySelector<HTMLButtonElement>(`[data-note-id="${id}"][data-note-action="${action}"]`)!;

it("returns focus to the note's edit button on cancel, and locks the other edits meanwhile", async () => {
  state.notes = [note("n-1", "short format"), note("n-2", "TSN means networking")];
  document.body.appendChild(container);
  render();
  await act(async () => noteButton("n-1", "edit").click());
  expect(noteButton("n-2", "edit").disabled).toBe(true);
  expect(noteButton("n-2", "remove").disabled).toBe(false);

  await act(async () => buttonNamed("capability.memory.manage.cancel").click());
  expect(document.activeElement).toBe(noteButton("n-1", "edit"));
  expect(noteButton("n-2", "edit").disabled).toBe(false);
  container.remove();
});

it("moves focus to the next note after a removal, else to the new-note field", async () => {
  state.notes = [note("n-1", "short format"), note("n-2", "TSN means networking")];
  state.forget.mockReturnValue({ unwrap: () => Promise.resolve() });
  document.body.appendChild(container);
  render();
  await act(async () => noteButton("n-1", "remove").click());
  expect(document.activeElement).toBe(noteButton("n-2", "remove"));

  state.notes = [note("n-2", "TSN means networking")];
  render();
  await act(async () => noteButton("n-2", "remove").click());
  state.notes = [];
  render();
  expect(document.activeElement).toBe(container.querySelector("textarea"));
  container.remove();
});

it("says a note replaced by an edit was replaced, not removed", async () => {
  state.notes = [
    note("n-2", "short answers", null, { revises: "n-1" }),
    note("n-1", "short format", "2026-11-21T10:00:00Z"),
    note("n-0", "old choice", "2026-11-21T10:00:00Z"),
  ];
  render();
  await act(async () => buttonNamed("capability.memory.manage.history").click());
  const history = container.querySelector('ul[aria-label="capability.memory.manage.historyAria"]')!;
  const items = [...history.querySelectorAll("li")].map((item) => item.textContent);
  expect(items[0]).toContain("capability.memory.manage.replacedByBob");
  expect(items[1]).toContain("capability.memory.manage.removedByBob");
});

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

// One element with two widths. These pin that it is the same element either
// way — the collapsed rail and the open panel are one node, and the button that
// grows it is the button that shrinks it back, in the same place.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  importPanelOpenRequested,
  taskEventReceived,
  taskRegistered,
  taskSlice,
  uploadHandedOff,
  uploadStarted,
} from "../../../../features/tasks/taskSlice";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("@shared/molecules/TaskCard/TaskCard", () => ({
  TaskCard: ({
    task,
    trailingSlot,
  }: {
    task: { taskId: string; target?: { label?: string } | null };
    trailingSlot?: unknown;
  }) => (
    <div data-testid="task-card" data-trailing={trailingSlot ? "markers" : "time"}>
      {task.target?.label ?? task.taskId}
    </div>
  ),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: vi.fn() }) }));
vi.mock("../../../../features/tasks/useTaskAcknowledgement", () => ({
  useTaskAcknowledgement: () => ({ acknowledge: vi.fn(), isAcknowledging: () => false }),
}));

import { ImportPanel } from "./ImportPanel";

let container: HTMLDivElement;
let root: Root;
let store: ReturnType<typeof makeStore>;

const makeStore = () => configureStore({ reducer: { tasks: taskSlice.reducer } });

beforeEach(() => {
  store = makeStore();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(
      <Provider store={store}>
        <ImportPanel teamId="team-1" />
      </Provider>,
    );
  });
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

const panel = () => container.querySelector("aside")!;
const toggle = () => container.querySelector("button")!;
const click = (element: HTMLElement) =>
  act(() => {
    element.click();
  });

function importOf(taskId: string, label: string) {
  return taskRegistered({
    taskId,
    kind: "ingestion",
    target: { type: "document", id: `uid-${taskId}`, label },
    teamId: "team-1",
  });
}

/** The file names the panel is currently listing, in order. */
const cards = () => [...container.querySelectorAll("[data-testid=task-card]")].map((n) => n.textContent);

const settled = (taskId: string, state: "succeeded" | "failed") => ({
  kind: "ingestion" as const,
  task_id: taskId,
  state,
  seq: 1,
  timestamp: "2026-01-01T00:00:00Z",
  progress: state === "succeeded" ? 1 : null,
  step: state === "succeeded" ? "done" : null,
  error: state === "failed" ? "boom" : null,
  detail: null,
});

/** The trailing corner of each card: live markers, or the time it settled. */
const corners = () =>
  [...container.querySelectorAll("[data-testid='task-card']")].map((c) => c.getAttribute("data-trailing"));

describe("ImportPanel", () => {
  it("lets a finished import go once it has been seen finishing", async () => {
    vi.useFakeTimers();
    try {
      await act(async () => {
        store.dispatch(importOf("t1", "report.pdf"));
      });
      click(toggle());
      expect(cards()).toEqual(["report.pdf"]);

      await act(async () => {
        store.dispatch(taskEventReceived(settled("t1", "succeeded")));
      });
      // Not on the instant: a card that vanished the moment it succeeded would
      // never be seen saying so.
      expect(cards()).toEqual(["report.pdf"]);

      await act(async () => {
        vi.advanceTimersByTime(3000);
      });
      expect(cards()).toEqual([]);
      // Gone from this list only. The task keeps its own window in the store:
      // the documents table reads it to mark the row as just completed, and
      // the tray reads it to show the task at all.
      expect(store.getState().tasks.byId["t1"]?.state).toBe("succeeded");

      // And it stays gone without scheduling itself again. The task keeps
      // emitting nothing, but its neighbours do — every one of those events
      // re-runs the effect over a list this task is still in.
      await act(async () => {
        store.dispatch(taskEventReceived({ ...settled("t1", "succeeded"), seq: 2 }));
        store.dispatch(taskEventReceived({ ...settled("t1", "succeeded"), seq: 3 }));
      });
      expect(vi.getTimerCount()).toBe(0);
      expect(cards()).toEqual([]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps a failed import until someone deals with it", async () => {
    vi.useFakeTimers();
    try {
      await act(async () => {
        store.dispatch(importOf("t1", "report.pdf"));
      });
      click(toggle());
      await act(async () => {
        store.dispatch(taskEventReceived(settled("t1", "failed")));
      });
      await act(async () => {
        vi.advanceTimersByTime(30_000);
      });

      // Nothing about a failure settles itself: the cause and the retry are
      // the whole reason the panel is still open.
      expect(cards()).toEqual(["report.pdf"]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("hands the card's trailing corner to the markers, and takes it back once the file settles", () => {
    act(() => {
      store.dispatch(importOf("t1", "report.pdf"));
    });
    click(toggle());
    expect(corners()).toEqual(["markers"]);

    act(() => {
      store.dispatch(
        taskEventReceived({
          kind: "ingestion",
          task_id: "t1",
          state: "succeeded",
          seq: 1,
          timestamp: "2026-01-01T00:00:00Z",
          progress: 1,
          step: "done",
          error: null,
          detail: null,
        }),
      );
    });

    // Markers that have nothing left to follow would only repeat the badge;
    // what the user wants then is when it happened.
    expect(corners()).toEqual(["time"]);
  });

  it("is the same element collapsed and open", () => {
    const collapsed = panel();
    expect(collapsed.dataset.expanded).toBe("false");

    click(toggle());

    // Not a second node appearing beside the rail: the rail itself widened.
    expect(panel()).toBe(collapsed);
    expect(collapsed.dataset.expanded).toBe("true");
  });

  it("opens and closes from the one button", () => {
    const button = toggle();
    click(button);
    expect(panel().dataset.expanded).toBe("true");

    click(toggle());

    expect(panel().dataset.expanded).toBe("false");
    // Same button, still there, still the only one.
    expect(container.querySelectorAll("button")).toHaveLength(1);
  });

  it("keeps the toggle on the right edge, the edge that does not move", () => {
    // The panel widens leftwards from a fixed right edge, so a right-aligned
    // toggle sits in the same place in both forms. Its icon is what changes:
    // an arrow pointing back the way it folds once open.
    // The button itself is the head's last child — nothing wraps it, so there
    // is nothing between it and the edge it is pinned to.
    const head = container.querySelector("aside > div")!;
    expect(head.lastElementChild).toBe(toggle());
    expect(container.querySelector(".material-symbols-outlined")?.textContent).toBe("download");

    click(toggle());

    expect(head.lastElementChild).toBe(toggle());
    expect(container.querySelector(".material-symbols-outlined")?.textContent).toBe("keyboard_arrow_right");
  });

  it("can be dragged wider only once it is open", () => {
    const handle = () => container.querySelector('[role="separator"]');
    // A rail the width of its button has nothing to resize.
    expect(handle()).toBeNull();

    click(toggle());

    expect(handle()).not.toBeNull();
    expect(panel().style.getPropertyValue("--import-panel-width")).toBe("360px");
  });

  it("shows nothing but the button while collapsed", () => {
    act(() => {
      store.dispatch(importOf("task-1", "report.pdf"));
    });

    expect(container.textContent).not.toContain("report.pdf");

    click(toggle());

    expect(container.textContent).toContain("report.pdf");
  });

  it("lists the imports, and says so when there are none", () => {
    click(toggle());
    expect(container.textContent).toContain("rework.imports.panel.empty");

    act(() => {
      store.dispatch(importOf("task-1", "report.pdf"));
      store.dispatch(importOf("task-2", "notes.md"));
    });

    // In the order they were sent, so the list does not reshuffle as each
    // new file registers.
    expect([...container.querySelectorAll("[data-testid=task-card]")].map((n) => n.textContent)).toEqual([
      "report.pdf",
      "notes.md",
    ]);
  });

  it("leaves another team's imports out — this panel belongs to one team's page", () => {
    act(() => {
      store.dispatch(
        taskRegistered({
          taskId: "elsewhere",
          kind: "ingestion",
          target: { type: "document", id: "uid-elsewhere", label: "someone-elses.pdf" },
          teamId: "team-2",
        }),
      );
      store.dispatch(importOf("task-1", "report.pdf"));
    });
    click(toggle());

    expect(container.textContent).toContain("report.pdf");
    expect(container.textContent).not.toContain("someone-elses.pdf");
  });

  it("leaves chat attachments out — they belong to the conversation", () => {
    act(() => {
      store.dispatch(
        taskRegistered({
          taskId: "chat-attachment-1",
          kind: "ingestion",
          target: { type: "attachment", id: "a1", label: "pasted.png" },
          localOnly: true,
          teamId: "team-1",
        }),
      );
      store.dispatch(importOf("task-1", "report.pdf"));
    });
    click(toggle());

    expect(container.textContent).toContain("report.pdf");
    expect(container.textContent).not.toContain("pasted.png");
  });

  it("lists a file while its bytes are still going up", () => {
    click(toggle());

    act(() => {
      store.dispatch(uploadStarted({ localId: "local-1", filename: "report.pdf", teamId: "team-1" }));
    });

    // The transfer is most of the wait on a large import; a panel that only
    // learns of a file once it is over shows an empty list for that whole time.
    expect(container.textContent).toContain("report.pdf");
  });

  it("keeps a file in its place when it crosses over to its ingestion task", () => {
    click(toggle());
    act(() => {
      store.dispatch(uploadStarted({ localId: "local-1", filename: "report.pdf", teamId: "team-1" }));
      store.dispatch(uploadStarted({ localId: "local-2", filename: "notes.md", teamId: "team-1" }));
      store.dispatch(
        uploadHandedOff({ localId: "local-2", taskId: "task-2", documentUid: "doc-2", filename: "notes.md" }),
      );
    });

    // Still second: it was sent second, and the list must not reshuffle as
    // each file is accepted.
    expect([...container.querySelectorAll("[data-testid=task-card]")].map((n) => n.textContent)).toEqual([
      "report.pdf",
      "notes.md",
    ]);
  });

  it("still lists the import after leaving the page and coming back", () => {
    act(() => {
      store.dispatch(importOf("task-1", "report.pdf"));
    });

    act(() => {
      root.unmount();
    });
    root = createRoot(container);
    act(() => {
      root.render(
        <Provider store={store}>
          <ImportPanel teamId="team-1" />
        </Provider>,
      );
    });
    click(toggle());

    expect(container.textContent).toContain("report.pdf");
  });

  it("opens itself when an import hands off", () => {
    expect(panel().dataset.expanded).toBe("false");

    act(() => {
      store.dispatch(importPanelOpenRequested());
    });

    expect(panel().dataset.expanded).toBe("true");
  });

  it("reopens for a second import after the user closed it", () => {
    act(() => {
      store.dispatch(importPanelOpenRequested());
    });
    click(toggle());
    expect(panel().dataset.expanded).toBe("false");

    act(() => {
      store.dispatch(importPanelOpenRequested());
    });

    expect(panel().dataset.expanded).toBe("true");
  });

  it("does not reopen for an import already under way when the page mounts", () => {
    // Arriving on Resources with something importing should not take the page
    // over; the badge says it is there.
    act(() => {
      store.dispatch(importPanelOpenRequested());
    });
    click(toggle());

    // A real remount, as navigating back to the page would do.
    act(() => {
      root.unmount();
    });
    root = createRoot(container);
    act(() => {
      root.render(
        <Provider store={store}>
          <ImportPanel teamId="team-1" />
        </Provider>,
      );
    });

    expect(panel().dataset.expanded).toBe("false");
  });
});

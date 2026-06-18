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

import { describe, it, expect, vi, afterEach } from "vitest";
import {
  taskSlice,
  taskRegistered,
  taskEventReceived,
  taskEvicted,
  trayClockTicked,
  failuresAcknowledged,
  completedTasksCleared,
  selectActiveTasks,
  selectVisibleTasks,
  selectAllTasks,
  selectActiveCount,
  selectUnacknowledgedFailures,
  selectActiveTaskForTarget,
  EVICTION_DELAY_MS,
} from "./taskSlice";
import type { TasksState } from "./taskSlice";
import type { IngestionTaskEvent, TaskTarget, TaskViewModel } from "./taskTypes";

const { reducer } = taskSlice;

// ── Factories ─────────────────────────────────────────────────────────────────

function empty(): TasksState {
  return { byId: {} };
}

function root(s: TasksState) {
  return { tasks: s };
}

function target(overrides: Partial<TaskTarget> = {}): TaskTarget {
  return { type: "document", id: "doc-1", label: "report.pdf", ...overrides };
}

function vm(overrides: Partial<TaskViewModel> = {}): TaskViewModel {
  return {
    taskId: "t1",
    kind: "ingestion",
    target: target(),
    owner: null,
    localOnly: false,
    state: "running",
    progress: null,
    step: null,
    error: null,
    lastSeq: -1,
    registeredAt: 1000,
    terminalAt: null,
    acknowledgedAt: null,
    ...overrides,
  };
}

function ev(overrides: Partial<IngestionTaskEvent> = {}): IngestionTaskEvent {
  return {
    kind: "ingestion",
    task_id: "t1",
    state: "running",
    seq: 0,
    timestamp: "2026-01-01T00:00:00Z",
    progress: null,
    step: null,
    error: null,
    detail: null,
    ...overrides,
  };
}

afterEach(() => {
  vi.useRealTimers();
});

// ── taskRegistered ────────────────────────────────────────────────────────────

describe("taskRegistered", () => {
  it("inserts a new entry with pending state and lastSeq -1", () => {
    const s = reducer(empty(), taskRegistered({ taskId: "t1", kind: "ingestion", target: target() }));
    expect(s.byId["t1"].state).toBe("pending");
    expect(s.byId["t1"].lastSeq).toBe(-1);
    expect(s.byId["t1"].kind).toBe("ingestion");
  });

  it("stores target when provided", () => {
    const t = target({ id: "doc-42", label: "report.pdf" });
    const s = reducer(empty(), taskRegistered({ taskId: "t1", target: t }));
    expect(s.byId["t1"].target?.id).toBe("doc-42");
    expect(s.byId["t1"].target?.label).toBe("report.pdf");
  });

  it("stores localOnly when provided", () => {
    const s = reducer(empty(), taskRegistered({ taskId: "t1", localOnly: true }));
    expect(s.byId["t1"].localOnly).toBe(true);
  });

  it("stores null target when not provided", () => {
    const s = reducer(empty(), taskRegistered({ taskId: "t1" }));
    expect(s.byId["t1"].target).toBeNull();
  });

  it("is idempotent — second call with same taskId is a no-op", () => {
    const tgt = target({ label: "a.pdf" });
    let s = reducer(empty(), taskRegistered({ taskId: "t1", target: tgt }));
    s = reducer(s, taskRegistered({ taskId: "t1", target: target({ label: "other.pdf" }) }));
    expect(s.byId["t1"].target?.label).toBe("a.pdf");
  });

  it("inserts multiple tasks independently", () => {
    let s = reducer(empty(), taskRegistered({ taskId: "t1" }));
    s = reducer(s, taskRegistered({ taskId: "t2" }));
    expect(Object.keys(s.byId)).toHaveLength(2);
  });
});

// ── taskEventReceived ─────────────────────────────────────────────────────────

describe("taskEventReceived", () => {
  it("updates state, progress, step, error, and lastSeq", () => {
    const init = { byId: { t1: vm() } };
    const s = reducer(
      init,
      taskEventReceived(ev({ seq: 0, state: "running", progress: 0.5, step: "vectorising", error: null })),
    );
    expect(s.byId["t1"].state).toBe("running");
    expect(s.byId["t1"].progress).toBe(0.5);
    expect(s.byId["t1"].step).toBe("vectorising");
    expect(s.byId["t1"].lastSeq).toBe(0);
  });

  it("updates target when event provides one", () => {
    const init = { byId: { t1: vm({ target: null }) } };
    const newTarget: TaskTarget = { type: "document", id: "doc-99", label: "final.pdf" };
    const s = reducer(init, taskEventReceived(ev({ seq: 0, target: newTarget })));
    expect(s.byId["t1"].target?.id).toBe("doc-99");
  });

  it("ignores an event with seq equal to lastSeq (dedup)", () => {
    const init = { byId: { t1: vm({ lastSeq: 5, state: "running" }) } };
    const s = reducer(init, taskEventReceived(ev({ seq: 5, state: "succeeded" })));
    expect(s.byId["t1"].state).toBe("running");
  });

  it("ignores an event with seq less than lastSeq (out-of-order)", () => {
    const init = { byId: { t1: vm({ lastSeq: 10, state: "running" }) } };
    const s = reducer(init, taskEventReceived(ev({ seq: 3, state: "succeeded" })));
    expect(s.byId["t1"].state).toBe("running");
  });

  it("stamps terminalAt on first terminal event", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:05:00Z"));
    const init = { byId: { t1: vm({ lastSeq: -1 }) } };
    const s = reducer(init, taskEventReceived(ev({ seq: 0, state: "succeeded" })));
    expect(s.byId["t1"].terminalAt).toBe(new Date("2026-01-01T00:05:00Z").getTime());
  });

  it("does not overwrite an already-set terminalAt", () => {
    const init = { byId: { t1: vm({ lastSeq: 0, terminalAt: 999, state: "succeeded" }) } };
    const s = reducer(init, taskEventReceived(ev({ seq: 1, state: "failed" })));
    expect(s.byId["t1"].terminalAt).toBe(999);
  });

  it("is a no-op when task_id is unknown", () => {
    const init = { byId: { t1: vm() } };
    const s = reducer(init, taskEventReceived(ev({ task_id: "unknown" })));
    expect(s).toEqual(init);
  });
});

// ── taskEvicted ───────────────────────────────────────────────────────────────

describe("taskEvicted", () => {
  it("removes the entry", () => {
    const init = { byId: { t1: vm() } };
    const s = reducer(init, taskEvicted("t1"));
    expect(s.byId["t1"]).toBeUndefined();
  });

  it("is a no-op when task_id is unknown", () => {
    const init = { byId: { t1: vm() } };
    const s = reducer(init, taskEvicted("unknown"));
    expect(Object.keys(s.byId)).toHaveLength(1);
  });
});

// ── trayClockTicked ───────────────────────────────────────────────────────────

describe("trayClockTicked", () => {
  it("advances the tick counter without touching tasks", () => {
    const init = { byId: { t1: vm() }, tick: 0 };
    const s = reducer(init, trayClockTicked());
    expect(s.tick).toBe(1);
    expect(s.byId).toEqual(init.byId);
  });

  it("treats a missing tick as zero", () => {
    const s = reducer({ byId: {} }, trayClockTicked());
    expect(s.tick).toBe(1);
  });
});

// ── failuresAcknowledged ──────────────────────────────────────────────────────

describe("failuresAcknowledged", () => {
  it("stamps acknowledgedAt on failed tasks with null acknowledgedAt", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:10:00Z"));
    const init = { byId: { t1: vm({ state: "failed", acknowledgedAt: null }) } };
    const s = reducer(init, failuresAcknowledged());
    expect(s.byId["t1"].acknowledgedAt).toBe(new Date("2026-01-01T00:10:00Z").getTime());
  });

  it("stamps acknowledgedAt on cancelled tasks", () => {
    const init = { byId: { t1: vm({ state: "cancelled", acknowledgedAt: null }) } };
    const s = reducer(init, failuresAcknowledged());
    expect(s.byId["t1"].acknowledgedAt).not.toBeNull();
  });

  it("does not overwrite an already-set acknowledgedAt", () => {
    const init = { byId: { t1: vm({ state: "failed", acknowledgedAt: 42 }) } };
    const s = reducer(init, failuresAcknowledged());
    expect(s.byId["t1"].acknowledgedAt).toBe(42);
  });

  it("does not touch succeeded tasks", () => {
    const init = { byId: { t1: vm({ state: "succeeded", acknowledgedAt: null }) } };
    const s = reducer(init, failuresAcknowledged());
    expect(s.byId["t1"].acknowledgedAt).toBeNull();
  });
});

// ── selectActiveTasks / selectActiveCount ─────────────────────────────────────

describe("selectActiveTasks", () => {
  it("returns only non-terminal tasks", () => {
    const s = {
      byId: {
        t1: vm({ taskId: "t1", state: "running" }),
        t2: vm({ taskId: "t2", state: "succeeded" }),
        t3: vm({ taskId: "t3", state: "pending" }),
      },
    };
    const active = selectActiveTasks(root(s));
    expect(active.map((t) => t.taskId).sort()).toEqual(["t1", "t3"]);
  });
});

describe("selectActiveCount", () => {
  it("counts only non-terminal tasks", () => {
    const s = {
      byId: {
        t1: vm({ taskId: "t1", state: "running" }),
        t2: vm({ taskId: "t2", state: "failed" }),
      },
    };
    expect(selectActiveCount(root(s))).toBe(1);
  });

  it("returns 0 when all tasks are terminal", () => {
    const s = { byId: { t1: vm({ state: "succeeded" }) } };
    expect(selectActiveCount(root(s))).toBe(0);
  });
});

// ── selectUnacknowledgedFailures ──────────────────────────────────────────────

describe("selectUnacknowledgedFailures", () => {
  it("counts failed tasks with null acknowledgedAt", () => {
    const s = {
      byId: {
        t1: vm({ taskId: "t1", state: "failed", acknowledgedAt: null }),
        t2: vm({ taskId: "t2", state: "failed", acknowledgedAt: 1 }),
        t3: vm({ taskId: "t3", state: "cancelled", acknowledgedAt: null }),
      },
    };
    expect(selectUnacknowledgedFailures(root(s))).toBe(2);
  });

  it("returns 0 when all failures are acknowledged", () => {
    const s = { byId: { t1: vm({ state: "failed", acknowledgedAt: 1 }) } };
    expect(selectUnacknowledgedFailures(root(s))).toBe(0);
  });
});

// ── selectVisibleTasks ────────────────────────────────────────────────────────

describe("selectVisibleTasks", () => {
  it("includes active (non-terminal) tasks regardless of age", () => {
    vi.useFakeTimers();
    vi.setSystemTime(Date.now() + EVICTION_DELAY_MS * 10);
    const s = { byId: { t1: vm({ state: "running", terminalAt: null }) } };
    expect(selectVisibleTasks(root(s))).toHaveLength(1);
  });

  it("includes a succeeded task within the eviction window", () => {
    vi.useFakeTimers();
    const now = 1_000_000;
    vi.setSystemTime(now);
    const s = { byId: { t1: vm({ state: "succeeded", terminalAt: now - 1000 }) } };
    expect(selectVisibleTasks(root(s))).toHaveLength(1);
  });

  it("hides a succeeded task after the eviction window", () => {
    vi.useFakeTimers();
    const now = 1_000_000;
    vi.setSystemTime(now);
    const s = { byId: { t1: vm({ state: "succeeded", terminalAt: now - EVICTION_DELAY_MS - 1 }) } };
    expect(selectVisibleTasks(root(s))).toHaveLength(0);
  });

  it("keeps a failed task visible before acknowledgement", () => {
    vi.useFakeTimers();
    vi.setSystemTime(Date.now() + EVICTION_DELAY_MS * 10);
    const s = { byId: { t1: vm({ state: "failed", terminalAt: 1, acknowledgedAt: null }) } };
    expect(selectVisibleTasks(root(s))).toHaveLength(1);
  });

  it("hides a failed task after acknowledgedAt + eviction window", () => {
    vi.useFakeTimers();
    const now = 1_000_000;
    vi.setSystemTime(now);
    const s = {
      byId: { t1: vm({ state: "failed", terminalAt: 1, acknowledgedAt: now - EVICTION_DELAY_MS - 1 }) },
    };
    expect(selectVisibleTasks(root(s))).toHaveLength(0);
  });

  it("includes active tasks in the result", () => {
    vi.useFakeTimers();
    const now = 1_000_000;
    vi.setSystemTime(now);
    const s = { byId: { t1: vm({ state: "running", terminalAt: null }) } };
    expect(selectVisibleTasks(root(s))).toHaveLength(1);
  });

  it("sorts active tasks above terminal tasks", () => {
    vi.useFakeTimers();
    const now = 1_000_000;
    vi.setSystemTime(now);
    const s = {
      byId: {
        done: vm({ taskId: "done", state: "succeeded", terminalAt: now - 1000, registeredAt: 2000 }),
        active: vm({ taskId: "active", state: "running", terminalAt: null, registeredAt: 1000 }),
      },
    };
    const visible = selectVisibleTasks(root(s));
    expect(visible[0].taskId).toBe("active");
  });
});

// ── selectActiveTaskForTarget ─────────────────────────────────────────────────

describe("selectActiveTaskForTarget", () => {
  it("returns task matching type and id when not succeeded", () => {
    const s = {
      byId: {
        t1: vm({ taskId: "t1", target: target({ type: "document", id: "doc-1" }), state: "running" }),
      },
    };
    const found = selectActiveTaskForTarget("document", "doc-1")(root(s));
    expect(found?.taskId).toBe("t1");
  });

  it("returns undefined when state is succeeded", () => {
    const s = {
      byId: {
        t1: vm({ taskId: "t1", target: target({ type: "document", id: "doc-1" }), state: "succeeded" }),
      },
    };
    expect(selectActiveTaskForTarget("document", "doc-1")(root(s))).toBeUndefined();
  });

  it("returns task when state is failed (shown until evicted)", () => {
    const s = {
      byId: {
        t1: vm({ taskId: "t1", target: target({ type: "document", id: "doc-1" }), state: "failed" }),
      },
    };
    const found = selectActiveTaskForTarget("document", "doc-1")(root(s));
    expect(found?.taskId).toBe("t1");
  });

  it("returns undefined when type does not match", () => {
    const s = {
      byId: {
        t1: vm({ taskId: "t1", target: target({ type: "database", id: "db-1" }), state: "running" }),
      },
    };
    expect(selectActiveTaskForTarget("document", "db-1")(root(s))).toBeUndefined();
  });

  it("returns undefined when id does not match", () => {
    const s = {
      byId: {
        t1: vm({ taskId: "t1", target: target({ type: "document", id: "doc-1" }), state: "running" }),
      },
    };
    expect(selectActiveTaskForTarget("document", "doc-99")(root(s))).toBeUndefined();
  });

  it("returns undefined for tasks with null target", () => {
    const s = {
      byId: { t1: vm({ taskId: "t1", target: null, state: "running" }) },
    };
    expect(selectActiveTaskForTarget("document", "doc-1")(root(s))).toBeUndefined();
  });
});

// ── completedTasksCleared ─────────────────────────────────────────────────────

describe("completedTasksCleared", () => {
  it("removes every terminal task but keeps active ones", () => {
    const s: TasksState = {
      byId: {
        ok: vm({ taskId: "ok", state: "succeeded", terminalAt: 1 }),
        ko: vm({ taskId: "ko", state: "failed", terminalAt: 1 }),
        cx: vm({ taskId: "cx", state: "cancelled", terminalAt: 1 }),
        run: vm({ taskId: "run", state: "running", terminalAt: null }),
        pend: vm({ taskId: "pend", state: "pending", terminalAt: null }),
      },
    };
    const next = reducer(s, completedTasksCleared());
    expect(Object.keys(next.byId).sort()).toEqual(["pend", "run"]);
  });

  it("is a no-op when there are no terminal tasks", () => {
    const s: TasksState = { byId: { run: vm({ taskId: "run", state: "running" }) } };
    const next = reducer(s, completedTasksCleared());
    expect(Object.keys(next.byId)).toEqual(["run"]);
  });
});

// ── selectAllTasks ────────────────────────────────────────────────────────────

describe("selectAllTasks", () => {
  it("keeps terminal tasks regardless of age (no eviction window)", () => {
    vi.useFakeTimers();
    const now = 1_000_000;
    vi.setSystemTime(now);
    // Older than the tray eviction window — selectVisibleTasks would drop this,
    // but the admin history must retain it.
    const s = { byId: { old: vm({ taskId: "old", state: "succeeded", terminalAt: now - EVICTION_DELAY_MS - 1 }) } };
    expect(selectVisibleTasks(root(s))).toHaveLength(0);
    expect(selectAllTasks(root(s))).toHaveLength(1);
  });

  it("sorts active tasks above terminal tasks, then by recency", () => {
    const s = {
      byId: {
        done: vm({ taskId: "done", state: "succeeded", terminalAt: 5, registeredAt: 2000 }),
        active: vm({ taskId: "active", state: "running", terminalAt: null, registeredAt: 1000 }),
      },
    };
    expect(selectAllTasks(root(s))[0].taskId).toBe("active");
  });
});

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

// Following imports end to end, short of the network: the polling loop, the
// generated clients and their base query (token refresh, 401 retry), the task
// store, and the two places a user reads progress — the import panel and the
// document row. The server is a table of task states behind a fake fetch.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: vi.fn() }) }));
vi.mock("./useTaskAcknowledgement", () => ({
  useTaskAcknowledgement: () => ({ acknowledge: vi.fn(), isAcknowledging: () => false }),
}));
const ensureFreshToken = vi.fn(async (_minValidity: number) => true);
vi.mock("../../../security/KeycloakService", () => ({
  KeyCloakService: {
    ensureFreshToken: (minValidity: number) => ensureFreshToken(minValidity),
    GetToken: () => "token",
    CallLogout: vi.fn(),
  },
}));

import { knowledgeFlowApi } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { controlPlaneApi } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { taskRegistered, taskSlice, uploadHandedOff, uploadStarted } from "./taskSlice";
import { POLL_INTERVAL_MS, READ_TIMEOUT_MS, useTaskPolling } from "./useTaskPolling";
import { ImportPanel } from "@shared/organisms/ImportPanel/ImportPanel";
import { DocRow } from "@shared/molecules/DocRow/DocRow";

const makeStore = () =>
  configureStore({
    reducer: {
      tasks: taskSlice.reducer,
      [knowledgeFlowApi.reducerPath]: knowledgeFlowApi.reducer,
      [controlPlaneApi.reducerPath]: controlPlaneApi.reducer,
    },
    middleware: (getDefault) => getDefault().concat(knowledgeFlowApi.middleware, controlPlaneApi.middleware),
  });

// ── The fake server ─────────────────────────────────────────────────────────

type ServerState = "pending" | "running" | "succeeded" | "failed";
/** What the backends have recorded, keyed by task id; a missing id is unknown. */
let server: Map<string, { state: ServerState; error?: string; kind?: string }>;
/** Reads to leave unanswered, never resolving, before answering again. */
let hangs: number;
/** The path of every read, to tell which backend was asked. */
let readPaths: string[];
/** Answers to give before consulting `server`, one per read: a status code. */
let refusals: number[];
let reads: string[][];
let inFlight: number;
let maxInFlight: number;

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

async function fakeFetch(input: Request | string): Promise<Response> {
  const url = new URL(typeof input === "string" ? input : input.url, "http://localhost");
  if (url.pathname !== "/knowledge-flow/v1/tasks" && url.pathname !== "/control-plane/v1/tasks") {
    return json({ detail: "unexpected" }, 404);
  }
  readPaths.push(url.pathname);
  if (hangs > 0) {
    hangs -= 1;
    return new Promise<Response>(() => {});
  }
  const ids = url.searchParams.getAll("task_id");
  inFlight += 1;
  maxInFlight = Math.max(maxInFlight, inFlight);
  try {
    await Promise.resolve();
    const refusal = refusals.shift();
    if (refusal) return json({ detail: "refused" }, refusal);
    reads.push(ids);
    const tasks = ids
      .filter((id) => server.has(id))
      .map((id) => ({
        task_id: id,
        kind: server.get(id)!.kind ?? "ingestion",
        state: server.get(id)!.state,
        error: server.get(id)!.error ?? null,
        created_at: "2026-10-03T00:00:00Z",
        updated_at: "2026-10-03T00:00:00Z",
      }));
    return json({ tasks });
  } finally {
    inFlight -= 1;
  }
}

// ── The page ────────────────────────────────────────────────────────────────

let store: ReturnType<typeof makeStore>;
let container: HTMLDivElement;
let root: Root;

/** MainLayout stays mounted; the Resources page comes and goes. */
function Layout({ onResources, docs }: { onResources: boolean; docs: string[] }) {
  useTaskPolling();
  if (!onResources) return null;
  return (
    <>
      <ImportPanel teamId="team-1" />
      {docs.map((doc) => (
        // The document's own metadata says it is not processed yet.
        <DocRow key={doc} id={doc} name={`${doc}.pdf`} fileType="pdf" status="raw" />
      ))}
    </>
  );
}

function render(onResources: boolean, docs: string[] = []) {
  act(() => {
    root.render(
      <Provider store={store}>
        <Layout onResources={onResources} docs={docs} />
      </Provider>,
    );
  });
  if (onResources && !container.querySelector("aside[role=region]")) {
    act(() => {
      container.querySelector("aside button")!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
  }
}

const text = () => container.textContent ?? "";
const settle = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

/** A file handed to its ingestion task, as an import leaves it. */
function imported(n: number, state: ServerState = "pending"): string[] {
  const docs: string[] = [];
  for (let i = 0; i < n; i++) {
    const doc = `doc-${i}`;
    store.dispatch(uploadStarted({ localId: `local-${i}`, filename: `${doc}.pdf`, teamId: "team-1" }));
    store.dispatch(
      uploadHandedOff({ localId: `local-${i}`, taskId: `task-${i}`, documentUid: doc, filename: `${doc}.pdf` }),
    );
    server.set(`task-${i}`, { state });
    docs.push(doc);
  }
  return docs;
}

const taskState = (taskId: string) => store.getState().tasks.byId[taskId];

beforeEach(() => {
  vi.useFakeTimers();
  server = new Map();
  refusals = [];
  hangs = 0;
  readPaths = [];
  reads = [];
  inFlight = 0;
  maxInFlight = 0;
  ensureFreshToken.mockReset();
  ensureFreshToken.mockImplementation(async () => true);
  vi.stubGlobal("fetch", vi.fn(fakeFetch));
  store = makeStore();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

// ── Behaviour ───────────────────────────────────────────────────────────────

describe("following an import by polling", () => {
  it("brings every file to its recorded outcome, in one read per round", async () => {
    const docs = imported(13);
    render(true, docs);
    await settle(0);
    expect(text()).toContain("rework.imports.stepper.waiting");
    expect(text()).toContain("rework.resources.status.processing");

    for (const id of server.keys()) server.set(id, { state: "succeeded" });
    await settle(POLL_INTERVAL_MS);

    expect(reads).toHaveLength(2);
    expect(reads[0]).toHaveLength(13);
    expect(text()).not.toContain("rework.imports.stepper.waiting");
    expect(text()).not.toContain("rework.resources.status.processing");
  });

  it("reads more files than one batch holds in batches, one at a time", async () => {
    imported(60);
    render(false);
    await settle(0);

    expect(reads.map((ids) => ids.length)).toEqual([50, 10]);
    expect(maxInFlight).toBe(1);
  });

  it("recovers from an expired token with no reload", async () => {
    const docs = imported(1, "succeeded");
    refusals = [401];
    render(true, docs);
    await settle(0);

    expect(ensureFreshToken).toHaveBeenCalledWith(0);
    expect(taskState("task-0").state).toBe("succeeded");
    expect(text()).not.toContain("rework.resources.status.processing");
  });

  it("reaches the outcome while the user is on another page, and shows it on return", async () => {
    const docs = imported(1);
    render(true, docs);
    await settle(0);
    render(false);
    server.set("task-0", { state: "succeeded" });
    await settle(POLL_INTERVAL_MS);
    render(true, docs);

    expect(text()).not.toContain("rework.imports.stepper.waiting");
    expect(text()).not.toContain("rework.resources.status.processing");
  });

  it("shows a failure as a failure", async () => {
    const docs = imported(1);
    server.set("task-0", { state: "failed", error: "extraction failed" });
    render(true, docs);
    await settle(0);

    expect(taskState("task-0").state).toBe("failed");
    expect(text()).toContain("rework.resources.status.failed");
  });

  it("changes nothing on a failed read, then converges", async () => {
    imported(1, "running");
    refusals = [500];
    render(false);
    await settle(0);
    expect(taskState("task-0").state).toBe("pending");
    expect(taskState("task-0").untracked).toBe(false);

    server.set("task-0", { state: "succeeded" });
    await settle(POLL_INTERVAL_MS);
    expect(taskState("task-0").state).toBe("succeeded");
  });

  it("marks a task the server no longer knows as untracked, and stops reading it", async () => {
    const docs = imported(2);
    server.delete("task-1");
    render(true, docs);
    await settle(0);

    expect(taskState("task-1").untracked).toBe(true);
    expect(text()).toContain("rework.imports.untracked.summary");
    // The row falls back to the document's own status.
    expect(text()).toContain("rework.resources.status.raw");

    await settle(POLL_INTERVAL_MS);
    expect(reads[reads.length - 1]).toEqual(["task-0"]);
  });

  it("stops reading once nothing is left to follow, and starts again for a new task", async () => {
    imported(1, "succeeded");
    render(false);
    await settle(0);
    await settle(POLL_INTERVAL_MS * 5);
    expect(reads).toHaveLength(1);

    store.dispatch(taskRegistered({ taskId: "task-new", kind: "ingestion" }));
    server.set("task-new", { state: "running" });
    await settle(0);
    expect(reads[reads.length - 1]).toEqual(["task-new"]);
  });

  it("reads again right away when the tab comes back to the foreground", async () => {
    imported(1, "running");
    render(false);
    await settle(0);
    expect(reads).toHaveLength(1);

    await settle(POLL_INTERVAL_MS / 4);
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await settle(0);
    expect(reads).toHaveLength(2);
  });

  it("gives up on a read that never answers, and converges on the next round", async () => {
    imported(1, "succeeded");
    hangs = 1;
    render(false);
    await settle(0);
    expect(taskState("task-0").state).toBe("pending");

    await settle(READ_TIMEOUT_MS + POLL_INTERVAL_MS);
    expect(taskState("task-0").state).toBe("succeeded");
  });

  it("asks the backend that owns each task", async () => {
    imported(1, "succeeded");
    store.dispatch(taskRegistered({ taskId: "migration-1", kind: "migration" }));
    server.set("migration-1", { state: "succeeded", kind: "migration" });
    render(false);
    await settle(0);

    expect(readPaths.sort()).toEqual(["/control-plane/v1/tasks", "/knowledge-flow/v1/tasks"]);
    expect(taskState("migration-1").state).toBe("succeeded");
  });

  it("leaves no earlier round running after the layout is unmounted and mounted again", async () => {
    imported(60, "running");
    hangs = 1;
    render(false);
    await settle(0);

    // A route outside MainLayout, then back: a new instance of the hook.
    act(() => root.unmount());
    root = createRoot(container);
    render(false);
    await settle(READ_TIMEOUT_MS + POLL_INTERVAL_MS / 2);

    // Every 10-task batch belongs to a round that also read its 50: none is a
    // leftover of the unmounted round.
    const sizes = reads.map((ids) => ids.length);
    expect(sizes.filter((n) => n === 10)).toHaveLength(sizes.filter((n) => n === 50).length);
  });
});

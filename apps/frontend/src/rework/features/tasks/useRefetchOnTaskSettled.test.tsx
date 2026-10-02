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

// The same mount-commit hazard `useNotifyOnNewTaskTarget` guards against, on
// the other hook that calls back into its parent: firing the catch-up inline
// reached a query whose subscription had not started, which RTK Query answers
// by throwing and taking the page down. It showed up for real as: ingest, leave
// the resources page, come back.

import { act, useEffect, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { taskEventReceived, taskRegistered, taskSlice } from "./taskSlice";
import { useRefetchOnTaskSettled } from "./useRefetchOnTaskSettled";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;
let store: ReturnType<typeof makeStore>;

const makeStore = () => configureStore({ reducer: { tasks: taskSlice.reducer } });

const register = (taskId: string, documentUid: string) =>
  taskRegistered({
    taskId,
    kind: "ingestion",
    target: { type: "document", id: documentUid, label: `${documentUid}.pdf` },
    teamId: "team-1",
  });

const settle = (taskId: string, state: "succeeded" | "cancelled" | "failed") =>
  taskEventReceived({
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

beforeEach(() => {
  store = makeStore();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

/** Stands in for a page whose own queries subscribe in its mount effect, with
 *  the workspace that refetches them as its child. */
function Page({ onSettled }: { onSettled: (targetId: string, parentReady: boolean) => void }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setReady(true);
  }, []);
  return <Workspace onSettled={(id) => onSettled(id, ready)} parentReady={ready} />;
}

function Workspace({ onSettled, parentReady }: { onSettled: (id: string) => void; parentReady: boolean }) {
  // Read through a prop so the callback the hook holds sees the live value.
  useRefetchOnTaskSettled("document", (id) => onSettled(id));
  return <div data-ready={String(parentReady)} />;
}

describe("useRefetchOnTaskSettled", () => {
  it("holds the mount catch-up until the parent's own effects have run", async () => {
    // The page was left and reopened after an ingestion finished: the settled
    // task is already in the store when the workspace mounts.
    await act(async () => {
      store.dispatch(register("t1", "doc-1"));
      store.dispatch(settle("t1", "succeeded"));
    });

    const calls: [string, boolean][] = [];
    await act(async () => {
      root.render(
        <Provider store={store}>
          <Page onSettled={(id, ready) => calls.push([id, ready])} />
        </Provider>,
      );
    });

    // Fired — and not from inside the commit that mounted it.
    expect(calls).toEqual([["doc-1", true]]);
  });

  it("fires once per task, on success and on cancellation but not on failure", async () => {
    const calls: string[] = [];
    await act(async () => {
      root.render(
        <Provider store={store}>
          <Page onSettled={(id) => calls.push(id)} />
        </Provider>,
      );
    });
    expect(calls).toEqual([]);

    await act(async () => {
      store.dispatch(register("t1", "doc-1"));
      store.dispatch(settle("t1", "succeeded"));
    });
    // The document survives a failure and keeps rendering from the retained
    // task, so there is nothing to refetch.
    await act(async () => {
      store.dispatch(register("t2", "doc-2"));
      store.dispatch(settle("t2", "failed"));
    });
    // Cancelling erases the half-built document outright — the row and the
    // quota would otherwise stay frozen.
    await act(async () => {
      store.dispatch(register("t3", "doc-3"));
      store.dispatch(settle("t3", "cancelled"));
    });

    expect(calls).toEqual(["doc-1", "doc-3"]);
  });

  it("refetches nothing after unmounting", async () => {
    const calls: string[] = [];
    await act(async () => {
      root.render(
        <Provider store={store}>
          <Page onSettled={(id) => calls.push(id)} />
        </Provider>,
      );
    });
    await act(async () => {
      store.dispatch(register("t1", "doc-1"));
      store.dispatch(settle("t1", "succeeded"));
      root.unmount();
    });

    expect(calls).toEqual([]);
    // afterEach unmounts again; a second unmount of the same root is a no-op.
  });
});

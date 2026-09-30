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

// The mount-commit hazard this hook exists to avoid. Its callers refetch their
// PARENT's queries, and React runs a child's effects before its parent's — so
// firing the catch-up inline reached a query whose subscription had not
// started, which RTK Query answers by throwing and taking the page down. It
// showed up for real as: start an import, leave the resources page, come back.

import { act, useEffect, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { taskRegistered, taskSlice } from "./taskSlice";
import { useNotifyOnNewTaskTarget } from "./useNotifyOnNewTaskTarget";

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
 *  the workspace that calls back into them as its child. */
function Page({ onNotified }: { onNotified: (targetId: string, parentReady: boolean) => void }) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setReady(true);
  }, []);
  return <Workspace onNotified={(id) => onNotified(id, ready)} parentReady={ready} />;
}

function Workspace({ onNotified, parentReady }: { onNotified: (id: string) => void; parentReady: boolean }) {
  // Read through a prop so the callback the hook holds sees the live value.
  useNotifyOnNewTaskTarget("document", (id) => onNotified(id));
  return <div data-ready={String(parentReady)} />;
}

describe("useNotifyOnNewTaskTarget", () => {
  it("holds the mount catch-up until the parent's own effects have run", async () => {
    // The page was left and reopened mid-import: the target is already in the
    // store when the workspace mounts.
    await act(async () => {
      store.dispatch(register("t1", "doc-1"));
    });

    const calls: [string, boolean][] = [];
    await act(async () => {
      root.render(
        <Provider store={store}>
          <Page onNotified={(id, ready) => calls.push([id, ready])} />
        </Provider>,
      );
    });

    // Fired — and not from inside the commit that mounted it.
    expect(calls).toEqual([["doc-1", true]]);
  });

  it("still fires once per target, and only for targets it has not seen", async () => {
    const calls: string[] = [];
    await act(async () => {
      root.render(
        <Provider store={store}>
          <Page onNotified={(id) => calls.push(id)} />
        </Provider>,
      );
    });
    expect(calls).toEqual([]);

    await act(async () => {
      store.dispatch(register("t1", "doc-1"));
    });
    await act(async () => {
      store.dispatch(register("t2", "doc-2"));
    });
    // A second task on a target already announced says nothing new.
    await act(async () => {
      store.dispatch(register("t3", "doc-1"));
    });

    expect(calls).toEqual(["doc-1", "doc-2"]);
  });

  it("announces nothing after unmounting", async () => {
    const calls: string[] = [];
    await act(async () => {
      root.render(
        <Provider store={store}>
          <Page onNotified={(id) => calls.push(id)} />
        </Provider>,
      );
    });
    await act(async () => {
      store.dispatch(register("t1", "doc-1"));
      root.unmount();
    });

    expect(calls).toEqual([]);
    // afterEach unmounts again; a second unmount of the same root is a no-op.
  });
});

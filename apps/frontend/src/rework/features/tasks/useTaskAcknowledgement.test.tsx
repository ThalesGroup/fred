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

// Dismissing a task: the server records it, unless the server does not know
// the task — then a POST could only 404 and leave the card on screen.

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

vi.mock("../../../security/KeycloakService", () => ({
  KeyCloakService: { ensureFreshToken: async () => true, GetToken: () => "token", CallLogout: vi.fn() },
}));

import { knowledgeFlowApi } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { legacyControlPlaneApi } from "../../../slices/legacyControlPlane/legacyControlPlaneOpenApi";
import { taskRegistered, taskSlice } from "./taskSlice";
import { useTaskAcknowledgement } from "./useTaskAcknowledgement";

const makeStore = () =>
  configureStore({
    reducer: {
      tasks: taskSlice.reducer,
      [knowledgeFlowApi.reducerPath]: knowledgeFlowApi.reducer,
      [legacyControlPlaneApi.reducerPath]: legacyControlPlaneApi.reducer,
    },
    middleware: (getDefault) => getDefault().concat(knowledgeFlowApi.middleware, legacyControlPlaneApi.middleware),
  });

let store: ReturnType<typeof makeStore>;
let container: HTMLDivElement;
let root: Root;
let acknowledge: ReturnType<typeof useTaskAcknowledgement>["acknowledge"];
const fetchMock = vi.fn();

function Probe() {
  acknowledge = useTaskAcknowledgement().acknowledge;
  return null;
}

beforeEach(() => {
  store = makeStore();
  fetchMock.mockReset();
  fetchMock.mockImplementation(
    async () =>
      new Response(JSON.stringify({ task_id: "t1", acknowledged_at: "2026-10-04T00:00:00Z", acknowledged_by: "u" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() =>
    root.render(
      <Provider store={store}>
        <Probe />
      </Provider>,
    ),
  );
  store.dispatch(taskRegistered({ taskId: "t1", kind: "migration" }));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

describe("useTaskAcknowledgement", () => {
  it("dismisses a browser activity locally", async () => {
    await act(() => acknowledge("t1", "migration", false));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(store.getState().tasks.byId.t1.acknowledgedAt).not.toBeNull();
  });
});

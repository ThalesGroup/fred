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

import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({ dispatch: vi.fn() }));
vi.mock("react-redux", () => ({ useDispatch: () => h.dispatch }));
vi.mock("../../../security/KeycloakService", () => ({
  KeyCloakService: { GetToken: () => "test-token", GetUserId: () => "user-1" },
}));

import { useTaskRehydration } from "./useTaskRehydration";

function Harness() {
  useTaskRehydration();
  return null;
}

it("restores Fred tasks without contacting the retired evaluator integration", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ tasks: [] }) });
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  const root = createRoot(document.createElement("div"));
  try {
    await act(async () => root.render(<Harness />));
    expect(fetchMock.mock.calls.map(([url]) => url).sort()).toEqual([
      "/control-plane/v1/tasks?scope=user",
      "/knowledge-flow/v1/tasks?scope=user",
    ]);
  } finally {
    await act(async () => root.unmount());
    vi.unstubAllGlobals();
  }
});

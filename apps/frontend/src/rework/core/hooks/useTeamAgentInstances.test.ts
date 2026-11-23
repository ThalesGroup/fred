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

import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ManagedAgentInstanceSummary } from "../../../slices/controlPlane/controlPlaneOpenApi";

const query = vi.hoisted(() => ({
  state: {} as { data?: unknown[]; fulfilledTimeStamp?: number },
  intervals: [] as (number | undefined)[],
}));
vi.mock("../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery: (
    _arg: unknown,
    options: { pollingInterval?: number },
  ) => {
    query.intervals.push(options.pollingInterval);
    return query.state;
  },
}));

import {
  PREPARING_POLL_BUDGET_MS,
  isPreparing,
  preparingPollDelay,
  useTeamAgentInstances,
} from "./useTeamAgentInstances";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const instance = (fields: Partial<ManagedAgentInstanceSummary>) => fields as ManagedAgentInstanceSummary;

describe("isPreparing", () => {
  it("is true while a capability is still preparing", () => {
    expect(isPreparing(instance({ suspension_reason: "capability_pending", suspension_detail: null }))).toBe(true);
  });

  it("is false once the preparation failed, so polling stops", () => {
    expect(
      isPreparing(instance({ suspension_reason: "capability_pending", suspension_detail: "Analysis failed" })),
    ).toBe(false);
  });

  it("is false for available agents and other suspensions", () => {
    expect(isPreparing(instance({ suspension_reason: null }))).toBe(false);
    expect(isPreparing(instance({ suspension_reason: "capability_unavailable" }))).toBe(false);
  });
});

describe("preparingPollDelay", () => {
  it("doubles from 5 s and caps at 60 s", () => {
    expect([0, 1, 2, 3, 4, 5, 9].map((attempt) => preparingPollDelay(attempt, 0))).toEqual([
      5_000, 10_000, 20_000, 40_000, 60_000, 60_000, 60_000,
    ]);
  });

  it("stops once ten minutes have been spent", () => {
    expect(preparingPollDelay(3, PREPARING_POLL_BUDGET_MS - 1)).toBe(40_000);
    expect(preparingPollDelay(3, PREPARING_POLL_BUDGET_MS)).toBe(0);
  });
});

describe("useTeamAgentInstances polling", () => {
  let container: HTMLDivElement;
  let root: Root;
  const preparing = (id: string) =>
    instance({ agent_instance_id: id, suspension_reason: "capability_pending", suspension_detail: null });
  function Harness() {
    useTeamAgentInstances("team");
    return null;
  }
  const answer = (data: ManagedAgentInstanceSummary[], fulfilledTimeStamp: number) => {
    query.state = { data, fulfilledTimeStamp };
    act(() => root.render(createElement(Harness)));
  };
  const interval = () => query.intervals[query.intervals.length - 1];

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(0);
    query.intervals = [];
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.useRealTimers();
  });

  it("backs off with each answer while an agent stays preparing", () => {
    const seen = [1, 2, 3, 4, 5].map((stamp) => {
      answer([preparing("a")], stamp);
      return interval();
    });
    expect(seen).toEqual([5_000, 10_000, 20_000, 40_000, 60_000]);
  });

  it("gives up after the budget, and starts over when the preparing agents change", () => {
    answer([preparing("a")], 1);
    vi.setSystemTime(PREPARING_POLL_BUDGET_MS);
    answer([preparing("a")], 2);
    expect(interval()).toBe(0);
    answer([preparing("a"), preparing("b")], 3);
    expect(interval()).toBe(5_000);
  });

  it("does not poll once nothing is preparing", () => {
    answer([preparing("a")], 1);
    answer([instance({ agent_instance_id: "a", suspension_reason: null })], 2);
    expect(interval()).toBe(0);
  });
});

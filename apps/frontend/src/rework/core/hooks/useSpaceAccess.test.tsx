// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useSpaceAccess } from "./useSpaceAccess";

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const context = { fulfilledTimeStamp: 0, isFetching: false, isError: false };
const refetch = vi.fn();
let query: Record<string, unknown>;

vi.mock("../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMySpacesQuery: () => context,
  useSpaceAccessQuery: () => query,
}));

const answer = (startedTimeStamp: number, allowed = true) => ({
  currentData: { allowed },
  startedTimeStamp,
  isFetching: false,
  isUninitialized: false,
  isError: false,
  refetch,
});

let current: ReturnType<typeof useSpaceAccess>;
function Probe() {
  current = useSpaceAccess("space", "write");
  return null;
}
function mount() {
  const root = createRoot(document.createElement("div"));
  const render = () => act(() => root.render(<Probe />));
  render();
  return render;
}

describe("useSpaceAccess", () => {
  beforeEach(() => {
    refetch.mockClear();
    context.fulfilledTimeStamp = 0;
  });

  it("shows a cached answer but rereads it before trusting it", () => {
    query = answer(1);
    mount();
    expect(current).toMatchObject({ offered: true, allowed: false, settled: false });
    expect(refetch).toHaveBeenCalledOnce();
  });

  it("keeps the answer on display while refreshed memberships are rechecked", () => {
    query = answer(Date.now() + 1000);
    const render = mount();
    expect(current.allowed).toBe(true);
    context.fulfilledTimeStamp = Date.now() + 2000;
    render();
    expect(current).toMatchObject({ offered: true, allowed: false });
    expect(refetch).toHaveBeenCalledOnce();
  });

  it("settles on a refusal", () => {
    query = answer(Date.now() + 1000, false);
    mount();
    expect(current).toMatchObject({ offered: false, allowed: false, settled: true });
  });
});

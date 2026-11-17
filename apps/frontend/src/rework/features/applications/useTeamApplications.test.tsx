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

import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  query: vi.fn((_args: unknown, _options: unknown) => ({ refetch: vi.fn() })),
}));

vi.mock("../../../slices/controlPlane/controlPlaneApiEnhancements.ts", () => ({
  useSpaceApplicationsQuery: (args: unknown, options: unknown) => h.query(args, options),
}));

import { CROSS_SESSION_REFRESH_INTERVAL_MS } from "@hooks/crossSessionRefresh.ts";
import { useTeamApplications } from "./useTeamApplications.ts";

function Host({ skip = false }: { skip?: boolean }) {
  useTeamApplications("team-1", skip);
  return null;
}

function render(skip = false) {
  renderToStaticMarkup(<Host skip={skip} />);
}

describe("useTeamApplications", () => {
  beforeEach(() => {
    h.query.mockClear();
  });

  it("suppresses the catalog subscription and polling when explicitly skipped", () => {
    render(true);
    expect(h.query).toHaveBeenCalledWith(
      { spaceId: "team-1" },
      {
        skip: true,
        pollingInterval: 0,
        refetchOnMountOrArgChange: CROSS_SESSION_REFRESH_INTERVAL_MS / 1000,
      },
    );
  });

  it("keeps the bounded refresh behavior without deployment configuration", () => {
    render();
    expect(h.query).toHaveBeenCalledWith(
      { spaceId: "team-1" },
      {
        skip: false,
        pollingInterval: CROSS_SESSION_REFRESH_INTERVAL_MS,
        refetchOnMountOrArgChange: CROSS_SESSION_REFRESH_INTERVAL_MS / 1000,
      },
    );
  });

  it("preserves an explicit caller skip for unavailable spaces", () => {
    render(true);
    const lastCall = h.query.mock.calls[h.query.mock.calls.length - 1];
    expect(lastCall?.[1]).toMatchObject({ skip: true, pollingInterval: 0 });
  });
});

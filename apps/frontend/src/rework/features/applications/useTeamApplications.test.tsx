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
  enabled: false,
  query: vi.fn((_args: unknown, _options: unknown) => ({ refetch: vi.fn() })),
}));

vi.mock("@hooks/useFrontendFeatureFlag.ts", () => ({
  useFrontendFeatureFlag: () => ({ enabled: h.enabled, isLoading: false }),
}));
vi.mock("../../../slices/controlPlane/controlPlaneApiEnhancements.ts", () => ({
  useTeamApplicationsQuery: (args: unknown, options: unknown) => h.query(args, options),
}));

import { TEAM_APPLICATIONS_REFRESH_INTERVAL_MS, useTeamApplications } from "./useTeamApplications.ts";

function Host({ skip = false }: { skip?: boolean }) {
  useTeamApplications("team-1", skip);
  return null;
}

function render(skip = false) {
  renderToStaticMarkup(<Host skip={skip} />);
}

describe("useTeamApplications", () => {
  beforeEach(() => {
    h.enabled = false;
    h.query.mockClear();
  });

  it("suppresses the catalog subscription and polling while applications are disabled", () => {
    render();
    expect(h.query).toHaveBeenCalledWith(
      { teamId: "team-1" },
      {
        skip: true,
        pollingInterval: 0,
        refetchOnMountOrArgChange: TEAM_APPLICATIONS_REFRESH_INTERVAL_MS / 1000,
      },
    );
  });

  it("keeps the bounded refresh behavior when applications are enabled", () => {
    h.enabled = true;
    render();
    expect(h.query).toHaveBeenCalledWith(
      { teamId: "team-1" },
      {
        skip: false,
        pollingInterval: TEAM_APPLICATIONS_REFRESH_INTERVAL_MS,
        refetchOnMountOrArgChange: TEAM_APPLICATIONS_REFRESH_INTERVAL_MS / 1000,
      },
    );
  });

  it("preserves an explicit caller skip when the feature is enabled", () => {
    h.enabled = true;
    render(true);
    const lastCall = h.query.mock.calls[h.query.mock.calls.length - 1];
    expect(lastCall?.[1]).toMatchObject({ skip: true, pollingInterval: 0 });
  });
});

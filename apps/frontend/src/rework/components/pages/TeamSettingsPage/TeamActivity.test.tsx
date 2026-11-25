// @vitest-environment happy-dom
// Copyright Thales 2026 - SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { DocumentActivityPage } from "../../../../slices/controlPlane/controlPlaneOpenApi";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const h = vi.hoisted(() => ({
  allowed: true,
  fetching: false,
  error: undefined as unknown,
  page: undefined as DocumentActivityPage | undefined,
  query: vi.fn(),
  refetch: vi.fn(),
  access: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }) }));
vi.mock("@core/hooks/useSpaceAccess", () => ({
  useSpaceAccess: (id: string, permission: string) => {
    h.access(id, permission);
    return { allowed: h.allowed, settled: true, refetch: h.refetch };
  },
}));
vi.mock("../../../../slices/controlPlane/controlPlaneApi", () => ({ sessionQueryArgs: (args: unknown) => args }));
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useTeamDocumentActivityQuery: (args: unknown, options: unknown) => {
    h.query(args, options);
    return { currentData: h.page, isFetching: h.fetching, isError: !!h.error, error: h.error, refetch: h.refetch };
  },
}));
import TeamActivity from "./TeamActivity";
let root: Root;
let container: HTMLDivElement;
function Location() {
  const location = useLocation();
  return <output>{location.search}</output>;
}
const render = async (team = "team-a", entry = "/?activitySpace=team-a&until=2026-11-15T09%3A00%3A00Z") => {
  await act(async () =>
    root.render(
      <MemoryRouter initialEntries={[entry]}>
        <TeamActivity key={team} spaceId={team} />
        <Location />
      </MemoryRouter>,
    ),
  );
};
const click = async (key: string) => {
  const button = [...container.querySelectorAll("button")].find((item) => item.textContent?.includes(key));
  expect(button).toBeDefined();
  await act(async () => button!.click());
};
beforeEach(() => {
  h.allowed = true;
  h.fetching = false;
  h.error = undefined;
  h.query.mockClear();
  h.access.mockClear();
  h.refetch.mockClear();
  h.page = {
    until: "2026-11-15T09:00:00Z",
    next_cursor: "next",
    items: [
      {
        id: "attempt",
        kind: "processing",
        status: "running",
        name: "visible.txt",
        target_id: "doc",
        stage: "extraction",
        profile: "fast",
        created_at: "2026-11-15T08:00:00Z",
      },
    ],
  };
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});
it("keeps the terminal outcome during background refresh and restores the selected detail from the URL", async () => {
  await render("team-a", "/?activitySpace=team-a&until=2026-11-15T09%3A00%3A00Z&operation=processing%3Aattempt");
  expect(container.textContent).toContain("rework.teamActivity.reference");
  h.page!.items[0] = { ...h.page!.items[0], status: "succeeded", completed_at: "2026-11-15T09:01:00Z" };
  h.fetching = true;
  await render();
  expect(container.textContent).toContain("visible.txt");
  expect(container.textContent).toContain("rework.tasks.state.succeeded");
  expect(container.textContent).toContain("rework.teamActivity.finishedAt");
  expect(h.query.mock.lastCall?.[1]).toMatchObject({ pollingInterval: 5000 });
});
it("distinguishes empty, load failure and refusal, even with cached content", async () => {
  h.page!.items = [];
  await render();
  expect(container.textContent).toContain("rework.taskActivity.empty");
  h.error = { status: 503 };
  await render();
  expect(container.textContent).toContain("rework.taskActivity.loadError");
  expect(container.textContent).not.toContain("rework.taskActivity.empty");
  h.error = { status: 403 };
  await render();
  expect(container.textContent).toContain("rework.teamActivity.forbidden");
});
it("does not query or disclose content to an owner without Read", async () => {
  h.allowed = false;
  await render();
  expect(h.access).toHaveBeenLastCalledWith("team-a", "read");
  expect(h.query.mock.lastCall?.[1]).toMatchObject({ skip: true });
  expect(container.textContent).not.toContain("visible.txt");
});
it("keeps pagination and filters in the URL and offers an explicit new window", async () => {
  await render("team-a", "/?activitySpace=team-a&until=2026-11-15T09%3A00%3A00Z&kind=processing&status=failed");
  await click("dataTable.pagination.next");
  expect(container.querySelector("output")?.textContent).toContain("before=next");
  expect(h.query.mock.lastCall?.[0]).toMatchObject({ kind: "processing", status: "failed", before: "next" });
  h.fetching = true; // New unanchored query has not returned its new server bound yet.
  await click("rework.teamActivity.newest");
  expect(container.querySelector("output")?.textContent).not.toContain("before=");
  expect(h.query.mock.lastCall?.[0]).toMatchObject({ view: 1, until: undefined });
});
it("drops another team's page, filters and expanded operation", async () => {
  await render();
  h.page = undefined;
  h.fetching = true;
  await render("team-b");
  expect(h.query.mock.lastCall?.[0]).toMatchObject({
    id: "team-b",
    before: undefined,
    until: undefined,
    kind: undefined,
  });
  expect(container.textContent).not.toContain("visible.txt");
});
it("shows blocked cleanup distinctly without proposing cancel, retry or acknowledgement", async () => {
  h.page!.items[0] = {
    ...h.page!.items[0],
    kind: "document_deletion",
    status: "blocked",
    error_code: "document_purge_pending",
  };
  await render();
  expect(container.textContent).toContain("rework.tasks.state.blocked");
  expect(container.textContent).not.toContain("rework.tasks.state.failed");
  expect(container.textContent).not.toContain("rework.taskActivity.acknowledge");
  expect(container.querySelectorAll("button").length).toBeGreaterThan(0);
});

it("refetches the durable page on reconnect and focus, and stops after leaving", async () => {
  await render();
  await act(async () => window.dispatchEvent(new Event("online")));
  await act(async () => window.dispatchEvent(new Event("focus")));
  expect(h.refetch).toHaveBeenCalledTimes(2);
  h.allowed = false;
  await render();
  await act(async () => window.dispatchEvent(new Event("online")));
  expect(h.refetch).toHaveBeenCalledTimes(2);
});

it("retains a known terminal result through a failed refresh but hides it on revocation", async () => {
  h.page!.items[0].status = "succeeded";
  await render();
  h.error = { status: "FETCH_ERROR" };
  await render();
  expect(container.textContent).toContain("rework.teamActivity.stale");
  expect(container.textContent).toContain("rework.tasks.state.succeeded");
  h.error = { status: 403 };
  await render();
  expect(container.textContent).not.toContain("visible.txt");
  expect(container.textContent).not.toContain("rework.tasks.state.succeeded");
});

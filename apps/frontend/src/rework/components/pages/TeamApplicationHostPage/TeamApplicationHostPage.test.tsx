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

import { act, Component, StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  appId: "example",
  isPersonalTeam: false,
  load: vi.fn(async () => ({ default: (_props: Record<string, unknown>) => null })),
  navigate: vi.fn(),
  receivedProps: undefined as Record<string, unknown> | undefined,
  registrationContractDigest: "sha256:abc",
  registrationHostApiVersion: "1",
  registrationId: "example",
  registrationVersion: "1.0.0",
  registryLookups: [] as string[],
  queryArgs: [] as Array<[string | undefined, boolean]>,
  result: { data: undefined, isLoading: false, isError: false } as {
    data?: { catalog_revision: string; items: Array<Record<string, string>> };
    isLoading: boolean;
    isError: boolean;
  },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en", resolvedLanguage: "en" },
  }),
}));
vi.mock("react-router-dom", () => ({
  useParams: () => ({ teamId: "team-1", appId: h.appId, "*": "details" }),
  useNavigate: () => h.navigate,
}));
vi.mock("../../../../hooks/useSelectedTeam.ts", () => ({
  useSelectedTeam: () => ({
    teamId: "team-1",
    isPersonalTeam: h.isPersonalTeam,
    selectedTeam: { id: "team-1", name: "Team One" },
  }),
}));
vi.mock("@rework/features/applications/useTeamApplications.ts", () => ({
  useTeamApplications: (teamId: string | undefined, skip: boolean) => {
    h.queryArgs.push([teamId, skip]);
    return h.result;
  },
}));
vi.mock("@rework/features/applications/generated/applicationRegistry.ts", () => ({
  applicationRegistry: new Proxy(
    {
      example: {
        get id() {
          return h.registrationId;
        },
        get version() {
          return h.registrationVersion;
        },
        get hostApiVersion() {
          return h.registrationHostApiVersion;
        },
        get contractDigest() {
          return h.registrationContractDigest;
        },
        load: h.load,
      },
    },
    {
      get(target, property, receiver) {
        h.registryLookups.push(String(property));
        return Reflect.get(target, property, receiver);
      },
      getOwnPropertyDescriptor(target, property) {
        h.registryLookups.push(String(property));
        return Reflect.getOwnPropertyDescriptor(target, property);
      },
    },
  ),
}));

import TeamApplicationHostPage from "./TeamApplicationHostPage.tsx";
import { reportCaughtReactError } from "@rework/features/applications/ApplicationErrorBoundary.tsx";

const application = {
  id: "example",
  version: "1.0.0",
  name: "applications.example.name",
  description: "applications.example.description",
  icon: "extension",
  host_api_version: "1",
  contract_digest: "sha256:abc",
};
const catalogRevisionA = `sha256:${"a".repeat(64)}`;
const catalogRevisionB = `sha256:${"b".repeat(64)}`;

function render() {
  return renderToStaticMarkup(<TeamApplicationHostPage />);
}

let container: HTMLDivElement | undefined;
let root: Root | undefined;

async function renderClient() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container, { onCaughtError: reportCaughtReactError });
  await rerenderClient();
  return container;
}

async function rerenderClient() {
  await act(async () => {
    root?.render(
      <StrictMode>
        <TeamApplicationHostPage />
      </StrictMode>,
    );
    await Promise.resolve();
  });
}

function consoleCallsContain(calls: readonly unknown[][], text: string) {
  return calls.flat().some((value) => {
    if (value instanceof Error) return value.message.includes(text) || (value.stack?.includes(text) ?? false);
    if (typeof value === "string") return value.includes(text);
    return false;
  });
}

afterEach(() => {
  if (root) {
    act(() => root?.unmount());
  }
  container?.remove();
  root = undefined;
  container = undefined;
  vi.restoreAllMocks();
});

describe("TeamApplicationHostPage admission ordering", () => {
  beforeEach(() => {
    h.appId = "example";
    h.isPersonalTeam = false;
    h.load.mockClear();
    h.load.mockImplementation(async () => ({
      default: (props: Record<string, unknown>) => {
        h.receivedProps = props;
        return <div data-application-loaded />;
      },
    }));
    h.navigate.mockReset();
    h.receivedProps = undefined;
    h.registrationContractDigest = "sha256:abc";
    h.registrationHostApiVersion = "1";
    h.registrationId = "example";
    h.registrationVersion = "1.0.0";
    h.registryLookups = [];
    h.queryArgs = [];
    h.result = { data: undefined, isLoading: false, isError: false };
  });

  it("does not inspect, diagnose, or load a local module before the authorized catalog contains it", async () => {
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => undefined);
    h.appId = "unknown";
    h.result.data = { catalog_revision: "revision", items: [application] };

    const page = await renderClient();

    expect(page.textContent).toContain("teamAppsPage.host.unavailable");
    expect(h.registryLookups).toEqual([]);
    expect(h.load).not.toHaveBeenCalled();
    expect(errorLog).not.toHaveBeenCalled();
  });

  it("does not load an authorized application whose local contract is incompatible", () => {
    h.result.data = { catalog_revision: "revision", items: [{ ...application, contract_digest: "different" }] };

    expect(render()).toContain("teamAppsPage.host.contract-mismatch");
    expect(h.load).not.toHaveBeenCalled();
  });

  it.each([
    {
      name: "missing registry entry",
      appId: "missing",
      catalogApplication: { ...application, id: "missing" },
      status: "missing-module",
    },
    {
      name: "registration id mismatch",
      appId: "example",
      catalogApplication: application,
      status: "registration-id-mismatch",
      registrationId: "different",
    },
    {
      name: "unsupported host API",
      appId: "example",
      catalogApplication: { ...application, host_api_version: "opaque-host-payload" },
      status: "unsupported-host-version",
    },
    {
      name: "version mismatch",
      appId: "example",
      catalogApplication: { ...application, version: "opaque-version-payload" },
      status: "version-mismatch",
    },
    {
      name: "contract mismatch",
      appId: "example",
      catalogApplication: { ...application, contract_digest: "opaque-contract-payload" },
      status: "contract-mismatch",
    },
  ])("diagnoses an authorized $name once without invoking its loader", async (testCase) => {
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => undefined);
    h.appId = testCase.appId;
    if (testCase.registrationId) h.registrationId = testCase.registrationId;
    h.result.data = { catalog_revision: "opaque-catalog-payload", items: [testCase.catalogApplication] };

    const page = await renderClient();

    expect(page.textContent).toContain(`teamAppsPage.host.${testCase.status}`);
    expect(errorLog).toHaveBeenCalledTimes(1);
    expect(errorLog).toHaveBeenCalledWith(
      `[applications] ${testCase.status} resolution failure for ${testCase.appId} at catalog revision <invalid>`,
    );
    expect(consoleCallsContain(errorLog.mock.calls, "opaque-")).toBe(false);
    expect(h.load).not.toHaveBeenCalled();
  });

  it("deduplicates an unchanged revision and reports the same failure once for a new revision", async () => {
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => undefined);
    h.result.data = {
      catalog_revision: catalogRevisionA,
      items: [{ ...application, contract_digest: "opaque-contract-payload" }],
    };

    await renderClient();
    await rerenderClient();
    expect(errorLog).toHaveBeenCalledTimes(1);

    h.result.data = {
      catalog_revision: catalogRevisionA,
      items: [{ ...application, contract_digest: "opaque-contract-payload" }],
    };
    await rerenderClient();
    expect(errorLog).toHaveBeenCalledTimes(1);

    h.result.data = {
      catalog_revision: catalogRevisionB,
      items: [{ ...application, contract_digest: "opaque-contract-payload" }],
    };
    await rerenderClient();
    await rerenderClient();

    expect(errorLog.mock.calls).toEqual([
      [`[applications] contract-mismatch resolution failure for example at catalog revision ${catalogRevisionA}`],
      [`[applications] contract-mismatch resolution failure for example at catalog revision ${catalogRevisionB}`],
    ]);
    expect(consoleCallsContain(errorLog.mock.calls, "opaque-")).toBe(false);
    expect(h.load).not.toHaveBeenCalled();
  });

  it("deduplicates changing invalid revisions without including either remote value", async () => {
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => undefined);
    h.result.data = {
      catalog_revision: "opaque-invalid-revision-a",
      items: [{ ...application, contract_digest: "opaque-contract-payload" }],
    };

    await renderClient();
    h.result.data = {
      catalog_revision: "opaque-invalid-revision-b",
      items: [{ ...application, contract_digest: "opaque-contract-payload" }],
    };
    await rerenderClient();
    await rerenderClient();

    expect(errorLog.mock.calls).toEqual([
      ["[applications] contract-mismatch resolution failure for example at catalog revision <invalid>"],
    ]);
    expect(consoleCallsContain(errorLog.mock.calls, "opaque-invalid-revision-a")).toBe(false);
    expect(consoleCallsContain(errorLog.mock.calls, "opaque-invalid-revision-b")).toBe(false);
    expect(h.load).not.toHaveBeenCalled();
  });

  it("fails closed on a catalog refetch error even if stale data is retained", () => {
    h.result = {
      data: { catalog_revision: "revision", items: [application] },
      isLoading: false,
      isError: true,
    };

    expect(render()).toContain("teamAppsPage.host.unavailable");
    expect(h.load).not.toHaveBeenCalled();
  });

  it("rejects personal spaces even if a stale catalog contains an application", () => {
    h.isPersonalTeam = true;
    h.result.data = { catalog_revision: "revision", items: [application] };

    expect(render()).toContain("teamAppsPage.host.unavailable");
    expect(h.queryArgs).toEqual([["team-1", true]]);
    expect(h.registryLookups).toEqual([]);
    expect(h.load).not.toHaveBeenCalled();
  });

  it("loads a matching registration only after the catalog admits it", async () => {
    h.result.data = { catalog_revision: "revision", items: [application] };

    const page = await renderClient();

    expect(h.registryLookups).toContain("example");
    expect(h.load).toHaveBeenCalledOnce();
    expect(page.querySelector("[data-application-loaded]")).not.toBeNull();
    const context = h.receivedProps?.context as {
      team: Record<string, unknown>;
      route: { basePath: string; subPath: string; navigate: (path: string, options?: { replace?: boolean }) => void };
      locale: string;
      request: unknown;
    };
    expect(Object.keys(context).sort()).toEqual(["locale", "request", "route", "team"]);
    expect(context.team).toEqual({ id: "team-1", name: "Team One", isPersonal: false });
    expect(context.route.basePath).toBe("/team/team-1/apps/example");
    expect(context.route.subPath).toBe("details");
    expect(context.locale).toBe("en");
    expect(context.request).toBeTypeOf("function");

    context.route.navigate("history/2", { replace: true });
    expect(h.navigate).toHaveBeenCalledWith("/team/team-1/apps/example/history/2", { replace: true });
  });

  it("contains a rejected lazy import inside the application host", async () => {
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => undefined);
    h.load.mockRejectedValue(new Error("application domain payload"));
    h.result.data = { catalog_revision: "revision", items: [application] };

    const page = await renderClient();

    expect(page.textContent).toContain("teamAppsPage.host.module-load");
    expect(document.body.textContent).toContain("teamAppsPage.host.module-load");
    expect(errorLog).toHaveBeenCalledTimes(1);
    expect(errorLog).toHaveBeenCalledWith("[applications] module-load failure for example");
    expect(consoleCallsContain(errorLog.mock.calls, "application domain payload")).toBe(false);
  });

  it("contains an application render failure without unmounting Fred", async () => {
    const errorLog = vi.spyOn(console, "error").mockImplementation(() => undefined);
    h.load.mockResolvedValue({
      default: () => {
        throw new Error("application render payload");
      },
    });
    h.result.data = { catalog_revision: "revision", items: [application] };

    const page = await renderClient();

    expect(page.textContent).toContain("teamAppsPage.host.render");
    expect(page.isConnected).toBe(true);
    expect(errorLog).toHaveBeenCalledTimes(1);
    expect(errorLog).toHaveBeenCalledWith("[applications] render failure for example");
    expect(consoleCallsContain(errorLog.mock.calls, "application render payload")).toBe(false);
  });

  it("preserves raw React caught-error reporting for a different boundary", () => {
    class ShellErrorBoundary extends Component<unknown> {}

    const errorLog = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const error = new Error("Fred shell error");

    reportCaughtReactError(error, { errorBoundary: new ShellErrorBoundary({}) });

    expect(errorLog).toHaveBeenCalledOnce();
    expect(errorLog).toHaveBeenCalledWith(error);
  });
});

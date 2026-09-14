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

// What the screen owes a team: one card per base, what each was configured
// with, and never a secret — the API strips those values, so a row for one
// could only ever be an empty promise.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const probe = vi.hoisted(() => ({
  instances: [] as Record<string, unknown>[],
  isLoading: false,
  isError: false,
  fields: undefined as Record<string, unknown> | undefined,
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
  }),
}));

vi.mock("react-router-dom", () => ({
  useParams: () => ({ teamId: "team-1" }),
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => <a href={to}>{children}</a>,
}));

vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements.ts", () => ({
  useKnowledgeBasesQuery: () => ({
    data: probe.instances,
    isLoading: probe.isLoading,
    isError: probe.isError,
  }),
  useDeleteKnowledgeBaseMutation: () => [vi.fn(() => ({ unwrap: () => Promise.resolve() }))],
  useKnowledgeBaseFieldsQuery: () => ({ data: probe.fields }),
  // Reached through the creation modal this page mounts, closed here.
  useKnowledgeBaseDefinitionsQuery: () => ({ data: [], isLoading: false, isError: false }),
  useCreateKnowledgeBaseMutation: () => [vi.fn(() => ({ unwrap: () => Promise.resolve({}) })), { isLoading: false }],
}));

vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: vi.fn() }),
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: vi.fn(), showSuccess: vi.fn() }),
}));

import TeamKnowledgeBasesPage from "./TeamKnowledgeBasesPage.tsx";

function base(overrides: Record<string, unknown> = {}) {
  return {
    id: "kb-1",
    definition_id: "fred.samples.local-folder",
    definition_name: "Local folder",
    team_id: "team-1",
    library_id: "lib-1",
    library_name: "Local-2",
    cadence: "daily",
    suspended: false,
    // What the API actually returns: it strips secret-declared values before
    // they leave the Control Plane, so no fixture here carries one by default.
    configuration: { path: "/srv/docs" },
    created_at: "2026-09-14T08:00:00Z",
    ...overrides,
  };
}

let container: HTMLDivElement;
let root: Root;

function render() {
  act(() => {
    root.render(<TeamKnowledgeBasesPage />);
  });
}

beforeEach(() => {
  probe.instances = [];
  probe.isLoading = false;
  probe.isError = false;
  probe.fields = undefined;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("TeamKnowledgeBasesPage", () => {
  it("names each base and the kind it is", () => {
    probe.instances = [base(), base({ id: "kb-2", library_name: "Notes", definition_name: "Git repository" })];
    render();

    expect(container.textContent).toContain("Local-2");
    expect(container.textContent).toContain("Local folder");
    expect(container.textContent).toContain("Notes");
    expect(container.textContent).toContain("Git repository");
  });

  it("says so when a team has no base at all", () => {
    render();
    expect(container.textContent).toContain("rework.knowledgeBases.empty");
  });

  it("labels the configuration with the titles its author declared", () => {
    probe.instances = [base()];
    probe.fields = {
      configuration_fields: [{ key: "path", type: "string", title: "Folder on disk" }],
    };
    render();

    expect(container.textContent).toContain("Folder on disk");
    expect(container.textContent).toContain("/srv/docs");
  });

  it("never renders a secret-declared field, even handed one", () => {
    // Defence in depth: the API strips these, so this fixture is a Fred that
    // stopped doing so. The screen must still not put it on a card.
    probe.instances = [base({ configuration: { path: "/srv/docs", token: "should never reach the page" } })];
    probe.fields = {
      configuration_fields: [
        { key: "path", type: "string", title: "Folder on disk" },
        { key: "token", type: "secret", title: "Access token" },
      ],
    };
    render();

    expect(container.textContent).toContain("Folder on disk");
    expect(container.textContent).not.toContain("Access token");
    expect(container.textContent).not.toContain("should never reach the page");
  });

  it("leads into the base's own documents", () => {
    probe.instances = [base()];
    render();

    const link = container.querySelector("a");
    expect(link?.getAttribute("href")).toBe("/team/team-1/knowledge-bases/kb-1");
  });
});

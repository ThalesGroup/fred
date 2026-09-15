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

// What the screen owes a team: one card per base, naming it, the kind it is
// and what that kind does. The configuration itself is a settings surface of
// its own — a card that listed it drowned the name it exists to show.

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
  definitions: [] as Record<string, unknown>[],
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
  useKnowledgeBaseDefinitionsQuery: () => ({ data: probe.definitions, isLoading: false, isError: false }),
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
    schedule: { type: "interval" as const, every_seconds: 86400 },
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
  probe.definitions = [
    {
      definition_id: "fred.samples.local-folder",
      name: "Local folder",
      description: "Synchronize documents from a folder on disk.",
    },
  ];
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

  it("says what the kind of base actually does", () => {
    probe.instances = [base()];
    render();

    expect(container.textContent).toContain("Synchronize documents from a folder on disk.");
  });

  it("keeps the configuration off the card entirely", () => {
    // The values are a settings surface of their own. A card listing them is
    // what buried the one thing it exists to show — the base's name.
    probe.instances = [base({ configuration: { path: "/srv/docs" } })];
    render();

    expect(container.textContent).not.toContain("/srv/docs");
  });

  it("falls back rather than showing an empty line when the kind is gone", () => {
    // A definition disabled for the team after a base was created: it drops
    // out of the list the descriptions come from, the base does not.
    probe.definitions = [];
    probe.instances = [base()];
    render();

    expect(container.textContent).toContain("rework.knowledgeBases.card.noDescription");
  });

  it("leads into the base's own documents", () => {
    probe.instances = [base()];
    render();

    const link = container.querySelector("a");
    expect(link?.getAttribute("href")).toBe("/team/team-1/knowledge-bases/kb-1");
  });
});

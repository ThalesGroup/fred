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

// This page browses a base's library with the Resources explorer itself, rooted
// at that library and offering no way to write. What it owes its own tests is
// therefore small: that it delegates, that it roots and locks the explorer
// correctly, and that it says something useful when the base cannot be read.
// How the explorer lists, paginates and previews is covered by its own tests —
// asserting it again here is what let the two views drift apart in the first
// place.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const probe = vi.hoisted(() => ({
  instance: undefined as Record<string, unknown> | undefined,
  isLoading: false,
  /** Every set of props the shared explorer was rendered with. */
  workspaceProps: [] as Record<string, unknown>[],
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("react-router-dom", () => ({
  useParams: () => ({ teamId: "team-1", instanceId: "kb-1" }),
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => <a href={to}>{children}</a>,
}));

vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements.ts", () => ({
  useKnowledgeBaseQuery: () => ({
    data: probe.instance,
    isLoading: probe.isLoading,
    isError: !probe.isLoading && !probe.instance,
  }),
}));

vi.mock("../TeamResourcesPage/DocumentWorkspace/DocumentWorkspace.tsx", () => ({
  default: (props: Record<string, unknown>) => {
    probe.workspaceProps.push(props);
    return <div data-testid="document-workspace" />;
  },
}));

import KnowledgeBaseDocumentsPage from "./KnowledgeBaseDocumentsPage.tsx";

let container: HTMLDivElement;
let root: Root;

async function render() {
  await act(async () => {
    root.render(<KnowledgeBaseDocumentsPage />);
  });
}

beforeEach(() => {
  probe.instance = {
    id: "kb-1",
    library_id: "lib-1",
    library_name: "Local-2",
    definition_name: "Local folder",
  };
  probe.isLoading = false;
  probe.workspaceProps = [];
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("KnowledgeBaseDocumentsPage", () => {
  it("browses the library with the Resources explorer, not a table of its own", async () => {
    await render();

    expect(container.querySelector("[data-testid=document-workspace]")).not.toBeNull();
    // No second table: the whole point is that both views are one component.
    expect(container.querySelector("table")).toBeNull();
  });

  it("roots the explorer at this base's library", async () => {
    // Rooted by tag id rather than by name: a library can be renamed, and two
    // teams' libraries can share a name.
    await render();

    expect(probe.workspaceProps).toHaveLength(1);
    expect(probe.workspaceProps[0]).toMatchObject({ teamId: "team-1", rootTagId: "lib-1" });
  });

  it("offers no way to write into it", async () => {
    // A base fills its own library; a person's write is refused by the backend,
    // so the affordance is withheld rather than shown and then rejected.
    await render();

    expect(probe.workspaceProps[0].readOnly).toBe(true);
  });

  it("names the base and the kind it is", async () => {
    await render();

    expect(container.textContent).toContain("Local-2");
    expect(container.textContent).toContain("Local folder");
  });

  it("says so when the base cannot be read, instead of an empty explorer", async () => {
    probe.instance = undefined;
    await render();

    expect(container.textContent).toContain("rework.knowledgeBases.documents.unavailable.title");
    expect(container.querySelector("[data-testid=document-workspace]")).toBeNull();
  });

  it("waits for the base before rooting anything", async () => {
    // Rendering the explorer with no root would show the whole team corpus —
    // exactly what this page must never do.
    probe.instance = undefined;
    probe.isLoading = true;
    await render();

    expect(probe.workspaceProps).toHaveLength(0);
  });
});

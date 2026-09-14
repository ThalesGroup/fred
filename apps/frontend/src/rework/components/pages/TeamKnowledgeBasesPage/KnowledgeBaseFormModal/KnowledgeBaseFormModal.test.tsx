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

// Creating a base is one call, carrying what its author declared: the fields
// Fred acts on and the fields it only passes through are sent apart, and a
// declared default survives a user who changes nothing.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const probe = vi.hoisted(() => ({
  definitions: [] as Record<string, unknown>[],
  definitionsLoading: false,
  definitionsFailed: false,
  fields: undefined as Record<string, unknown> | undefined,
  created: [] as Record<string, unknown>[],
  rejects: false,
}));

const createTrigger = vi.hoisted(() => (args: Record<string, unknown>) => {
  probe.created.push(args);
  return { unwrap: () => (probe.rejects ? Promise.reject(new Error("nope")) : Promise.resolve({})) };
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("@shared/utils/Portal.tsx", () => ({
  Portal: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: vi.fn(), showSuccess: vi.fn() }),
}));

vi.mock("../../TeamAgentsPage/AgentFormModal/TuningFieldRenderer", () => ({
  TuningFieldRenderer: ({ field }: { field: { key: string; title: string } }) => (
    <div data-field={field.key}>{field.title}</div>
  ),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements.ts", () => ({
  useKnowledgeBaseDefinitionsQuery: () => ({
    data: probe.definitions,
    isLoading: probe.definitionsLoading,
    isError: probe.definitionsFailed,
  }),
  useKnowledgeBaseFieldsQuery: () => ({ data: probe.fields }),
  useCreateKnowledgeBaseMutation: () => [createTrigger, { isLoading: false }],
}));

import KnowledgeBaseFormModal, { buildCreatePayload } from "./KnowledgeBaseFormModal.tsx";

let container: HTMLDivElement;
let root: Root;

async function render() {
  await act(async () => {
    root.render(<KnowledgeBaseFormModal open teamId="team-1" onClose={() => {}} />);
  });
}

function setName(value: string) {
  const input = container.querySelector("input") as HTMLInputElement;
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;
  act(() => {
    setter.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

beforeEach(() => {
  probe.definitions = [{ definition_id: "fred.samples.local-folder", name: "Local folder" }];
  probe.definitionsLoading = false;
  probe.definitionsFailed = false;
  probe.fields = undefined;
  probe.created = [];
  probe.rejects = false;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("KnowledgeBaseFormModal", () => {
  it("tells an empty list apart from a list that failed to load", async () => {
    probe.definitions = [];
    await render();
    expect(container.textContent).toContain("rework.knowledgeBases.form.noDefinitions");

    act(() => root.unmount());
    container.remove();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    probe.definitionsFailed = true;
    await render();
    expect(container.textContent).toContain("rework.knowledgeBases.form.definitionsFailed");
  });

  it("keeps the two zones apart", async () => {
    probe.fields = {
      platform_fields: [{ key: "fred.cadence", type: "select", title: "Cadence" }],
      configuration_fields: [{ key: "path", type: "string", title: "Folder on disk" }],
    };
    await render();

    expect(container.textContent).toContain("rework.knowledgeBases.form.zoneFred");
    expect(container.textContent).toContain("rework.knowledgeBases.form.zoneSource");
    expect(container.querySelectorAll("fieldset")).toHaveLength(2);
  });

  it("refuses to submit without a name and a source", async () => {
    await render();
    const submit = [...container.querySelectorAll("button")].find(
      (button) => button.textContent === "rework.knowledgeBases.form.submit",
    ) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    expect(probe.created).toHaveLength(0);
  });

  it("accepts a name", async () => {
    await render();
    setName("Handbook");
    expect((container.querySelector("input") as HTMLInputElement).value).toBe("Handbook");
  });
});

describe("buildCreatePayload", () => {
  const base = {
    definitionId: "fred.samples.local-folder",
    teamId: "team-1",
    folderName: "Handbook",
  };

  it("sends Fred's own settings apart from the author's", () => {
    const payload = buildCreatePayload({
      ...base,
      declaredConfigurationKeys: ["path"],
      values: { "fred.cadence": "daily", "fred.suspended": true, path: "/srv/docs" },
    });

    expect(payload.cadence).toBe("daily");
    expect(payload.suspended).toBe(true);
    // The source is told what its author declared, and nothing of Fred's: a
    // cadence in there is a key the connector never asked for.
    expect(payload.configuration).toEqual({ path: "/srv/docs" });
  });

  it("carries a declared default the user never touched", () => {
    const payload = buildCreatePayload({
      ...base,
      declaredConfigurationKeys: ["path"],
      values: { path: "/srv/docs" },
    });
    expect(payload.configuration).toEqual({ path: "/srv/docs" });
  });

  it("omits a field left empty rather than sending an empty string", () => {
    const payload = buildCreatePayload({
      ...base,
      declaredConfigurationKeys: ["path", "branch"],
      values: { path: "/srv/docs", branch: "" },
    });
    expect(payload.configuration).toEqual({ path: "/srv/docs" });
  });

  it("never invents a value for a key the definition did not declare", () => {
    const payload = buildCreatePayload({
      ...base,
      declaredConfigurationKeys: ["path"],
      values: { path: "/srv/docs", leftover: "from a previous definition" },
    });
    expect(payload.configuration).toEqual({ path: "/srv/docs" });
  });
});

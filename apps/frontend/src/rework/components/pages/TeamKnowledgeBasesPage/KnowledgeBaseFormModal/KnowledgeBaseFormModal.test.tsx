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

// One surface, two jobs. Creating a base is one call carrying what its author
// declared: the fields Fred acts on and the fields it only passes through are
// sent apart, and a declared default survives a user who changes nothing.
// Opening an existing base shows those same fields, filled in and frozen —
// and never a secret.

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

vi.mock("@shared/utils/Portal.tsx", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@shared/utils/Portal.tsx")>()),
  Portal: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: vi.fn(), showSuccess: vi.fn() }),
}));

// A native select stands in for the molecule, which is a button and a listbox:
// what is under test is what choosing a source does, not how it is picked.
vi.mock("@shared/molecules/Select/Select.tsx", () => ({
  default: ({
    options,
    value,
    onChange,
  }: {
    options: { key: string; value: string; label: string }[];
    value: string;
    onChange: (next: string) => void;
  }) => (
    <select data-testid="source" value={value} onChange={(event) => onChange(event.target.value)}>
      {options.map((option) => (
        <option key={option.key} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));

vi.mock("../../TeamAgentsPage/AgentFormModal/TuningFieldRenderer", () => ({
  TuningFieldRenderer: ({
    field,
    value,
    disabled,
  }: {
    field: { key: string; title: string };
    value: unknown;
    disabled?: boolean;
  }) => (
    <div data-field={field.key} data-disabled={String(!!disabled)}>
      {field.title}
      {value === undefined || value === null ? "" : String(value)}
    </div>
  ),
}));

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements.ts", () => ({
  useKnowledgeBaseDefinitionsQuery: () => ({
    data: probe.definitions,
    isLoading: probe.definitionsLoading,
    isError: probe.definitionsFailed,
  }),
  // Honours `skip`, because that is the whole mechanism here: no declaration is
  // fetched until a source is chosen, and the form has nothing to render until
  // one is.
  useKnowledgeBaseFieldsQuery: (_args: unknown, options?: { skip?: boolean }) => ({
    data: options?.skip ? undefined : probe.fields,
  }),
  useCreateKnowledgeBaseMutation: () => [createTrigger, { isLoading: false }],
}));

import KnowledgeBaseFormModal, { buildCreatePayload, readInstanceValues } from "./KnowledgeBaseFormModal.tsx";
import type {
  KnowledgeBaseInstanceFields,
  KnowledgeBaseInstanceSummary,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi.ts";

let container: HTMLDivElement;
let root: Root;

function instanceFixture(overrides: Partial<KnowledgeBaseInstanceSummary> = {}): KnowledgeBaseInstanceSummary {
  return {
    id: "kb-1",
    definition_id: "fred.samples.local-folder",
    definition_name: "Local folder",
    team_id: "team-1",
    library_id: "lib-1",
    library_name: "Handbook",
    schedule: { type: "interval" as const, every_seconds: 86400 },
    suspended: false,
    configuration: { path: "/srv/docs" },
    created_at: "2026-09-14T08:00:00Z",
    updated_at: "2026-09-14T08:00:00Z",
    ...overrides,
  };
}

async function render(instance?: KnowledgeBaseInstanceSummary) {
  await act(async () => {
    root.render(<KnowledgeBaseFormModal open teamId="team-1" instance={instance} onClose={() => {}} />);
  });
}

/** Which surface is on screen: the app's central `Dialog` asks the couple of
 *  questions, `SettingsModal` (through `FullPageModal`) hosts the form. */
const onSettingsPage = () => container.querySelector('[data-background="container"]') !== null;

async function chooseSource(definitionId: string) {
  const select = container.querySelector('[data-testid="source"]') as HTMLSelectElement;
  await act(async () => {
    select.value = definitionId;
    select.dispatchEvent(new Event("change", { bubbles: true }));
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
      configuration_fields: [{ key: "path", type: "string", title: "Folder on disk" }],
    };
    await render();
    await chooseSource("fred.samples.local-folder");

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

  it("asks which source in a dialog, and only then takes the page", async () => {
    probe.fields = {
      configuration_fields: [{ key: "path", type: "string", title: "Folder on disk" }],
    };
    await render();

    // Nothing is chosen yet, so there is no form to show — a full-page
    // takeover here would be a screen of empty space.
    expect(onSettingsPage()).toBe(false);
    expect(container.querySelector("fieldset")).toBeNull();

    await chooseSource("fred.samples.local-folder");

    expect(onSettingsPage()).toBe(true);
    expect(container.textContent).toContain("Folder on disk");
  });
});

describe("KnowledgeBaseFormModal, on an existing base", () => {
  const fields = {
    configuration_fields: [{ key: "path", type: "string", title: "Folder on disk" }],
  };

  it("shows what the base was configured with", async () => {
    probe.fields = fields;
    await render(instanceFixture());

    expect(container.textContent).toContain("Folder on disk");
    expect(container.textContent).toContain("/srv/docs");
    expect(container.textContent).toContain("rework.schedule.label");
  });

  it("opens straight onto the page, its source being already settled", async () => {
    probe.fields = fields;
    await render(instanceFixture());

    expect(onSettingsPage()).toBe(true);
  });

  it("freezes every field, because nothing here can be saved", async () => {
    probe.fields = fields;
    await render(instanceFixture());

    // No update route exists on the Control Plane: an editable field would
    // promise a save that cannot happen.
    expect((container.querySelector("input") as HTMLInputElement).disabled).toBe(true);
    for (const rendered of container.querySelectorAll("[data-field]")) {
      expect(rendered.getAttribute("data-disabled")).toBe("true");
    }
    expect([...container.querySelectorAll("button")].map((button) => button.textContent)).not.toContain(
      "rework.knowledgeBases.form.submit",
    );
  });

  it("never renders a secret, even handed one", async () => {
    // Defence in depth: the API strips these before they leave it, so this
    // fixture is a Fred that stopped doing so.
    probe.fields = {
      ...fields,
      configuration_fields: [...fields.configuration_fields, { key: "token", type: "secret", title: "Access token" }],
    };
    await render(instanceFixture({ configuration: { path: "/srv/docs", token: "should never reach the screen" } }));

    // The field itself is shown — an author declared it, and a blank one is
    // the truth. Its value is what must not arrive.
    expect(container.textContent).toContain("Access token");
    expect(container.textContent).not.toContain("should never reach the screen");
  });
});

describe("readInstanceValues", () => {
  const declaration: KnowledgeBaseInstanceFields = {
    configuration_fields: [
      { key: "path", type: "string", title: "Folder on disk" },
      { key: "token", type: "secret", title: "Access token" },
    ],
  };

  it("carries the author's fields only — what Fred owns is typed on the instance", () => {
    const values = readInstanceValues(
      instanceFixture({
        schedule: { type: "interval", every_seconds: 604800 },
        suspended: true,
        configuration: { path: "/srv/docs" },
      }),
      declaration,
    );

    expect(values.path).toBe("/srv/docs");
    // No key of Fred's own travels through the generic values any more.
    expect(Object.keys(values).some((key) => key.startsWith("fred."))).toBe(false);
  });

  it("drops a secret-declared value and keeps the rest", () => {
    const values = readInstanceValues(
      instanceFixture({ configuration: { path: "/srv/docs", token: "leaked" } }),
      declaration,
    );

    expect(values.path).toBe("/srv/docs");
    expect(values).not.toHaveProperty("token");
  });

  it("carries no configuration at all until the declaration says which is a secret", () => {
    // The fields query answers after the panel is on screen, and can answer
    // from cache on the very next render. Carrying values before it lands is
    // what would put a secret in the DOM for that frame.
    const values = readInstanceValues(instanceFixture({ configuration: { path: "/srv/docs", token: "leaked" } }));

    expect(values).not.toHaveProperty("path");
    expect(values).not.toHaveProperty("token");
  });

  it("ignores a stored value no declared field asks for", () => {
    // A definition that dropped a field leaves the value behind in storage.
    // Nothing renders it, so carrying it would only be state nobody reads.
    const values = readInstanceValues(
      instanceFixture({ configuration: { path: "/srv/docs", legacy: "left over" } }),
      declaration,
    );

    expect(values.path).toBe("/srv/docs");
    expect(values).not.toHaveProperty("legacy");
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
      values: { path: "/srv/docs" },
      schedule: { type: "interval", every_seconds: 3600 },
      suspended: true,
    });

    expect(payload.schedule).toEqual({ type: "interval", every_seconds: 3600 });
    expect(payload.suspended).toBe(true);
    // The source is told what its author declared, and nothing of Fred's:
    // a key of Fred's own in there is one the connector never asked for.
    expect(payload.configuration).toEqual({ path: "/srv/docs" });
  });

  it("carries a declared default the user never touched", () => {
    const payload = buildCreatePayload({
      ...base,
      declaredConfigurationKeys: ["path"],
      values: { path: "/srv/docs" },
      schedule: { type: "interval", every_seconds: 86400 },
      suspended: false,
    });
    expect(payload.configuration).toEqual({ path: "/srv/docs" });
  });

  it("omits a field left empty rather than sending an empty string", () => {
    const payload = buildCreatePayload({
      ...base,
      declaredConfigurationKeys: ["path", "branch"],
      values: { path: "/srv/docs", branch: "" },
      schedule: { type: "interval", every_seconds: 86400 },
      suspended: false,
    });
    expect(payload.configuration).toEqual({ path: "/srv/docs" });
  });

  it("never invents a value for a key the definition did not declare", () => {
    const payload = buildCreatePayload({
      ...base,
      declaredConfigurationKeys: ["path"],
      values: { path: "/srv/docs", leftover: "from a previous definition" },
      schedule: { type: "interval", every_seconds: 86400 },
      suspended: false,
    });
    expect(payload.configuration).toEqual({ path: "/srv/docs" });
  });
});

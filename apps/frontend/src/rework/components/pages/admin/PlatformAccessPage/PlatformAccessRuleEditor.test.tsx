// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import type { PlatformAccessState } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
const hooks = vi.hoisted(() => ({ preview: vi.fn(), save: vi.fn() }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: { number: number }) => (values ? `${key} ${values.number}` : key),
  }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePlatformAccessClaimsQuery: () => ({
    data: [
      { path: ["profile", "unit"], types: ["string"] },
      { path: ["a.b"], types: ["string_array"] },
      { path: ["department"], types: ["string"] },
      { path: ["iss"], types: ["string"] },
    ],
  }),
  usePlatformAccessOwnClaimsQuery: () => ({
    data: {
      claims: {
        department: "Customer Services",
        name: "Demo person",
        iss: "https://identity.example.test/realms/demo",
        scope: "openid profile",
        profile: { unit: "actual" },
        "a.b": ["one", "two", "a.b[2]"],
        exp: 123,
        enabled: true,
      },
      selectable_paths: [["department"], ["name"], ["iss"], ["scope"], ["profile", "unit"], ["a.b"]],
      truncated: false,
    },
  }),
  usePreviewPlatformPolicyMutation: () => [hooks.preview],
  useSavePlatformPolicyMutation: () => [hooks.save],
}));
import PlatformAccessRuleEditor from "./PlatformAccessRuleEditor";
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement, root: Root, state: PlatformAccessState;
const reload = vi.fn();
beforeEach(() => {
  vi.clearAllMocks();
  state = {
    filtering_enabled: false,
    t0_completed_at: null,
    revision: 1,
    policy: {
      combination: "all",
      conditions: [{ claim: ["profile", "unit"], operator: "contains", value: "accepted" }],
    },
  };
  hooks.preview.mockReturnValue({ unwrap: async () => ({ matched: false, admitted: true, conditions: ["missing"] }) });
  hooks.save.mockImplementation(({ setPlatformAccessPolicy }) => ({
    unwrap: async () => ({ ...state, policy: setPlatformAccessPolicy.policy, revision: 2 }),
  }));
  reload.mockResolvedValue(state);
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});
const render = () =>
  act(() => root.render(<PlatformAccessRuleEditor state={state} disabled={false} reload={reload} />));
const button = (name: string) =>
  [...host.querySelectorAll("button")].find(
    (node) => node.textContent?.trim() === `rework.platformAccess.rule.${name}`,
  )!;
const input = (label: string) =>
  [...host.querySelectorAll("input")].find(
    (node) => node.labels?.[0]?.textContent === `rework.platformAccess.rule.${label}`,
  )!;
const change = (node: HTMLInputElement, value: string) =>
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(node, value);
    node.dispatchEvent(new Event("input", { bubbles: true }));
  });
it("previews without saving and distinguishes rule match from independent admission", async () => {
  render();
  await act(async () => button("test").click());
  expect(hooks.preview).toHaveBeenCalledWith({ platformAccessPolicy: state.policy });
  expect(hooks.save).not.toHaveBeenCalled();
  expect(host.textContent).toContain("rework.platformAccess.rule.result.missing");
  expect(host.textContent).toContain("rework.platformAccess.rule.ruleDoesNotMatch");
  expect(host.textContent).toContain("rework.platformAccess.rule.admitted");
  change(input("value"), "new");
  expect(host.textContent).not.toContain("rework.platformAccess.rule.result.missing");
});
it("preserves drafts on concurrent refresh and conflict, then explicitly reloads", async () => {
  hooks.save.mockReturnValue({
    unwrap: async () => {
      throw { status: 409, data: { detail: "platform_access_policy_conflict" } };
    },
  });
  render();
  change(input("value"), "draft");
  state = {
    ...state,
    revision: 2,
    policy: { ...state.policy!, conditions: [{ claim: ["other"], operator: "equals", value: "remote" }] },
  };
  reload.mockResolvedValue(state);
  render();
  expect(input("value").value).toBe("draft");
  await act(async () => button("save").click());
  expect(hooks.save.mock.calls[0][0].setPlatformAccessPolicy.expected_revision).toBe(1);
  expect(host.textContent).toContain("rework.platformAccess.rule.conflict");
  expect(input("value").value).toBe("draft");
  expect(button("save").disabled).toBe(true);
  await act(async () => button("reload").click());
  expect(input("value").value).toBe("remote");
});
it("adds literal nested keys and conditions without interpreting dots", async () => {
  render();
  change(input("pathKey 1"), "a.b");
  await act(async () => button("test").click());
  expect(hooks.preview.mock.calls[0][0].platformAccessPolicy.conditions[0].claim).toEqual(["a.b", "unit"]);
  act(() => button("addCondition").click());
  expect(host.querySelectorAll("fieldset")).toHaveLength(2);
  expect(button("test").disabled).toBe(true);
  const removals = [...host.querySelectorAll("button")].filter(
    (node) => node.textContent === "rework.platformAccess.rule.removeCondition",
  );
  act(() => removals[1].click());
  expect(host.querySelectorAll("fieldset")).toHaveLength(1);
});
it("keeps selection accessible by keyboard", () => {
  render();
  const selector = host.querySelector<HTMLButtonElement>('button[aria-haspopup="listbox"][aria-labelledby]')!;
  act(() => selector.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowDown", bubbles: true })));
  expect(selector.getAttribute("aria-expanded")).toBe("true");
  expect(document.querySelector('[role="listbox"]')).not.toBeNull();
  act(() => selector.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
  expect(selector.getAttribute("aria-expanded")).toBe("false");
});

it("clears the preview when a clean rule is replaced by a newer revision", async () => {
  render();
  await act(async () => button("test").click());
  expect(host.textContent).toContain("rework.platformAccess.rule.result.missing");
  state = {
    ...state,
    revision: 2,
    policy: { ...state.policy!, conditions: [{ claim: ["other"], operator: "equals", value: "remote" }] },
  };
  render();
  expect(input("value").value).toBe("remote");
  expect(host.textContent).not.toContain("rework.platformAccess.rule.result.missing");
});

it("links invalid regex feedback to the affected condition and keeps the draft", async () => {
  state.policy!.conditions[0] = { claim: ["unit"], operator: "regex", value: "[" };
  hooks.preview.mockReturnValue({
    unwrap: async () => {
      throw {
        status: 422,
        data: { detail: [{ loc: ["body", "conditions", 0], msg: "Invalid regular expression", type: "value_error" }] },
      };
    },
  });
  render();
  await act(async () => button("test").click());
  expect(input("regex").value).toBe("[");
  expect(input("regex").getAttribute("aria-invalid")).toBe("true");
  expect(host.textContent).toContain("rework.platformAccess.rule.invalidRegex");
});

it("ignores an in-flight preview when its clean rule is replaced", async () => {
  let resolve!: (value: { matched: boolean; admitted: boolean; conditions: ["missing"] }) => void;
  hooks.preview.mockReturnValue({
    unwrap: () =>
      new Promise((done) => {
        resolve = done;
      }),
  });
  render();
  act(() => button("test").click());
  state = {
    ...state,
    revision: 2,
    policy: { ...state.policy!, conditions: [{ claim: ["other"], operator: "equals", value: "remote" }] },
  };
  render();
  await act(async () => resolve({ matched: false, admitted: true, conditions: ["missing"] }));
  expect(input("value").value).toBe("remote");
  expect(host.textContent).not.toContain("rework.platformAccess.rule.result.missing");
});

it("selects real session keys into a draft without saving or interpreting literal dots", async () => {
  render();
  const choose = [...host.querySelectorAll("button")].find(
    (node) => node.textContent === "rework.platformAccess.picker.choose",
  )!;
  act(() => choose.click());
  const dialog = document.querySelector('[role="dialog"]')!;
  act(() =>
    [...dialog.querySelectorAll("button")]
      .find((node) => node.textContent === "rework.platformAccess.picker.advancedFields")!
      .click(),
  );
  const key = [...dialog.querySelectorAll("button")].find((node) => node.textContent === '\"a.b\"')!;
  act(() => key.click());
  expect(hooks.save).not.toHaveBeenCalled();
  const confirm = [...dialog.querySelectorAll("button")].find(
    (node) => node.textContent === "rework.platformAccess.picker.useField",
  )!;
  act(() => confirm.click());
  await act(async () => button("test").click());
  expect(hooks.preview.mock.calls[0][0].platformAccessPolicy.conditions[0]).toMatchObject({
    claim: ["a.b"],
    value: "accepted",
  });
  expect(document.querySelector('[role="dialog"]')).toBeNull();
});
it("copies one current array element explicitly and keeps unsupported keys disabled", async () => {
  render();
  act(() =>
    [...host.querySelectorAll("button")]
      .find((node) => node.textContent === "rework.platformAccess.picker.choose")!
      .click(),
  );
  const dialog = document.querySelector('[role="dialog"]')!;
  act(() =>
    [...dialog.querySelectorAll("button")]
      .find((node) => node.textContent === "rework.platformAccess.picker.advancedFields")!
      .click(),
  );
  const find = (label: string) => [...dialog.querySelectorAll("button")].find((node) => node.textContent === label)!;
  expect(find('"exp"').disabled).toBe(true);
  expect(find('"enabled"').disabled).toBe(true);
  act(() => find('"a.b"').click());
  act(() => find('"two"').click());
  act(() => find("rework.platformAccess.picker.useField").click());
  expect(input("value").value).toBe("two");
  expect(hooks.save).not.toHaveBeenCalled();
});

it("keeps Enter on a JSON branch from implicitly confirming a selected field", () => {
  render();
  act(() =>
    [...host.querySelectorAll("button")]
      .find((node) => node.textContent === "rework.platformAccess.picker.choose")!
      .click(),
  );
  const dialog = document.querySelector('[role="dialog"]')!;
  act(() =>
    [...dialog.querySelectorAll("button")]
      .find((node) => node.textContent === "rework.platformAccess.picker.advancedFields")!
      .click(),
  );
  act(() => [...dialog.querySelectorAll("button")].find((node) => node.textContent === '\"a.b\"')!.click());
  const summary = dialog.querySelector("summary")!;
  act(() => summary.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
  expect(document.querySelector('[role="dialog"]')).not.toBeNull();
  expect(hooks.save).not.toHaveBeenCalled();
});

it("reuses a current value as a literal when the condition uses regex", () => {
  state.policy!.conditions[0].operator = "regex";
  render();
  act(() =>
    [...host.querySelectorAll("button")]
      .find((node) => node.textContent === "rework.platformAccess.picker.choose")!
      .click(),
  );
  const dialog = document.querySelector('[role="dialog"]')!;
  act(() =>
    [...dialog.querySelectorAll("button")]
      .find((node) => node.textContent === "rework.platformAccess.picker.advancedFields")!
      .click(),
  );
  const find = (label: string) => [...dialog.querySelectorAll("button")].find((node) => node.textContent === label)!;
  act(() => find('"a.b"').click());
  act(() => find('"a.b[2]"').click());
  act(() => find("rework.platformAccess.picker.useField").click());
  expect(input("regex").value).toBe("a\\.b\\[2\\]");
  expect(hooks.save).not.toHaveBeenCalled();
});

const openPicker = () => {
  render();
  act(() =>
    [...host.querySelectorAll("button")]
      .find((node) => node.textContent === "rework.platformAccess.picker.choose")!
      .click(),
  );
  return document.querySelector('[role="dialog"]')!;
};
const pickerButton = (dialog: Element, label: string) =>
  [...dialog.querySelectorAll("button")].find((node) => node.textContent?.trim() === label);

it("defaults to root text account attributes and explicitly copies a selected value", async () => {
  const dialog = openPicker();
  expect(pickerButton(dialog, '"department"')).toBeDefined();
  expect(pickerButton(dialog, '"name"')).toBeDefined();
  for (const key of ["iss", "scope", "profile", "a.b", "exp", "enabled"])
    expect(pickerButton(dialog, JSON.stringify(key))).toBeUndefined();
  expect(dialog.querySelector("summary")).toBeNull();
  act(() => pickerButton(dialog, '"department"')!.click());
  act(() => pickerButton(dialog, '"Customer Services"')!.click());
  act(() => pickerButton(dialog, "rework.platformAccess.picker.useField")!.click());
  expect(input("value").value).toBe("Customer Services");
  expect(hooks.save).not.toHaveBeenCalled();
  await act(async () => button("test").click());
  expect(hooks.preview.mock.calls[0][0].platformAccessPolicy.conditions[0].claim).toEqual(["department"]);
});

it("limits observed names to root text attributes until advanced fields are requested", () => {
  const dialog = openPicker();
  act(() => pickerButton(dialog, "rework.platformAccess.picker.observed")!.click());
  expect(dialog.textContent).toContain('"department"');
  expect(dialog.textContent).not.toContain('"iss"');
  expect(dialog.textContent).not.toContain('"profile"');
  expect(dialog.textContent).not.toContain('"a.b"');
  act(() => pickerButton(dialog, "rework.platformAccess.picker.advancedFields")!.click());
  expect(dialog.textContent).toContain('"iss"');
  expect(dialog.textContent).toContain('"profile" > "unit"');
  expect(dialog.textContent).toContain('"a.b"');
});

it("clears hidden advanced selections and copied values without changing the draft", () => {
  const dialog = openPicker();
  act(() => pickerButton(dialog, "rework.platformAccess.picker.advancedFields")!.click());
  act(() => pickerButton(dialog, '"a.b"')!.click());
  act(() => pickerButton(dialog, '"two"')!.click());
  act(() => pickerButton(dialog, "rework.platformAccess.picker.simpleFields")!.click());
  expect(pickerButton(dialog, "rework.platformAccess.picker.useField")!.disabled).toBe(true);
  expect(dialog.textContent).not.toContain("rework.platformAccess.picker.copied");
  expect(input("value").value).toBe("accepted");
  act(() => pickerButton(dialog, "rework.platformAccess.picker.advancedFields")!.click());
  expect(pickerButton(dialog, "rework.platformAccess.picker.useField")!.disabled).toBe(true);
  expect(hooks.save).not.toHaveBeenCalled();
});

it("reports an empty simple search without exposing hidden token metadata", () => {
  const dialog = openPicker();
  change(dialog.querySelector("input")!, "iss");
  expect(dialog.textContent).toContain("rework.platformAccess.picker.simpleEmpty");
  expect(pickerButton(dialog, '"iss"')).toBeUndefined();
  act(() => pickerButton(dialog, "rework.platformAccess.picker.advancedFields")!.click());
  expect(pickerButton(dialog, '"iss"')).toBeDefined();
  act(() => pickerButton(dialog, "rework.platformAccess.picker.simpleFields")!.click());
  change(dialog.querySelector("input")!, "DEPART");
  expect(pickerButton(dialog, '"department"')).toBeDefined();
  expect(dialog.textContent).not.toContain("rework.platformAccess.picker.simpleEmpty");
});

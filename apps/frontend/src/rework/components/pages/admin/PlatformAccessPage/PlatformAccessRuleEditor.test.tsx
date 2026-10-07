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
    ],
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

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
const showPicker = () => {
  const field = host.querySelector<HTMLButtonElement>('button[aria-label^="rework.platformAccess.rule.accountField"]')!;
  act(() => field.click());
};
const valuePrompt = (useValue: boolean, example?: string) => {
  const dialog = document.querySelector('[role="dialog"]')!;
  if (example) {
    act(() => dialog.querySelector<HTMLButtonElement>('button[aria-haspopup="listbox"]')!.click());
    act(() =>
      [...document.querySelectorAll<HTMLElement>('[role="option"]')]
        .find((node) => node.textContent?.trim() === example)!
        .click(),
    );
  }
  act(() =>
    [...dialog.querySelectorAll("button")]
      .find(
        (node) => node.textContent?.trim() === `rework.platformAccess.picker.${useValue ? "useValue" : "keepValue"}`,
      )!
      .click(),
  );
};
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
const confirmField = (name = '"department"') => {
  const dialog = document.querySelector('[role="dialog"]')!;
  act(() => [...dialog.querySelectorAll("button")].find((node) => node.textContent === name)!.click());
  act(() =>
    [...dialog.querySelectorAll("button")]
      .find((node) => node.textContent === "rework.platformAccess.picker.useField")!
      .click(),
  );
};
it("adds only confirmed fields and permits an empty unsaved draft", () => {
  state.policy = null;
  render();
  expect(host.querySelectorAll("fieldset")).toHaveLength(0);
  expect(button("test").disabled).toBe(true);
  expect(button("save").disabled).toBe(true);
  act(() => button("addCondition").click());
  expect(host.querySelectorAll("fieldset")).toHaveLength(0);
  act(() => [...document.querySelectorAll("button")].find((node) => node.textContent === "common.cancel")!.click());
  expect(host.textContent).not.toContain("rule.unsaved");
  act(() => button("addCondition").click());
  confirmField();
  valuePrompt(true);
  expect(host.querySelectorAll("fieldset")).toHaveLength(1);
  act(() =>
    host
      .querySelector<HTMLButtonElement>('button[aria-label^="rework.platformAccess.rule.removeConditionNumber"]')!
      .click(),
  );
  expect(host.querySelectorAll("fieldset")).toHaveLength(0);
  expect(button("save").disabled).toBe(true);
  expect(hooks.save).not.toHaveBeenCalled();
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
  expect(host.textContent).not.toContain("1 / 2048");
  expect(input("regex").closest("[data-compact]")?.getAttribute("data-compact")).toBe("false");
});

it("keeps case handling visible without a manual path editor", async () => {
  render();
  const field = host.querySelector<HTMLButtonElement>('button[aria-label^="rework.platformAccess.rule.accountField"]')!;
  expect(field.getAttribute("aria-label")).toContain('"profile" > "unit"');
  expect(host.querySelector("fieldset > details")).toBeNull();
  const toggle = host.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
  expect(toggle.closest("details")).toBeNull();
  expect(toggle.closest("label")?.getAttribute("data-size")).toBe("small");
  act(() => toggle.click());
  await act(async () => button("test").click());
  expect(hooks.preview.mock.calls[0][0].platformAccessPolicy.conditions[0]).toMatchObject({
    claim: ["profile", "unit"],
    case_sensitive: true,
  });
  expect(hooks.save).not.toHaveBeenCalled();
});

it("changes combination without saving and identifies each removable condition", async () => {
  render();
  act(() => button("addCondition").click());
  confirmField();
  valuePrompt(true);
  const removal = host.querySelector<HTMLButtonElement>(
    'button[aria-label="rework.platformAccess.rule.removeConditionNumber 2"]',
  )!;
  expect(removal).not.toBeNull();
  act(() => removal.click());
  act(() => button("any").click());
  expect(button("any").getAttribute("aria-pressed")).toBe("true");
  expect(button("all").getAttribute("aria-pressed")).toBe("false");
  await act(async () => button("test").click());
  expect(hooks.preview.mock.calls[0][0].platformAccessPolicy.combination).toBe("any");
  expect(hooks.save).not.toHaveBeenCalled();
});

it("shows the operand counter only near its unchanged limit", () => {
  render();
  change(input("value"), "x".repeat(921));
  expect(host.textContent).not.toContain("921 / 1024");
  expect(input("value").maxLength).toBe(1024);
  change(input("value"), "x".repeat(922));
  expect(host.textContent).toContain("922 / 1024");
  change(input("value"), "short");
  expect(host.textContent).not.toContain("5 / 1024");
  expect(button("save").disabled).toBe(false);
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
  showPicker();
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
  valuePrompt(false);
  await act(async () => button("test").click());
  expect(hooks.preview.mock.calls[0][0].platformAccessPolicy.conditions[0]).toMatchObject({
    claim: ["a.b"],
    value: "accepted",
  });
  expect(document.querySelector('[role="dialog"]')).toBeNull();
});
it("copies one current array element explicitly and keeps unsupported keys disabled", async () => {
  render();
  showPicker();
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
  act(() => find("rework.platformAccess.picker.useField").click());
  valuePrompt(true, "two");
  expect(input("value").value).toBe("two");
  expect(hooks.save).not.toHaveBeenCalled();
});

it("keeps Enter on a JSON branch from implicitly confirming a selected field", () => {
  render();
  showPicker();
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
  showPicker();
  const dialog = document.querySelector('[role="dialog"]')!;
  act(() =>
    [...dialog.querySelectorAll("button")]
      .find((node) => node.textContent === "rework.platformAccess.picker.advancedFields")!
      .click(),
  );
  const find = (label: string) => [...dialog.querySelectorAll("button")].find((node) => node.textContent === label)!;
  act(() => find('"a.b"').click());
  act(() => find("rework.platformAccess.picker.useField").click());
  valuePrompt(true, "a.b[2]");
  expect(input("regex").value).toBe("a\\.b\\[2\\]");
  expect(hooks.save).not.toHaveBeenCalled();
});

const openPicker = () => {
  render();
  showPicker();
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
  act(() => pickerButton(dialog, "rework.platformAccess.picker.useField")!.click());
  expect(input("value").value).toBe("accepted");
  valuePrompt(true);
  expect(input("value").value).toBe("Customer Services");
  expect(hooks.save).not.toHaveBeenCalled();
  await act(async () => button("test").click());
  expect(hooks.preview.mock.calls[0][0].platformAccessPolicy.conditions[0].claim).toEqual(["department"]);
});

it("exposes only own fields in a named keyboard scroll region", () => {
  const dialog = openPicker();
  expect(pickerButton(dialog, "rework.platformAccess.picker.observed")).toBeUndefined();
  const region = dialog.querySelector<HTMLElement>('[role="region"]')!;
  expect(region.getAttribute("aria-label")).toBe("rework.platformAccess.picker.own");
  expect(region.tabIndex).toBe(0);
  expect(dialog.querySelector('[data-scroll-mode="children"]')).not.toBeNull();
});

it("clears hidden advanced selections without changing the draft", () => {
  const dialog = openPicker();
  act(() => pickerButton(dialog, "rework.platformAccess.picker.advancedFields")!.click());
  act(() => pickerButton(dialog, '"a.b"')!.click());
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

it("opens the own JSON directly and preserves its original revision while selecting", async () => {
  render();
  showPicker();
  expect(document.querySelector('[role="listbox"]')).toBeNull();
  state = {
    ...state,
    revision: 2,
    policy: { combination: "all", conditions: [{ claim: ["other"], operator: "equals", value: "remote" }] },
  };
  render();
  confirmField();
  valuePrompt(false);
  expect(input("value").value).toBe("accepted");
  await act(async () => button("save").click());
  expect(hooks.save.mock.calls[0][0].setPlatformAccessPolicy).toMatchObject({
    expected_revision: 1,
    policy: { conditions: [{ claim: ["department"], value: "accepted" }] },
  });
});
it("adopts a newer clean policy after picker cancellation", () => {
  render();
  showPicker();
  state = {
    ...state,
    revision: 2,
    policy: { combination: "all", conditions: [{ claim: ["other"], operator: "equals", value: "remote" }] },
  };
  render();
  act(() => [...document.querySelectorAll("button")].find((node) => node.textContent === "common.cancel")!.click());
  expect(input("value").value).toBe("remote");
  expect(hooks.save).not.toHaveBeenCalled();
});

it("places persisted allow/block mode before conditions and submits the selected draft mode", async () => {
  render();
  const mode = [...host.querySelectorAll<HTMLButtonElement>('button[aria-haspopup="listbox"]')].find((node) =>
    node.textContent?.includes("rework.platformAccess.rule.modeLabel.allow"),
  )!;
  expect(mode).toBeDefined();
  expect(mode.compareDocumentPosition(host.querySelector("fieldset")!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  act(() => mode.click());
  act(() =>
    [...document.querySelectorAll<HTMLElement>('[role="option"]')]
      .find((node) => node.textContent?.trim() === "rework.platformAccess.rule.modeLabel.block")!
      .click(),
  );
  expect(hooks.save).not.toHaveBeenCalled();
  await act(async () => button("test").click());
  expect(hooks.preview.mock.calls[0][0].platformAccessPolicy.mode).toBe("block");
  expect(host.querySelector('[data-outcome="allowed"] h3')?.textContent).toContain("rule.testAllowed");
});
it("shows an explicit readable refusal when preview denies effective admission", async () => {
  hooks.preview.mockReturnValue({ unwrap: async () => ({ matched: false, admitted: false, conditions: ["missing"] }) });
  render();
  await act(async () => button("test").click());
  expect(host.querySelector('[data-outcome="denied"] h3')?.textContent).toContain("rule.testDenied");
  expect(host.textContent).toContain("rule.ruleDoesNotMatch");
});

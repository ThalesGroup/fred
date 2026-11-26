// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { beforeEach, afterEach, it, expect, vi } from "vitest";
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const h = vi.hoisted(() => ({
  data: {
    configured_seconds: null as number | null,
    inherited_seconds: 90,
    inherited_from_team: false,
    effective_seconds: 60,
    organization_ceiling_seconds: 60,
  },
  save: vi.fn(),
  refetch: vi.fn(),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string, values?: object) => `${key}${values ? JSON.stringify(values) : ""}` }),
}));
vi.mock("../../../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useTeamConversationRetentionQuery: () => ({ currentData: h.data, refetch: h.refetch }),
  useReplaceTeamConversationRetentionMutation: () => [h.save, { isLoading: false }],
}));
vi.mock("@shared/molecules/Select/Select", () => ({
  default: ({
    value,
    onChange,
    disabled,
    options,
  }: {
    value: string;
    onChange: (value: string) => void;
    disabled: boolean;
    options: { value: string; label: string }[];
  }) => (
    <select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));
import TeamConversationRetention from "./TeamConversationRetention";
let root: Root;
let container: HTMLDivElement;
beforeEach(() => {
  vi.clearAllMocks();
  h.data = {
    configured_seconds: null,
    inherited_seconds: 90,
    inherited_from_team: false,
    effective_seconds: 60,
    organization_ceiling_seconds: 60,
  };
  h.save.mockImplementation(({ replaceConversationRetention }) => ({
    unwrap: async () => {
      h.data = { ...h.data, configured_seconds: replaceConversationRetention.configured_seconds };
    },
  }));
  h.refetch.mockReturnValue({ unwrap: async () => h.data });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});
const render = async (allowed = true) => {
  await act(async () => root.render(<TeamConversationRetention spaceId="team" allowed={allowed} />));
};
const mode = async (value: string) => {
  await act(async () => {
    const select = container.querySelector("select")!;
    select.value = value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
};
const seconds = async (value: string) => {
  await act(async () => {
    const input = container.querySelector("input")!;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
};
const button = () => container.querySelector("button")!;
it("shows effective ceiling and saves immediate as zero, then inheritance as null", async () => {
  await render();
  expect(container.textContent).toContain('effective{"seconds":60}');
  await mode("immediate");
  await act(async () => button().click());
  expect(h.save).toHaveBeenLastCalledWith({ id: "team", replaceConversationRetention: { configured_seconds: 0 } });
  await mode("inherit");
  await act(async () => button().click());
  expect(h.save).toHaveBeenLastCalledWith({ id: "team", replaceConversationRetention: { configured_seconds: null } });
});
it("rejects nonpositive, fractional and above-ceiling explicit durations", async () => {
  await render();
  await mode("duration");
  for (const value of ["", "0", "-1", "1.5", "61"]) {
    await seconds(value);
    expect(button().disabled).toBe(true);
  }
  await seconds("30");
  expect(button().disabled).toBe(false);
  await act(async () => button().click());
  expect(h.save).toHaveBeenCalledWith({ id: "team", replaceConversationRetention: { configured_seconds: 30 } });
});
it("keeps the draft when save fails and shows failure", async () => {
  h.save.mockReturnValue({
    unwrap: async () => {
      throw new Error("failed");
    },
  });
  await render();
  await mode("duration");
  await seconds("25");
  await act(async () => button().click());
  expect(container.querySelector("input")!.value).toBe("25");
  expect(container.textContent).toContain("teamRetention.failed");
});
it("disables writes when Manage is unavailable", async () => {
  await render(false);
  expect(container.querySelector("select")!.disabled).toBe(true);
  expect(button().disabled).toBe(true);
  expect(h.save).not.toHaveBeenCalled();
});
it("preserves a pending draft across a background policy refresh", async () => {
  await render();
  await mode("duration");
  await seconds("25");
  h.data = { ...h.data, configured_seconds: 10, effective_seconds: 10 };
  await render();
  expect(container.querySelector("input")!.value).toBe("25");
});
it("names the team delay a project follows when it has no value of its own", async () => {
  await render();
  expect(container.textContent).toContain("teamRetention.inherit");
  expect(container.textContent).not.toContain("inheritTeam");
  h.data = { ...h.data, inherited_seconds: 45, inherited_from_team: true, effective_seconds: 45 };
  await render();
  expect(container.textContent).toContain('teamRetention.inheritTeam{"seconds":45}');
});

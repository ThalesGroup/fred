// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ModelOfferKey, SpaceModels } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import { modelChoiceKey } from "@rework/features/capabilities/modelChoice";
import { RecommendedModelField } from "./RecommendedModelField";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const h = vi.hoisted(() => ({ data: undefined as SpaceModels | undefined, error: false }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useSpaceModelsQuery: () => ({ currentData: h.data, isError: h.error, isFetching: false }),
}));
vi.mock("@shared/molecules/Select/Select", () => ({
  default: ({
    options,
    value,
    onChange,
  }: {
    options: { value: string; label: string; disabled?: boolean }[];
    value: string;
    onChange: (value: string) => void;
  }) => (
    <div data-selected={value}>
      {options.map((option) => (
        <button
          key={option.value}
          data-value={option.value}
          disabled={option.disabled}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  ),
}));
const key = (model: string): ModelOfferKey => ({ source_id: "source", upstream_model_id: model });
let root: Root;
let container: HTMLDivElement;
const onChange = vi.fn();
beforeEach(() => {
  container = document.createElement("div");
  root = createRoot(container);
  h.error = false;
  h.data = {
    policy: { revision: 0, default: null, disabled: [], reasoning_default_on: [] },
    inherited_default: key("available"),
    parent_permitted: [key("available")],
    models: {
      default: key("available"),
      policy: {
        organization_id: "org",
        revision: 1,
        permitted: [key("available")],
        reasoning_enabled: [],
        embedding_locked: false,
        default: key("available"),
      },
      options: {},
      reasoning_default_on: [],
      offers: ["available", "forbidden"].map((model) => ({
        key: key(model),
        selectable: model === "available",
        candidate: model === "available",
        permitted: model === "available",
        diagnostics: [],
      })),
    },
  };
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  onChange.mockClear();
});
function render(value: ModelOfferKey | null) {
  act(() => root.render(<RecommendedModelField teamId="team" value={value} onChange={onChange} />));
}
it("offers only selectable models and sends canonical keys or an explicit null", () => {
  render(null);
  const buttons = container.querySelectorAll("button");
  expect(buttons).toHaveLength(2);
  act(() => buttons[1].click());
  expect(onChange).toHaveBeenLastCalledWith(key("available"));
  act(() => buttons[0].click());
  expect(onChange).toHaveBeenLastCalledWith(null);
});
it("retains a forbidden recommendation visibly until the editor changes it", () => {
  render(key("forbidden"));
  expect(container.querySelector("[data-selected]")?.getAttribute("data-selected")).toBe(
    modelChoiceKey(key("forbidden")),
  );
  expect(container.querySelectorAll("button")[2].disabled).toBe(true);
  expect(onChange).not.toHaveBeenCalled();
});
it("keeps an explicit model pinned even when it equals the default", () => {
  render(key("available"));
  expect(container.querySelector("[data-selected]")?.getAttribute("data-selected")).toBe(
    modelChoiceKey(key("available")),
  );
  expect(onChange).not.toHaveBeenCalled();
});
it("does not clear a recommendation when the catalogue cannot be read", () => {
  h.error = true;
  render(key("available"));
  expect(container.textContent).toContain("recommendedModel.loadError");
  expect(onChange).not.toHaveBeenCalled();
});

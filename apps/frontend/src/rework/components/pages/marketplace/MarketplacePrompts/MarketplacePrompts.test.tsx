// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { promptSummaryFixture } from "../../PromptsPage/weaverPromptFixtures";

const state = vi.hoisted(() => ({
  failed: false,
  canPublish: true,
  read: vi.fn(),
  publish: vi.fn(),
  navigate: vi.fn(),
  confirmation: undefined as undefined | (() => unknown),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }) }));
vi.mock("react-router-dom", () => ({ useNavigate: () => state.navigate }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: vi.fn(), showSuccess: vi.fn() }),
}));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({
    showConfirmationDialog: ({ onConfirm }) => {
      state.confirmation = onConfirm;
    },
  }),
}));
// Native select exercises the consumer's mapping and selection, not the design system's popover.
vi.mock("@shared/molecules/Select/Select", () => ({
  default: ({ options, onChange, value, label }) => (
    <select aria-label={label} value={value ?? ""} onChange={(event) => onChange(event.target.value)}>
      {options.map((option) => (
        <option key={option.key} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));
vi.mock("../../PromptsPage/PromptViewDialog/PromptViewDialog", () => ({ default: () => null }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMarketplacesQuery: () => ({
    currentData: {
      items: [
        { space_id: "org-a", name: "Organization A" },
        { space_id: "org-b", name: "Organization B" },
      ],
      next_cursor: null,
    },
    refetch: vi.fn(),
  }),
  usePromptPublicationSpacesQuery: () => ({
    currentData: { items: [{ id: "personal", name: "My library", marketplace_space_ids: ["org-a"] }] },
    refetch: vi.fn(),
  }),
  usePublishedPromptsQuery: (args) => {
    state.read(args);
    return {
      currentData: {
        items: [
          {
            ...promptSummaryFixture({ space_id: "personal", published_in: [args.marketplaceSpaceId] }),
            source_space_name: "Personal library",
            can_publish: state.canPublish,
          },
        ],
      },
      isError: state.failed,
      refetch: vi.fn(),
    };
  },
  useSetPromptPublicationMutation: () => [state.publish],
}));
import MarketplacePrompts from "./MarketplacePrompts";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let node: HTMLDivElement;
let root: ReturnType<typeof createRoot>;
const render = () => act(async () => root.render(<MarketplacePrompts />));
beforeEach(async () => {
  vi.clearAllMocks();
  state.failed = false;
  state.canPublish = true;
  state.confirmation = undefined;
  state.publish.mockReturnValue({ unwrap: async () => undefined });
  node = document.createElement("div");
  document.body.append(node);
  root = createRoot(node);
  await render();
});
afterEach(async () => {
  await act(async () => root.unmount());
  node.remove();
});

it("uses the selected marketplace space and offers only its publishing libraries", async () => {
  expect(state.read).toHaveBeenLastCalledWith({ marketplaceSpaceId: "org-a" });
  expect(node.textContent).toContain("Personal library");
  expect(node.querySelector('[aria-label="rework.promptPublication.libraries"]')).not.toBeNull();
  const select = node.querySelector<HTMLSelectElement>('[aria-label="rework.promptPublication.marketplace"]')!;
  await act(async () => {
    select.value = "org-b";
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(state.read).toHaveBeenLastCalledWith({ marketplaceSpaceId: "org-b" });
  expect(node.querySelector('[aria-label="rework.promptPublication.libraries"]')).toBeNull();
});

it("retracts only the selected publication after confirmation", async () => {
  const more = Array.from(node.querySelectorAll("button")).find((button) => button.textContent?.includes("more_vert"));
  expect(more).toBeTruthy();
  await act(async () => more!.click());
  const remove = Array.from(document.querySelectorAll("li")).find((item) =>
    item.textContent?.includes("removeFromMarketplace"),
  );
  expect(remove).toBeTruthy();
  await act(async () => remove!.click());
  expect(state.publish).not.toHaveBeenCalled();
  await act(async () => state.confirmation?.());
  expect(state.publish).toHaveBeenCalledExactlyOnceWith({
    spaceId: "personal",
    promptId: "prompt-1",
    marketplaceSpaceId: "org-a",
    promptPublicationRequest: { published: false },
  });
});

it("does not expose cached publications after a denied catalogue refresh", async () => {
  state.failed = true;
  await render();
  expect(node.textContent).not.toContain("Personal library");
  expect(node.textContent).toContain("rework.manager.unavailable");
});

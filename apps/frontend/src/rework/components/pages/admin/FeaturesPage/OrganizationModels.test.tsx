// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { OrganizationModels } from "./OrganizationModels";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const h = vi.hoisted(() => ({
  title: null as null | { source_id: string; upstream_model_id: string },
  locked: false,
  save: vi.fn(() => ({ unwrap: () => Promise.resolve() })),
  error: vi.fn(),
  refetch: vi.fn(),
  refresh: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError: h.error, showSuccess: vi.fn() }),
}));
vi.mock("@shared/molecules/DataTable/LocalizedDataTable.tsx", () => ({ default: () => null }));
vi.mock("@shared/molecules/InlineDrawer/InlineDrawer.tsx", () => ({
  InlineDrawer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock("@shared/molecules/Select/Select.tsx", () => ({
  default: ({
    label,
    value,
    options,
    onChange,
    disabled,
  }: {
    label: string;
    value: string;
    disabled: boolean;
    onChange: (value: string) => void;
    options: { key: string; value: string; label: string; disabled?: boolean }[];
  }) => (
    <select aria-label={label} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => (
        <option key={o.key} value={o.value} disabled={o.disabled}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useOrganizationModelsQuery: () => ({
    currentData: {
      policy: {
        revision: 4,
        permitted: ["chat", "withdrawn", "embed", "ranker"].map((upstream_model_id) => ({
          source_id: "a",
          upstream_model_id,
        })),
        reasoning_enabled: [],
        default: null,
        fallback: null,
        title: h.title,
        embedding: h.locked ? { source_id: "a", upstream_model_id: "embed" } : null,
        embedding_locked: h.locked,
        vision: null,
        reranker: null,
      },
      sources: [
        {
          observation: { enabled: false },
          offers: ["chat", "withdrawn", "not-permitted", "embed", "ranker"].map((id) => ({
            source_id: "a",
            upstream_model_id: id,
            selectable: id !== "withdrawn",
            advertised: true,
            metadata:
              id === "embed"
                ? { chat: false, embedding: true }
                : id === "ranker"
                  ? { chat: false, rerank: true }
                  : { chat: true, vision: id === "chat" ? null : false },
          })),
        },
      ],
    },
    isFetching: false,
    isError: false,
    refetch: h.refetch,
  }),
  useRefreshModelSourceMutation: () => [h.refresh],
  useReplaceOrganizationModelPolicyMutation: () => [h.save, { isLoading: false }],
}));
let root: Root;
let container: HTMLDivElement;
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.clearAllMocks();
  h.title = null;
  h.locked = false;
});
it("uses the server choices, restores the saved title choice and reports conflicts", async () => {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  const render = () => root.render(<OrganizationModels organizationId="org" defaultsOpen onCloseDefaults={() => {}} />);
  await act(async () => render());
  const title = () => container.querySelector<HTMLSelectElement>('select[aria-label$=".title"]')!;
  expect([...title().options].map((o) => o.text)).toEqual([
    "rework.admin.capabilities.organizationModels.none",
    "a / chat",
    "a / withdrawn",
  ]);
  expect(title().options[2].disabled).toBe(true);
  await act(async () => {
    title().selectedIndex = 1;
    title().dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(h.save).toHaveBeenCalledWith({
    organizationId: "org",
    replaceModelPolicy: expect.objectContaining({
      expected_revision: 4,
      title: { source_id: "a", upstream_model_id: "chat" },
    }),
  });
  h.title = { source_id: "a", upstream_model_id: "chat" };
  await act(async () => render());
  expect(title().selectedIndex).toBe(1);
  h.save.mockReturnValueOnce({ unwrap: () => Promise.reject({ status: 409, data: { detail: "Reload policy" } }) });
  await act(async () => {
    title().selectedIndex = 0;
    title().dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(h.error).toHaveBeenCalledWith(
    expect.objectContaining({ summary: "rework.admin.capabilities.organizationModels.saveError" }),
  );
});
it("offers each document choice only its aptitude and keeps the corpus model locked", async () => {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  const render = () => root.render(<OrganizationModels organizationId="org" defaultsOpen onCloseDefaults={() => {}} />);
  await act(async () => render());
  const select = (field: string) => container.querySelector<HTMLSelectElement>(`select[aria-label$=".${field}"]`)!;
  const labels = (field: string) => [...select(field).options].map((o) => o.text);
  const none = "rework.admin.capabilities.organizationModels.none";
  expect(labels("default")).toEqual([none, "a / chat", "a / withdrawn"]);
  expect(labels("embedding")).toEqual([none, "a / embed"]);
  // Unknown image input is offered; a source-reported refusal is not.
  expect(labels("vision")).toEqual([none, "a / chat"]);
  expect(labels("reranker")).toEqual([none, "a / ranker"]);
  await act(async () => {
    select("embedding").selectedIndex = 1;
    select("embedding").dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(h.save).toHaveBeenCalledWith({
    organizationId: "org",
    replaceModelPolicy: expect.objectContaining({
      embedding: { source_id: "a", upstream_model_id: "embed" },
      vision: null,
      reranker: null,
    }),
  });
  await act(async () => {
    select("reranker").selectedIndex = 1;
    select("reranker").dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(h.save).toHaveBeenCalledWith({
    organizationId: "org",
    replaceModelPolicy: expect.objectContaining({ reranker: { source_id: "a", upstream_model_id: "ranker" } }),
  });
  h.locked = true;
  await act(async () => render());
  expect(select("embedding").disabled).toBe(true);
  expect(container.textContent).toContain("rework.admin.capabilities.organizationModels.embeddingLockedHint");
});

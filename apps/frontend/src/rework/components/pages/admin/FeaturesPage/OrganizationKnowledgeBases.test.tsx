// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { beforeEach, afterEach, expect, it, vi } from "vitest";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const probe = vi.hoisted(() => ({
  services: [] as Record<string, unknown>[],
  inventory: [] as Record<string, unknown>[],
  failed: false,
  register: vi.fn(() => ({ unwrap: async () => ({}) })),
  authorize: vi.fn(() => ({ unwrap: async () => ({}) })),
  read: vi.fn(),
  confirm: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: vi.fn() }) }));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: probe.confirm }),
}));
vi.mock("@shared/molecules/Dialog/Dialog", () => ({
  Dialog: ({
    children,
    onConfirm,
    confirmDisabled,
  }: {
    children: React.ReactNode;
    onConfirm: () => void;
    confirmDisabled: boolean;
  }) => (
    <div>
      {children}
      <button disabled={confirmDisabled} onClick={onConfirm}>
        save
      </button>
    </div>
  ),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useOrganizationKnowledgeBaseServicesQuery: (args: unknown) => {
    probe.read(args);
    return { currentData: probe.services, isError: probe.failed, refetch: vi.fn() };
  },
  useOrganizationCapabilitiesQuery: () => ({ currentData: probe.inventory, isError: false, refetch: vi.fn() }),
  useRegisterKnowledgeBaseServiceMutation: () => [probe.register, { isLoading: false }],
  useUpdateKnowledgeBaseServiceMutation: () => [vi.fn(), { isLoading: false }],
  useSetOrganizationCapabilityDefaultMutation: () => [probe.authorize, { isLoading: false }],
}));
import OrganizationKnowledgeBases from "./OrganizationKnowledgeBases";
let container: HTMLDivElement;
let root: Root;
beforeEach(() => {
  vi.clearAllMocks();
  probe.services = [];
  probe.inventory = [];
  probe.failed = false;
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});
async function render() {
  await act(async () => root.render(<OrganizationKnowledgeBases organizationId="acme" />));
}
it("reads only the selected organization and distinguishes error from empty", async () => {
  await render();
  expect(probe.read).toHaveBeenCalledWith({ organizationId: "acme" });
  expect(container.textContent).toContain("emptyKnowledgeBases");
  probe.failed = true;
  await render();
  expect(container.querySelector('[role="alert"]')).not.toBeNull();
  expect(container.textContent).not.toContain("emptyKnowledgeBases");
});
it("registers an identity and credential names without authorizing its offers", async () => {
  await render();
  await act(async () =>
    [...container.querySelectorAll("button")]
      .find((button) => button.textContent?.endsWith("registry.create"))!
      .click(),
  );
  const inputs = [...container.querySelectorAll("input")];
  const values = [
    "acme-webdav",
    "https://identity.example/realms/app",
    "acme-kb-worker",
    "app",
    "wiki-password, archive-password",
  ];
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
  await act(async () =>
    inputs.forEach((input, i) => {
      setter.call(input, values[i]);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }),
  );
  await act(async () =>
    [...container.querySelectorAll("button")].find((button) => button.textContent === "save")!.click(),
  );
  expect(probe.register).toHaveBeenCalledWith({
    organizationId: "acme",
    registerKnowledgeBaseService: {
      runtime_id: "acme-webdav",
      issuer: "https://identity.example/realms/app",
      client_id: "acme-kb-worker",
      audience: "app",
      credential_bindings: ["wiki-password", "archive-password"],
    },
  });
  expect(probe.authorize).not.toHaveBeenCalled();
});
it("waits for publication and changes the existing organization policy", async () => {
  probe.services = [{ runtime_id: "acme-webdav", credential_bindings: [] }];
  await render();
  expect(container.textContent).toContain("awaitingPublication");
  probe.inventory = [
    {
      source_id: "acme-webdav",
      origin: "knowledge_base",
      capabilities: [
        {
          source_id: "acme-webdav",
          capability_id: "knowledge-base:registered-id",
          advertised: true,
          default_on: false,
          descriptor: { name: "WebDAV", description: "A mirror" },
        },
      ],
    },
  ];
  await render();
  await act(async () => container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click());
  expect(probe.authorize).toHaveBeenCalledWith({
    organizationId: "acme",
    sourceId: "acme-webdav",
    capabilityId: "knowledge-base:registered-id",
    setDefaultOnRequest: { default_on: true },
  });
  probe.inventory[0] = {
    ...probe.inventory[0],
    capabilities: [
      {
        source_id: "acme-webdav",
        capability_id: "knowledge-base:registered-id",
        advertised: true,
        default_on: true,
        descriptor: { name: "WebDAV" },
      },
    ],
  };
  await render();
  await act(async () => container.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click());
  expect(probe.confirm).toHaveBeenCalled();
  expect(probe.authorize).toHaveBeenCalledTimes(1);
});

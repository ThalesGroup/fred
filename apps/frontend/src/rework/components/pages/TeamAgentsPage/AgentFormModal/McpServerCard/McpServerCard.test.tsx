import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ManagedMcpServerRef } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import { CHAT_OPTION_FIELD_KEYS } from "../chatOptionsConfig";
import { McpServerCard } from "./McpServerCard";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (value: string) => value,
  }),
}));

vi.mock("@shared/atoms/Switch/Switch.tsx", () => ({
  default: ({ checked, disabled }: { checked: boolean; disabled: boolean }) => (
    <div data-switch={checked ? "on" : "off"} data-disabled={disabled ? "true" : "false"} />
  ),
}));

vi.mock("@shared/atoms/ButtonGroup/ButtonGroup.tsx", () => ({
  default: () => <div>button-group</div>,
}));

vi.mock("@components/pages/TeamAgentsPage/AgentCreateEditModal/SwitchRow/SwitchRow.tsx", () => ({
  SwitchRow: ({ label, description }: { label: string; description?: string }) => (
    <div>
      <span>{label}</span>
      {description ? <span>{description}</span> : null}
    </div>
  ),
}));

vi.mock(
  "@components/pages/TeamAgentsPage/AgentCreateEditModal/DocumentLibraryScopePicker/DocumentLibraryScopePicker",
  () => ({
    DocumentLibraryScopePicker: () => <div>document-library-scope-picker</div>,
  }),
);

function makeServer(keys: string[]): ManagedMcpServerRef {
  return {
    id: "mcp-knowledge-flow-mcp-text",
    display_name: "Knowledge Flow",
    require_tools: [],
    config_fields: keys.map((key) => ({
      key,
      title: key,
      description: `${key}.description`,
      type: "boolean",
      required: false,
    })),
  } as ManagedMcpServerRef;
}

function renderCard(server: ManagedMcpServerRef, configValues: Record<string, unknown> = {}): string {
  return renderToStaticMarkup(
    <McpServerCard
      server={server}
      checked={true}
      disabled={false}
      configValues={configValues}
      tuningValues={{}}
      onToggle={() => undefined}
      onConfigChange={() => undefined}
      onTuningChange={() => undefined}
    />,
  );
}

describe("McpServerCard", () => {
  it("does not render the binding switch when only libraries_selection is declared", () => {
    const html = renderCard(makeServer([CHAT_OPTION_FIELD_KEYS.librariesSelection]));

    expect(html).not.toContain("agentTuning.fields.library_binding.title");
  });

  it("renders the binding switch when libraries_binding is declared", () => {
    const html = renderCard(makeServer([CHAT_OPTION_FIELD_KEYS.librariesBinding]));

    expect(html).toContain("agentTuning.fields.library_binding.title");
  });

  it("does not render the bound library picker when bound_library_ids is undeclared", () => {
    const html = renderCard(makeServer([CHAT_OPTION_FIELD_KEYS.librariesBinding]), {
      [CHAT_OPTION_FIELD_KEYS.librariesBinding]: true,
    });

    expect(html).not.toContain("document-library-scope-picker");
  });
});

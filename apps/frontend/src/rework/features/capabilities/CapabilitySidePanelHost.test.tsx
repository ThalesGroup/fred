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

// The launcher rail: what the user sees before opening anything. A session can
// activate several document-producing capabilities from the start, so a launcher
// that appears on declaration alone points at an empty panel - the plugin's
// `useHasContent` is what turns it on, and its glyph is what tells two of them
// apart.

import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CapabilitySidePanelHost } from "./CapabilitySidePanelHost";
import type { CapabilitySidePanelProps } from "./types";

const state = vi.hoisted(() => ({ entries: [] as unknown[] }));

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

vi.mock("./sessionProbeRegistry", () => ({ sessionProbesForCapabilities: () => [] }));

vi.mock("./sidePanelRegistry", () => ({ sidePanelsForCapabilities: () => state.entries }));

vi.mock("@shared/atoms/IconButton/IconButton", () => ({
  default: ({ icon, ...rest }: { icon: { type: string }; "aria-label": string }) => (
    <button data-icon={icon.type} aria-label={rest["aria-label"]} />
  ),
}));

vi.mock("@shared/molecules/InlineDrawer/InlineDrawer", () => ({
  InlineDrawer: ({ open, children }: { open: boolean; children: React.ReactNode }) =>
    open ? <div data-drawer>{children}</div> : null,
}));

function StubPanel(_props: CapabilitySidePanelProps) {
  return <div data-panel />;
}

const entry = (capabilityId: string, icon: string, useHasContent?: () => boolean) => ({
  capabilityId,
  widget: `${capabilityId}_pane`,
  Component: StubPanel,
  icon,
  useHasContent,
});

const render = (activeKey: string | null = null) =>
  renderToStaticMarkup(
    <CapabilitySidePanelHost
      capabilityIds={["ppt_filler"]}
      activeKey={activeKey}
      onActiveKeyChange={() => undefined}
    />,
  );

describe("CapabilitySidePanelHost launcher rail", () => {
  beforeEach(() => {
    state.entries = [];
  });

  it("offers no launcher while the panel has nothing to show", () => {
    state.entries = [entry("ppt_filler", "slideshow", () => false)];
    expect(render()).not.toContain("<button");
  });

  it("offers the launcher once the panel has content", () => {
    state.entries = [entry("ppt_filler", "slideshow", () => true)];
    expect(render()).toContain('data-icon="slideshow"');
  });

  it("offers a panel that declares no visibility hook unconditionally", () => {
    state.entries = [entry("demo_echo", "forum")];
    expect(render()).toContain('data-icon="forum"');
  });

  it("gives each panel its own glyph", () => {
    state.entries = [
      entry("ppt_filler", "slideshow", () => true),
      entry("writable_document", "edit_document", () => true),
    ];
    const html = render();

    expect(html).toContain('data-icon="slideshow"');
    expect(html).toContain('data-icon="edit_document"');
  });

  it("retires the whole rail while a panel is open, other panels included", () => {
    // It floats over the right edge of the slot, drawer included, so it would land
    // on the drawer's own close button. Closing the open panel brings it back.
    state.entries = [
      entry("ppt_filler", "slideshow", () => true),
      entry("writable_document", "edit_document", () => true),
    ];

    expect(render("writable_document:writable_document_pane")).not.toContain("<button");
  });
});

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
  InlineDrawer: ({
    open,
    headerActions,
    children,
  }: {
    open: boolean;
    headerActions?: React.ReactNode;
    children: React.ReactNode;
  }) =>
    open ? (
      <div data-drawer>
        <header>{headerActions}</header>
        {children}
      </div>
    ) : null,
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
    state.entries = [entry("ppt_filler", "slideshow", () => true), entry("writable_document", "article", () => true)];
    const html = render();

    expect(html).toContain('data-icon="slideshow"');
    expect(html).toContain('data-icon="article"');
  });

  it("hides a launcher while its own panel is open", () => {
    state.entries = [entry("ppt_filler", "slideshow", () => true)];
    expect(render("ppt_filler:ppt_filler_pane")).not.toContain("<button");
  });

  it("moves the other launchers into the open drawer's header, off the rail", () => {
    state.entries = [entry("ppt_filler", "slideshow", () => true), entry("writable_document", "article", () => true)];
    const html = render("writable_document:writable_document_pane");

    // In the drawer header, and ONLY there - the rail would float on the drawer's
    // own close button. (CSS-module class names are hashed, so count the buttons.)
    expect(html).toContain('<header><button data-icon="slideshow"');
    expect(html.match(/<button/g)).toHaveLength(1);
  });
});

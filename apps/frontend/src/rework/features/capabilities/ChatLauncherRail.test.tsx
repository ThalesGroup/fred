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
import { ChatLauncherRail, type ChatLauncher } from "./ChatLauncherRail";

const state = vi.hoisted(() => ({ entries: [] as unknown[] }));

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

vi.mock("./sessionProbeRegistry", () => ({ sessionProbesForCapabilities: () => [] }));

vi.mock("./sidePanelRegistry", () => ({ sidePanelsForCapabilities: () => state.entries }));

// Stubbed down to what the rail actually decides: which glyph, which label, and
// what count it hands the badge. The badge's own rendering rules are
// IconButton's, and are tested there.
vi.mock("@shared/atoms/IconButton/IconButton", () => ({
  default: ({ icon, badgeCount, ...rest }: { icon: { type: string }; badgeCount?: number; "aria-label": string }) => (
    <button data-icon={icon.type} aria-label={rest["aria-label"]} data-badge={badgeCount} />
  ),
}));

function StubPanel() {
  return <div data-panel />;
}

const entry = (capabilityId: string, icon: string, useHasContent?: () => boolean) => ({
  capabilityId,
  widget: `${capabilityId}_pane`,
  Component: StubPanel,
  icon,
  useHasContent,
  ownsHeader: false,
});

const render = (activeKey: string | null = null, launchers?: ChatLauncher[]) =>
  renderToStaticMarkup(
    <ChatLauncherRail
      capabilityIds={["ppt_filler"]}
      activeKey={activeKey}
      onActiveKeyChange={() => undefined}
      launchers={launchers}
    />,
  );

const attachmentsLauncher = (badgeCount?: number): ChatLauncher => ({
  key: "attachments",
  label: "Attachments",
  icon: "attach_file",
  badgeCount,
  onOpen: () => undefined,
});

describe("ChatLauncherRail", () => {
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

  it("renders a first-party launcher with no capability contributing a panel", () => {
    // The attachments button must reach an otherwise bare chat.
    const html = render(null, [attachmentsLauncher()]);

    expect(html).toContain('data-icon="attach_file"');
  });

  it("puts first-party launchers above the capability ones", () => {
    state.entries = [entry("ppt_filler", "slideshow", () => true)];
    const html = render(null, [attachmentsLauncher()]);

    expect(html.indexOf('data-icon="attach_file"')).toBeLessThan(html.indexOf('data-icon="slideshow"'));
  });

  it("hands the launcher's count to the button's badge", () => {
    // Whether a count actually paints a badge is IconButton's rule, tested there.
    expect(render(null, [attachmentsLauncher(3)])).toContain('data-badge="3"');
    expect(render(null, [attachmentsLauncher()])).not.toContain("data-badge");
  });

  it("retires the whole rail while a panel is open, other panels included", () => {
    // Opening one panel closes the rail entirely; the body-side push drawer takes
    // over. Reaching another launcher means closing the open panel first.
    state.entries = [
      entry("ppt_filler", "slideshow", () => true),
      entry("writable_document", "edit_document", () => true),
    ];

    expect(render("writable_document:writable_document_pane")).not.toContain("<button");
  });
});

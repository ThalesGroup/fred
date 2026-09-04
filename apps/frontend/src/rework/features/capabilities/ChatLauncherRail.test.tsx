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

const state = vi.hoisted(() => ({ entries: [] as unknown[], clicks: [] as Array<() => void> }));

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

vi.mock("./sessionProbeRegistry", () => ({ sessionProbesForCapabilities: () => [] }));

vi.mock("./sidePanelRegistry", () => ({ sidePanelsForCapabilities: () => state.entries }));

// Stubbed down to what the rail actually decides: which glyph, which label,
// what count it hands the badge, whether the button reads as selected, and what
// its click does. The badge's own rendering rules are IconButton's, tested
// there. Click handlers are recorded because renderToStaticMarkup never fires
// them.
vi.mock("@shared/atoms/IconButton/IconButton", () => ({
  default: ({
    icon,
    badgeCount,
    onClick,
    ...rest
  }: {
    icon: { type: string };
    badgeCount?: number;
    onClick?: () => void;
    "aria-pressed"?: boolean;
    "aria-label": string;
  }) => {
    if (onClick) state.clicks.push(onClick);
    return (
      <button
        data-icon={icon.type}
        aria-label={rest["aria-label"]}
        aria-pressed={rest["aria-pressed"]}
        data-badge={badgeCount}
      />
    );
  },
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

const render = (activeKey: string | null = null, launchers?: ChatLauncher[], footerLaunchers?: ChatLauncher[]) =>
  renderToStaticMarkup(
    <ChatLauncherRail
      capabilityIds={["ppt_filler"]}
      activeKey={activeKey}
      onActiveKeyChange={() => undefined}
      launchers={launchers}
      footerLaunchers={footerLaunchers}
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
    // Handlers accumulate across renders; without this a test would click a
    // button from the previous one.
    state.clicks.length = 0;
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

  it("renders footer launchers after the rest, in their own group", () => {
    // The group carries `margin-top: auto`, which is what puts admin tooling at
    // the rail's foot however many launchers sit above it.
    state.entries = [entry("ppt_filler", "slideshow", () => true)];
    const html = render(null, [attachmentsLauncher()], [{ ...attachmentsLauncher(), key: "debug", icon: "build" }]);

    expect(html.indexOf('data-icon="slideshow"')).toBeLessThan(html.indexOf('data-icon="build"'));
    expect(html).toMatch(/_railFooter[^"]*"><span[^>]*><button data-icon="build"/);
  });

  it("renders a rail holding nothing but a footer launcher", () => {
    // A chat with no capability panel and no attachments still shows admin
    // tooling; the "nothing to show" guard must count the footer.
    const html = render(null, [], [{ ...attachmentsLauncher(), key: "debug", icon: "build" }]);

    expect(html).toContain('data-icon="build"');
  });

  it("keeps every launcher reachable while a panel is open", () => {
    // The rail owns its own in-flow column beside the viewer, so switching
    // viewers - or reaching the attachments - no longer means closing first.
    state.entries = [
      entry("ppt_filler", "slideshow", () => true),
      entry("writable_document", "edit_document", () => true),
    ];
    const html = render("writable_document:writable_document_pane", [attachmentsLauncher()]);

    expect(html).toContain('data-icon="slideshow"');
    expect(html).toContain('data-icon="edit_document"');
    expect(html).toContain('data-icon="attach_file"');
  });

  it("marks the open panel's launcher as selected, and only that one", () => {
    state.entries = [
      entry("ppt_filler", "slideshow", () => true),
      entry("writable_document", "edit_document", () => true),
    ];
    const html = render("writable_document:writable_document_pane");

    expect(html).toMatch(/data-icon="edit_document"[^>]*aria-pressed="true"/);
    expect(html).toMatch(/data-icon="slideshow"[^>]*aria-pressed="false"/);
  });

  it("closes the open panel when its own launcher is clicked again", () => {
    // The launcher is the way in and the way out; without this the open panel
    // could only be dismissed from its own header.
    const changes: (string | null)[] = [];
    state.entries = [entry("ppt_filler", "slideshow", () => true)];

    renderToStaticMarkup(
      <ChatLauncherRail
        capabilityIds={["ppt_filler"]}
        activeKey="ppt_filler:ppt_filler_pane"
        onActiveKeyChange={(key) => changes.push(key)}
      />,
    );
    state.clicks[0]();

    expect(changes).toEqual([null]);
  });
});

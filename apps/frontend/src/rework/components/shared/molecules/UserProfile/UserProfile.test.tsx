// @vitest-environment happy-dom
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

// What these pin: "What's new" appears only while there is a patch note to
// read, and opens the history on its first entry, whether or not an
// announcement is pending for the user.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

const queryMock = vi.fn();

vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePatchNoteHistoryQuery: () => queryMock(),
}));
vi.mock("../../../../../security/KeycloakService.ts", () => ({
  KeyCloakService: { GetUserFullName: () => "Alice", GetUserMail: () => "alice@example.com", CallLogout: vi.fn() },
}));
vi.mock("../../../../../hooks/useFrontendProperties.ts", () => ({ useFrontendProperties: () => ({}) }));
vi.mock("../../../../../hooks/useFrontendBootstrap.ts", () => ({ useFrontendBootstrap: () => ({ bootstrap: null }) }));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

import UserProfile from "./UserProfile";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement | null = null;
let root: Root | null = null;

const note = (id: string, title: string) => ({ id, title: { en: title }, description_long: { en: `# ${title}` } });

function mountWith(patchNotes: unknown[], pendingAnnouncementId: string | null = null) {
  queryMock.mockReturnValue({ data: { patch_notes: patchNotes, pending_announcement_id: pendingAnnouncementId } });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root!.render(<UserProfile />));
  act(() => container!.querySelector<HTMLButtonElement>("button[aria-haspopup]")!.click());
}

const whatsNew = () =>
  [...document.body.querySelectorAll("button")].find((b) => b.textContent?.includes("rework.profileMenu.whatsNew"));

afterEach(() => {
  act(() => root?.unmount());
  container?.remove();
  container = null;
  root = null;
  document.getElementById("modal-portal")?.remove();
});

describe("UserProfile What's new entry", () => {
  it("is hidden when no patch note is visible", () => {
    mountWith([]);

    expect(whatsNew()).toBeUndefined();
  });

  it("opens the history on its first entry, with nothing pending", () => {
    mountWith([note("p2", "Version 3.4"), note("p1", "Version 3.3")]);

    act(() => whatsNew()!.click());

    const dialog = document.body.querySelector('[role="dialog"]')!;
    expect(dialog.textContent).toContain("Version 3.4");
    expect(dialog.querySelector("nav")?.textContent).toContain("1 / 2");
    expect(dialog.querySelector('input[type="checkbox"]')).toBeNull();
  });
});

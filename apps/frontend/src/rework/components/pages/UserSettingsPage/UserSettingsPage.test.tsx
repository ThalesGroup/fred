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

// The theme picker lists only the themes the platform offers, and disappears
// when there is nothing to choose; the light/dark/system choice always stays.
// The profile picture card uploads the crop and deletes only after confirmation;
// a failed delete is reported to the user.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApplicationContext } from "../../../../app/ApplicationContextProvider.tsx";
import type { UiTheme } from "../../../../app/uiThemes.ts";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "fr", changeLanguage: vi.fn() } }),
}));

vi.mock("../../../../security/KeycloakService.ts", () => ({
  KeyCloakService: {
    GetUserFullName: () => "Ada Lovelace",
    GetUserName: () => "ada",
    GetUserMail: () => "ada@example.com",
    GetUserRoles: () => [],
    CallLogout: vi.fn(),
  },
}));

vi.mock("../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({ siteTitle: "Fred", siteSubtitle: "" }),
}));

vi.mock("@shared/molecules/Select/Select.tsx", () => ({
  default: ({ options, ariaLabel }: { options: { value: string }[]; ariaLabel: string }) => (
    <select aria-label={ariaLabel}>
      {options.map((o) => (
        <option key={o.value} value={o.value} />
      ))}
    </select>
  ),
}));

const picture = vi.hoisted(() => ({
  url: undefined as string | undefined,
  upload: vi.fn(),
  remove: vi.fn(),
  confirm: vi.fn(),
  notifyApiError: vi.fn(),
}));

vi.mock("@core/hooks/useApiErrorToast.ts", () => ({
  useApiErrorToast: () => ({ notifyApiError: picture.notifyApiError }),
}));

vi.mock("../../../../hooks/useFrontendBootstrap.ts", () => ({
  useFrontendBootstrap: () => ({ bootstrap: { current_user: { id: "u-1", avatar_image_url: picture.url } } }),
}));

vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements.ts", () => ({
  useUploadUserAvatarMutation: () => [
    (arg: unknown) => ({ unwrap: () => Promise.resolve(picture.upload(arg)) }),
    { isLoading: false },
  ],
  useDeleteUserAvatarMutation: () => [
    () => ({ unwrap: () => Promise.resolve().then(() => picture.remove()) }),
    { isLoading: false },
  ],
}));

vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: picture.confirm }),
}));

// The card's own file/crop behaviour is covered by AvatarUploadCard.test.tsx.
vi.mock("@shared/molecules/AvatarUploadCard/AvatarUploadCard.tsx", () => ({
  default: ({
    onUpload,
    onDelete,
    imageUrl,
  }: {
    onUpload: (file: File) => Promise<void>;
    onDelete?: () => void;
    imageUrl?: string;
  }) => (
    <div data-testid="picture-card" data-image={imageUrl ?? ""}>
      <button
        data-testid="picture-upload"
        onClick={() => onUpload(new File(["x"], "avatar.webp", { type: "image/webp" }))}
      />
      {onDelete && <button data-testid="picture-delete" onClick={onDelete} />}
    </div>
  ),
}));

import UserSettingsPage from "./UserSettingsPage";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;

function render(offeredUiThemes: UiTheme[]) {
  act(() =>
    root.render(
      <MemoryRouter>
        <ApplicationContext.Provider
          value={{
            isSidebarCollapsed: false,
            darkMode: false,
            themeMode: "system",
            uiTheme: offeredUiThemes[0],
            offeredUiThemes,
            toggleSidebar: () => undefined,
            setThemeMode: () => undefined,
            setUiTheme: () => undefined,
          }}
        >
          <UserSettingsPage />
        </ApplicationContext.Provider>
      </MemoryRouter>,
    ),
  );
}

const themePicker = () => container.querySelector('select[aria-label="rework.userSettings.app.uiThemeAria"]');
const modeGroup = () => container.querySelector('[aria-label="rework.userSettings.app.themeAria"]');

beforeEach(() => {
  picture.url = undefined;
  picture.upload.mockReset();
  picture.remove.mockReset();
  picture.confirm.mockReset();
  picture.notifyApiError.mockReset();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("UserSettingsPage theme picker", () => {
  it("lists only the offered themes", () => {
    render(["cobalt", "cloud"]);
    const values = Array.from(themePicker()!.querySelectorAll("option")).map((o) => o.getAttribute("value"));
    expect(values).toEqual(["cobalt", "cloud"]);
  });

  it("hides the picker when a single theme is offered but keeps the mode choice", () => {
    render(["cobalt"]);
    expect(themePicker()).toBeNull();
    expect(modeGroup()).not.toBeNull();
  });
});

describe("UserSettingsPage profile picture", () => {
  const click = (testId: string) =>
    act(async () => {
      (container.querySelector(`[data-testid="${testId}"]`) as HTMLButtonElement).click();
    });

  it("shows the current picture and sends the file the card hands over", async () => {
    picture.url = "https://objects.test/me.webp";
    render(["cobalt"]);
    expect(container.querySelector('[data-testid="picture-card"]')!.getAttribute("data-image")).toBe(
      "https://objects.test/me.webp",
    );

    await click("picture-upload");

    const arg = picture.upload.mock.calls[0][0] as {
      bodyUploadMyAvatarControlPlaneV1UsersMeAvatarPost: { file: File };
    };
    expect(arg.bodyUploadMyAvatarControlPlaneV1UsersMeAvatarPost.file.type).toBe("image/webp");
  });

  it("deletes the picture only once the confirmation is accepted", async () => {
    picture.url = "https://objects.test/me.webp";
    render(["cobalt"]);

    await click("picture-delete");

    expect(picture.remove).not.toHaveBeenCalled();
    const options = picture.confirm.mock.calls[0][0] as { criticalAction: boolean; onConfirm: () => void };
    expect(options.criticalAction).toBe(true);
    await act(async () => options.onConfirm());
    expect(picture.remove).toHaveBeenCalledTimes(1);
  });

  it("tells the user when the delete fails", async () => {
    picture.url = "https://objects.test/me.webp";
    picture.remove.mockImplementation(() => {
      throw { status: 500 };
    });
    render(["cobalt"]);

    await click("picture-delete");
    const options = picture.confirm.mock.calls[0][0] as { onConfirm: () => void };
    await act(async () => options.onConfirm());

    expect(picture.notifyApiError).toHaveBeenCalledWith(
      { status: 500 },
      expect.objectContaining({ summary: "rework.userSettings.picture.deleteFailed" }),
    );
  });

  it("keeps the picture when the confirmation is cancelled", async () => {
    picture.url = "https://objects.test/me.webp";
    render(["cobalt"]);

    await click("picture-delete");
    const options = picture.confirm.mock.calls[0][0] as { onCancel?: () => void };
    options.onCancel?.();

    expect(picture.remove).not.toHaveBeenCalled();
  });
});

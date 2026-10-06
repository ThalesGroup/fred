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

// Only JPEG/PNG/WebP up to 5 MB reach the crop editor; saving the crop hands
// the blob to `onUpload`; Delete shows only with `onDelete` and an image.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@shared/organisms/AvatarCropEditor/AvatarCropEditor.tsx", () => ({
  default: ({ file, onSave }: { file: File; onSave: (blob: Blob) => Promise<void> }) => (
    <div data-testid="crop-editor" data-file={file.name}>
      <button data-testid="crop-save" onClick={() => onSave(new Blob(["cropped"], { type: "image/webp" }))} />
    </div>
  ),
}));

import AvatarUploadCard from "./AvatarUploadCard";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

function render(props: Partial<Parameters<typeof AvatarUploadCard>[0]> = {}) {
  const onUpload = props.onUpload ?? vi.fn(() => Promise.resolve());
  act(() =>
    root.render(
      <AvatarUploadCard
        title="Picture"
        hint="hint"
        importLabel="Import"
        emptyLabel="Empty"
        deleteLabel="Delete"
        {...props}
        onUpload={onUpload}
      />,
    ),
  );
  return onUpload;
}

function pick(file: File) {
  const input = container.querySelector('[data-testid="avatar-upload-input"]') as HTMLInputElement;
  Object.defineProperty(input, "files", { value: [file], configurable: true });
  act(() => {
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
}

const cropEditor = () => container.querySelector('[data-testid="crop-editor"]');
// Button text also carries the icon ligature, so match on inclusion.
const deleteButton = () =>
  Array.from(container.querySelectorAll("button")).find((b) => b.textContent?.includes("Delete"));

describe("AvatarUploadCard", () => {
  it("rejects an unsupported file type", () => {
    render();
    pick(new File(["gif"], "me.gif", { type: "image/gif" }));
    expect(cropEditor()).toBeNull();
  });

  it("rejects a file over 5 MB", () => {
    render();
    pick(new File([new Uint8Array(5 * 1024 * 1024 + 1)], "big.png", { type: "image/png" }));
    expect(cropEditor()).toBeNull();
  });

  it("uploads the saved crop and closes the editor", async () => {
    const onUpload = render();
    pick(new File(["png"], "me.png", { type: "image/png" }));
    expect(cropEditor()?.getAttribute("data-file")).toBe("me.png");

    await act(async () => {
      (container.querySelector('[data-testid="crop-save"]') as HTMLButtonElement).click();
    });

    expect(onUpload).toHaveBeenCalledTimes(1);
    expect((onUpload as ReturnType<typeof vi.fn>).mock.calls[0][0]).toBeInstanceOf(Blob);
    expect(cropEditor()).toBeNull();
  });

  it("shows Delete only with a delete handler and an image", () => {
    render({ imageUrl: "https://objects.test/me.webp" });
    expect(deleteButton()).toBeUndefined();

    render({ onDelete: vi.fn() });
    expect(deleteButton()).toBeUndefined();
    expect(container.textContent).toContain("Empty");

    const onDelete = vi.fn();
    render({ onDelete, imageUrl: "https://objects.test/me.webp" });
    act(() => deleteButton()!.click());
    expect(onDelete).toHaveBeenCalledTimes(1);
  });
});

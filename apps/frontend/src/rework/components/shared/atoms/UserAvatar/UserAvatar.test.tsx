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

// A profile picture replaces the initials; without one, or when it fails to
// load, the initials come back - until a different URL is given.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import UserAvatar from "./UserAvatar";

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
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

const render = (imageUrl?: string) =>
  act(() => root.render(<UserAvatar name="Ada Lovelace" size="small" imageUrl={imageUrl} />));

describe("UserAvatar", () => {
  it("shows the picture instead of the initials", () => {
    render("https://objects.test/ada.webp");
    const img = container.querySelector("img");
    expect(img?.getAttribute("src")).toBe("https://objects.test/ada.webp");
    expect(img?.getAttribute("width")).toBe("32");
    expect(container.textContent).toBe("");
  });

  it("shows the initials without a picture", () => {
    render();
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toBe("AL");
  });

  it("falls back to the initials when the picture fails, and retries a new URL", () => {
    render("https://objects.test/broken.webp");
    act(() => {
      container.querySelector("img")!.dispatchEvent(new Event("error"));
    });
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toBe("AL");

    render("https://objects.test/new.webp");
    expect(container.querySelector("img")?.getAttribute("src")).toBe("https://objects.test/new.webp");
  });
});

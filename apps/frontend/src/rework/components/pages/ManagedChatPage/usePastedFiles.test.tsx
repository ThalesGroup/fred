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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePastedFiles } from "./usePastedFiles";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function Host({ enabled, onFiles }: { enabled: boolean; onFiles: (files: File[]) => void }) {
  usePastedFiles({ enabled, onFiles });
  return <textarea data-testid="composer" />;
}

// A paste event as the browser would dispatch it: on the focused element,
// bubbling up to the document, with the clipboard payload attached.
function paste(target: EventTarget, files: File[], text = ""): Event {
  const event = new Event("paste", { bubbles: true, cancelable: true });
  Object.defineProperty(event, "clipboardData", {
    value: { files, types: files.length ? ["Files"] : ["text/plain"], getData: () => text },
  });
  target.dispatchEvent(event);
  return event;
}

const pdf = (name: string) => new File(["%PDF"], name, { type: "application/pdf" });

describe("usePastedFiles", () => {
  let container: HTMLDivElement;
  let root: Root;
  const onFiles = vi.fn();

  const mount = (enabled: boolean) => {
    act(() => {
      root.render(<Host enabled={enabled} onFiles={onFiles} />);
    });
  };

  beforeEach(() => {
    onFiles.mockReset();
    vi.spyOn(console, "debug").mockImplementation(() => undefined);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.restoreAllMocks();
  });

  it("attaches files pasted while the focus sits outside the composer", () => {
    mount(true);
    const event = paste(document.body, [pdf("a.pdf"), pdf("b.pdf")]);

    expect(onFiles).toHaveBeenCalledTimes(1);
    expect(onFiles.mock.calls[0][0].map((f: File) => f.name)).toEqual(["a.pdf", "b.pdf"]);
    expect(event.defaultPrevented).toBe(true);
  });

  it("attaches files pasted into the composer itself, once", () => {
    mount(true);
    paste(container.querySelector("textarea")!, [pdf("a.pdf")]);

    expect(onFiles).toHaveBeenCalledTimes(1);
  });

  it("leaves a text paste to the browser", () => {
    mount(true);
    const event = paste(container.querySelector("textarea")!, [], "hello");

    expect(onFiles).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  it("does nothing while the agent accepts no attachments", () => {
    mount(false);
    const event = paste(document.body, [pdf("a.pdf")]);

    expect(onFiles).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  it("stops listening once unmounted", () => {
    mount(true);
    act(() => root.unmount());
    root = createRoot(container);
    paste(document.body, [pdf("a.pdf")]);

    expect(onFiles).not.toHaveBeenCalled();
  });
});

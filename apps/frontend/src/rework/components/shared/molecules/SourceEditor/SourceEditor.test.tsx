// @vitest-environment jsdom
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
import { createRoot } from "react-dom/client";
import { expect, it } from "vitest";
import { SourceEditor } from "./SourceEditor";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

it("highlights a Python file and returns to plain text for an unknown filename without changing the source", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const source = 'def greet(name):\n    return "Hello " + name';
  const changes: string[] = [];
  const render = async (filename: string) => {
    await act(async () => {
      root.render(
        <SourceEditor
          filename={filename}
          value={source}
          label="File source"
          onChange={(value) => changes.push(value)}
        />,
      );
    });
  };
  try {
    await render("/scripts/greet.py");
    for (let attempt = 0; attempt < 20 && !host.querySelector(".cm-line span"); attempt++)
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 20));
      });
    expect([...host.querySelectorAll(".cm-line span")].some((node) => node.textContent === "def")).toBe(true);
    expect(host.querySelector('[role="textbox"]')?.textContent).toBe('def greet(name):    return "Hello " + name');
    await render("/notes.unrecognized");
    expect(host.querySelector(".cm-line span")).toBeNull();
    expect(host.querySelector('[role="textbox"]')?.textContent).toBe('def greet(name):    return "Hello " + name');
    expect(changes).toEqual([]);
  } finally {
    act(() => root.unmount());
    host.remove();
  }
});

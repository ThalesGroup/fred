// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { EditorView } from "@codemirror/view";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import { formatTraceJson } from "./formatTraceJson";
import TraceJson from "./TraceJson";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));

const writeRichClipboard = vi.hoisted(() => vi.fn(async () => true));
vi.mock("@rework/utils/clipboardUtils", () => ({ writeRichClipboard }));

it("indents captured JSON without changing number or string tokens and copies the original text", async () => {
  const raw = ' \r\n{"id":9223372036854775807,"id":-0,"array":[1e900,{},[],"x\\u0020y,]"]}\r\n';
  const code = formatTraceJson(raw);
  expect(code).toBe(
    '{\n  "id": 9223372036854775807,\n  "id": -0,\n  "array": [\n    1e900,\n    {},\n    [],\n    "x\\u0020y,]"\n  ]\n}',
  );

  const host = document.body.appendChild(document.createElement("div"));
  const root = createRoot(host);
  try {
    act(() => root.render(<TraceJson code={code!} label="Captured payload" copyText={raw} />));
    const editor = host.querySelector<HTMLElement>(".cm-editor");
    expect(EditorView.findFromDOM(editor!)?.state.doc.toString()).toBe(code);
    expect(host.querySelector(".cm-foldGutter [title]")).toBeTruthy();
    await act(async () => host.querySelector<HTMLButtonElement>('[aria-label="common.copyCode"]')?.click());
    expect(writeRichClipboard).toHaveBeenCalledWith("", raw);
  } finally {
    act(() => root.unmount());
    host.remove();
  }
});

it.each(['{"truncated":1', "[DONE]", "upstream unavailable"])("keeps non-JSON evidence in the raw view (%s)", (raw) => {
  expect(formatTraceJson(raw)).toBeUndefined();
});

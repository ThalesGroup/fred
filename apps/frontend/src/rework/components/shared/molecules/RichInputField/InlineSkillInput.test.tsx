// @vitest-environment jsdom
// Copyright Thales 2026 — Licensed under the Apache License, Version 2.0.
import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { EditorView } from "@codemirror/view";
import { deleteCharBackward, undo } from "@codemirror/commands";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { usePastedFiles } from "@rework/components/pages/ManagedChatPage/usePastedFiles";
import { RichInputField } from "./RichInputField";
import { findSkillInvocation } from "@rework/utils/skillInvocation";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
vi.mock("react-i18next", () => {
  const t = (key: string) => key;
  return { useTranslation: () => ({ t }) };
});
// jsdom has no layout engine; interaction assertions do not use geometry.
beforeAll(() => {
  Element.prototype.scrollIntoView = () => {};
  Range.prototype.getClientRects = () => [] as unknown as DOMRectList;
  Range.prototype.getBoundingClientRect = () => new DOMRect();
});
let root: Root;
let container: HTMLDivElement;
const onSend = vi.fn();
const onOpen = vi.fn();
const onChange = vi.fn();
const onFiles = vi.fn();
const claimKey = vi.fn<(event: import("./RichInputField").CommandKeyEvent) => boolean>(() => false);
function Host({ disabled = false, prompt = false }: { disabled?: boolean; prompt?: boolean }) {
  usePastedFiles({ enabled: !disabled, onFiles });
  const [value, setValue] = useState(prompt ? "/hello Notes" : "Before /compte-rendu after\nAction");
  const token = findSkillInvocation(value, ["compte-rendu"], true);
  return (
    <RichInputField
      value={value}
      disabled={disabled}
      onChange={(text) => {
        onChange(text);
        setValue(text);
      }}
      onSend={onSend}
      showSendButton
      placeholder="[notes]"
      inlineSkills={{
        tokens: token ? [{ ...token, description: "Meeting minutes", onOpen }] : [],
        promptToken:
          prompt && value.startsWith("/hello ")
            ? { from: 0, to: 6, name: "Hello", description: "Say hello", source: "personal" }
            : null,
      }}
      commandTrigger={{
        onQueryChange: vi.fn(),
        onFocusChange: vi.fn(),
        onKeyDown: claimKey,
        listboxId: "commands",
        open: false,
        activeDescendantId: null,
      }}
    />
  );
}
const editor = () => EditorView.findFromDOM(container.querySelector(".cm-content")!)!;
beforeEach(() => {
  vi.clearAllMocks();
  claimKey.mockReset().mockReturnValue(false);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root.render(<Host />));
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

it("keeps canonical text in the editor while placing the clickable token between surrounding words", () => {
  expect(editor().state.doc.toString()).toBe("Before /compte-rendu after\nAction");
  expect(editor().contentDOM.getAttribute("aria-label")).toBe("chatbot.composerPlaceholder");
  expect(container.querySelector(".cm-line")?.textContent).toBe("Before compte-rendu after");
  const badge = container.querySelector<HTMLButtonElement>('[aria-label="chatbot.skills.open"]')!;
  expect(badge.title).toBe("chatbot.skills.platformProvided\nMeeting minutes");
  act(() => badge.click());
  expect(onOpen).toHaveBeenCalledWith("compte-rendu");
  expect(onSend).not.toHaveBeenCalled();
  expect(onChange).not.toHaveBeenCalled();
});
it("deleting a character removes the import and undo restores it with the request intact", () => {
  act(() => {
    editor().dispatch({ selection: { anchor: 20 } });
    deleteCharBackward(editor());
  });
  expect(editor().state.doc.toString()).toBe("Before /compte-rend after\nAction");
  expect(container.querySelector('[aria-label="chatbot.skills.open"]')).toBeNull();
  expect(editor().contentDOM.getAttribute("aria-label")).toBe("chatbot.composerPlaceholder");
  act(() => {
    undo(editor());
  });
  expect(container.querySelector('[aria-label="chatbot.skills.open"]')).not.toBeNull();
});
it("lets the completion handler consume Enter before the editor inserts a newline or sends", () => {
  claimKey.mockImplementation((event) => {
    event.preventDefault();
    return true;
  });
  act(() =>
    editor().contentDOM.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true })),
  );
  expect(onSend).not.toHaveBeenCalled();
  expect(editor().state.doc.lines).toBe(2);
});
it("sends on Enter and keeps Shift+Enter as a real document newline", () => {
  act(() =>
    editor().contentDOM.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true })),
  );
  expect(onSend).toHaveBeenCalledOnce();
  act(() =>
    editor().contentDOM.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", shiftKey: true, bubbles: true, cancelable: true }),
    ),
  );
  expect(editor().state.doc.lines).toBe(3);
  expect(onSend).toHaveBeenCalledOnce();
});
it("copies selected underlying invocation text rather than losing the slash with its visual token", () => {
  const setData = vi.fn();
  act(() => {
    editor().dispatch({ selection: { anchor: 7, head: 20 } });
    const event = new Event("copy", { bubbles: true, cancelable: true });
    Object.defineProperty(event, "clipboardData", { value: { clearData: vi.fn(), setData } });
    editor().contentDOM.dispatchEvent(event);
  });
  expect(setData).toHaveBeenCalledWith("text/plain", "/compte-rendu");
});
it("keeps arguments as an inline hint for a bare selected invocation", () => {
  act(() =>
    editor().dispatch({
      changes: { from: 0, to: editor().state.doc.length, insert: "/compte-rendu " },
      selection: { anchor: 14 },
    }),
  );
  expect(container.querySelector(".cm-line")?.textContent).toContain("[notes]");
  act(() => editor().dispatch({ changes: { from: 14, insert: "Meeting" } }));
  expect(container.querySelector(".cm-line")?.textContent).not.toContain("[notes]");
});
it("blocks editing and sending while disabled", () => {
  act(() => root.render(<Host disabled />));
  expect(editor().state.readOnly).toBe(true);
  expect(editor().contentDOM.getAttribute("contenteditable")).toBe("false");
  act(() =>
    editor().contentDOM.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true })),
  );
  expect(onSend).not.toHaveBeenCalled();
});

it.each(["partial", "whole"])(
  "pasting a screenshot keeps a %s draft selection intact and attaches the file once",
  (selection) => {
    const original = editor().state.doc.toString();
    const file = new File(["image"], "screenshot.png", { type: "image/png" });
    act(() => {
      editor().dispatch({
        selection: selection === "whole" ? { anchor: 0, head: editor().state.doc.length } : { anchor: 21, head: 26 },
      });
      const paste = new Event("paste", { bubbles: true, cancelable: true });
      Object.defineProperty(paste, "clipboardData", { value: { files: [file], types: ["Files"], getData: () => "" } });
      editor().contentDOM.dispatchEvent(paste);
      expect(paste.defaultPrevented).toBe(true);
    });
    expect(onFiles).toHaveBeenCalledExactlyOnceWith([file]);
    expect(editor().state.doc.toString()).toBe(original);
    expect(onChange).not.toHaveBeenCalled();
  },
);

it("does not reconfigure the editor when unchanged parent renders recreate token and trigger objects", () => {
  const dispatch = vi.spyOn(editor(), "dispatch");
  for (let index = 0; index < 20; index++) act(() => root.render(<Host />));
  expect(dispatch).not.toHaveBeenCalled();
  expect(editor().state.doc.toString()).toBe("Before /compte-rendu after\nAction");
  dispatch.mockRestore();
});

it("keeps a prompt command copyable, editable and undoable beneath its visual", () => {
  act(() => {
    root.unmount();
    root = createRoot(container);
    root.render(<Host prompt />);
  });
  const setData = vi.fn();
  act(() => {
    editor().dispatch({ selection: { anchor: 0, head: 6 } });
    const event = new Event("copy", { bubbles: true, cancelable: true });
    Object.defineProperty(event, "clipboardData", { value: { clearData: vi.fn(), setData } });
    editor().contentDOM.dispatchEvent(event);
  });
  expect(setData).toHaveBeenCalledWith("text/plain", "/hello");
  act(() => {
    editor().dispatch({ selection: { anchor: 6 } });
    deleteCharBackward(editor());
  });
  expect(editor().state.doc.toString()).toBe("/hell Notes");
  expect(container.querySelector("[class*=promptToken]")).toBeNull();
  act(() => {
    undo(editor());
  });
  expect(editor().state.doc.toString()).toBe("/hello Notes");
  expect(container.querySelector("[class*=promptToken]")).not.toBeNull();
  const dispatch = vi.spyOn(editor(), "dispatch");
  act(() => root.render(<Host prompt />));
  expect(dispatch).not.toHaveBeenCalled();
  dispatch.mockRestore();
});

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

import { act, type ComponentProps } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
const native = vi.hoisted(() => ({
  latest: null as string | null,
  props: null as null | { markdown: string; onChange: (value: string, initial: boolean) => void; onError: () => void },
}));
vi.mock("@mdxeditor/editor", async () => {
  const { forwardRef, useImperativeHandle, useEffect } = await import("react");
  return {
    MDXEditor: forwardRef((props: NonNullable<typeof native.props>, ref) => {
      native.props = props;
      useEffect(() => {
        native.latest = null;
      }, []);
      useImperativeHandle(ref, () => ({ getMarkdown: () => native.latest ?? props.markdown }));
      return <textarea aria-label="mock markdown" value={props.markdown} readOnly />;
    }),
    realmPlugin: () => () => null,
    diffSourcePlugin: () => null,
    markdownShortcutPlugin: () => null,
    toolbarPlugin: () => null,
  };
});
vi.mock("@mdxeditor/editor/style.css", () => ({}));
vi.mock("@shared/organisms/ProseMdxEditor/ProseMdxEditor", () => ({
  ProseToolbarButtons: () => null,
  proseMdxPlugins: () => [],
}));

import { ApplicationContext } from "../../../../app/ApplicationContextProvider";
import { WikiEditor } from "./WikiEditor";

describe("WikiEditor", () => {
  let container: HTMLDivElement;
  let root: Root;
  const onSave = vi.fn();
  const onDelete = vi.fn();

  beforeEach(() => {
    native.latest = null;
    onSave.mockReset();
    onDelete.mockReset();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  const render = (
    withPlacement: boolean,
    overrides: Partial<ComponentProps<typeof WikiEditor>> = {},
    darkMode = false,
  ) =>
    act(() => {
      root.render(
        <ApplicationContext.Provider value={{ darkMode } as never}>
          <WikiEditor
            title="Onboarding"
            placement={
              withPlacement
                ? {
                    parentId: "",
                    parentOptions: [
                      { value: "", key: "__root__", label: "root" },
                      { value: "p-2", key: "p-2", label: "Tooling" },
                    ],
                    onDelete,
                  }
                : undefined
            }
            initialContent="hello"
            maxChars={1000}
            saving={false}
            conflict={null}
            onSave={onSave}
            onCancel={vi.fn()}
            onTakeTheirs={vi.fn()}
            {...overrides}
          />
        </ApplicationContext.Provider>,
      );
    });

  const button = (label: string) =>
    [...container.querySelectorAll("button")].find(
      (b) => b.textContent === label || b.getAttribute("aria-label") === label,
    );

  it("edits the title of an ordinary page and saves it with the text", () => {
    render(true);
    const input = container.querySelector("input")!;
    expect(input.value).toBe("Onboarding");
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
      setter.call(input, "  Getting started ");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(container.querySelector("h1")?.textContent).toBe("Getting started");
    act(() => button("rework.wiki.editor.save")!.click());
    expect(onSave).toHaveBeenCalledWith("hello", { title: "Getting started", parentId: "" });
  });

  it("asks to delete from the error-colored icon button", () => {
    render(true);
    act(() => button("rework.wiki.editor.delete")!.click());
    expect(onDelete).toHaveBeenCalledTimes(1);
  });

  it("keeps the rules page title fixed, with no parent and no delete", () => {
    render(false);
    expect(container.querySelector("input")).toBeNull();
    expect(container.querySelector("h1")?.textContent).toBe("Onboarding");
    expect(button("rework.wiki.editor.delete")).toBeUndefined();
    act(() => button("rework.wiki.editor.save")!.click());
    expect(onSave).toHaveBeenCalledWith("hello", null);
  });

  const formatted = (body: string, prefix = "") =>
    ({
      body_md: body,
      frontmatter_prefix: prefix,
      page_type: "untyped",
      tags: [],
    }) as NonNullable<ComponentProps<typeof WikiEditor>["initialFormat"]>;

  it("prepares the latest source ref before saving, including changes not yet delivered by onChange", async () => {
    const onPrepare = vi.fn(async ({ content_md }) => formatted(content_md));
    render(true, { onPrepare });
    native.latest = "# Latest\n\n- One";
    await act(async () => button("rework.wiki.editor.save")!.click());
    expect(onPrepare).toHaveBeenCalledWith({ content_md: "# Latest\n\n- One" });
    expect(onSave).toHaveBeenCalledWith("# Latest\n\n- One", { title: "Onboarding", parentId: "" });
  });

  it("retains invalid source and mode on server refusal, then permits correction", async () => {
    const onPrepare = vi
      .fn()
      .mockRejectedValueOnce({ data: { detail: "type: unsupported" } })
      .mockResolvedValueOnce(formatted("# Fixed"));
    render(true, { onPrepare });
    native.latest = "---\ntype: imported\n---\n# Draft";
    await act(async () => button("rework.wiki.editor.visual")!.click());
    expect(native.props!.markdown).toBe(native.latest);
    expect(container.textContent).toContain("type: unsupported");
    expect(onSave).not.toHaveBeenCalled();
    native.latest = "# Fixed";
    await act(async () => button("rework.wiki.editor.visual")!.click());
    expect(native.props!.markdown).toBe("# Fixed");
  });

  it.each(["\n", "\r\n"])(
    "preserves the %j opaque prefix and inserts only a required EOF separator",
    async (newline) => {
      const prefix = ["---", "type: topic", "x-large: 123456789012345678901234567890", "---"].join(newline);
      const onPrepare = vi.fn(async ({ content_md }) => formatted(content_md));
      render(true, { initialContent: prefix, initialFormat: formatted("", prefix), onPrepare });
      native.latest = "Body";
      await act(async () => button("rework.wiki.editor.save")!.click());
      expect(onPrepare).toHaveBeenCalledWith({ content_md: prefix + newline + "Body", properties: {} });
    },
  );

  it("preserves raw CRLF on source focus, theme remount and no-op save", async () => {
    const raw = "---\r\ntype: topic\r\n---\r\nBody\r\n";
    const onPrepare = vi.fn(async ({ content_md }) => formatted(content_md));
    const props = { initialContent: raw, onPrepare };
    render(true, props);
    act(() => native.props!.onChange(raw.replaceAll("\r\n", "\n"), true));
    render(true, props, true);
    expect(native.props!.markdown).toBe(raw);
    native.latest = raw.replaceAll("\r\n", "\n");
    await act(async () => button("rework.wiki.editor.save")!.click());
    expect(onSave).toHaveBeenCalledWith(raw, { title: "Onboarding", parentId: "" });
  });

  it("ignores preparation completed after closing and reopening", async () => {
    let finish!: (value: ReturnType<typeof formatted>) => void;
    const onPrepare = vi.fn(
      () =>
        new Promise<ReturnType<typeof formatted>>((resolve) => {
          finish = resolve;
        }),
    );
    render(true, { onPrepare });
    await act(async () => button("rework.wiki.editor.save")!.click());
    act(() => root.render(null));
    render(true, { initialContent: "Other draft", onPrepare });
    await act(async () => finish(formatted("Old draft")));
    expect(onSave).not.toHaveBeenCalled();
    expect(native.props!.markdown).toBe("Other draft");
  });

  it("applies pending description before falling back to source and preserves fields on refusal", async () => {
    const onPrepare = vi
      .fn()
      .mockRejectedValueOnce({ data: { detail: "description: invalid" } })
      .mockResolvedValueOnce(formatted("Body", "---\ndescription: fixed\n---\n"));
    render(true, { initialFormat: formatted("Body"), initialContent: "Body", onPrepare });
    // TextInput's label wiring is exercised by selecting its visible description label.
    const labels = [...container.querySelectorAll("label")];
    const label = labels.find((element) => element.textContent?.includes("descriptionLabel"))!;
    const input = document.getElementById(label.htmlFor) as HTMLInputElement;
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "fixed");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => native.props!.onError());
    expect(onPrepare).toHaveBeenLastCalledWith({ content_md: "Body", properties: { description: "fixed" } });
    expect(input.value).toBe("fixed");
    expect(container.textContent).toContain("description: invalid");
    expect(container.querySelector("textarea")!.closest("[inert]")).not.toBeNull();
    expect(input.disabled).toBe(false);
    await act(async () => button("rework.wiki.editor.markdown")!.click());
    expect(native.props!.markdown).toContain("description: fixed");
  });
  it("keeps Save disabled until the whole save including placement has completed", async () => {
    let finish!: () => void;
    onSave.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve;
        }),
    );
    render(true);
    await act(async () => button("rework.wiki.editor.save")!.click());
    expect(button("rework.wiki.editor.save")!.disabled).toBe(true);
    await act(async () => finish());
    expect(button("rework.wiki.editor.save")!.disabled).toBe(false);
  });

  it("lets rules use both modes without metadata or format preparation", async () => {
    render(false);
    await act(async () => button("rework.wiki.editor.markdown")!.click());
    act(() => native.props!.onChange("# Rules\n\n- Cite sources", true));
    await act(async () => button("rework.wiki.editor.visual")!.click());
    expect(native.props!.markdown).toBe("# Rules\n\n- Cite sources");
    expect(container.querySelector("input")).toBeNull();
    await act(async () => button("rework.wiki.editor.save")!.click());
    expect(onSave).toHaveBeenCalledWith("# Rules\n\n- Cite sources", null);
  });
  it("edits type, description and tags through Fred controls, saves and reopens them together", async () => {
    const originalPrefix = "---\ntype: topic\ndescription: Original\ntags: [old]\nx-extra: retained\n---\n";
    const preparedPrefix =
      "---\ntype: procedure\ndescription: Trier les observations\ntags: [astronomie, occultation]\nx-extra: retained\n---\n";
    const prepared = {
      ...formatted("# Observation", preparedPrefix),
      page_type: "procedure",
      description: "Trier les observations",
      tags: ["astronomie", "occultation"],
    };
    const onPrepare = vi.fn(async () => prepared);
    render(true, {
      initialContent: originalPrefix + "# Observation",
      initialFormat: {
        ...formatted("# Observation", originalPrefix),
        page_type: "topic",
        description: "Original",
        tags: ["old"],
      },
      onPrepare,
    });
    const labeledControl = (key: string) => {
      const label = [...container.querySelectorAll("label")].find((element) => element.textContent === key)!;
      return document.getElementById(label.htmlFor)!;
    };
    const setInput = (input: HTMLInputElement, value: string) =>
      act(() => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
    act(() => labeledControl("rework.wiki.editor.typeLabel").click());
    const procedure = [...document.querySelectorAll<HTMLElement>('[role="option"]')].find((option) =>
      option.textContent?.includes("rework.wiki.editor.types.procedure"),
    )!;
    act(() => procedure.click());
    setInput(labeledControl("rework.wiki.editor.descriptionLabel") as HTMLInputElement, "Trier les observations");
    act(() => button("rework.wiki.editor.removeTag")!.click());
    const tagsInput = container.querySelector<HTMLInputElement>('input[aria-label="rework.wiki.editor.tagsLabel"]')!;
    for (const tag of ["astronomie", "occultation"]) {
      setInput(tagsInput, tag);
      act(() => tagsInput.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
    }
    await act(async () => button("rework.wiki.editor.save")!.click());
    expect(onPrepare).toHaveBeenCalledExactlyOnceWith({
      content_md: originalPrefix + "# Observation",
      properties: {
        page_type: "procedure",
        description: "Trier les observations",
        tags: ["astronomie", "occultation"],
      },
    });
    const savedSource = preparedPrefix + "# Observation";
    expect(onSave).toHaveBeenCalledExactlyOnceWith(savedSource, { title: "Onboarding", parentId: "" });
    act(() => root.render(null));
    render(true, { initialContent: savedSource, initialFormat: prepared, onPrepare });
    expect(labeledControl("rework.wiki.editor.typeLabel").textContent).toContain("rework.wiki.editor.types.procedure");
    expect((labeledControl("rework.wiki.editor.descriptionLabel") as HTMLInputElement).value).toBe(
      "Trier les observations",
    );
    expect(container.textContent).toContain("astronomie");
    expect(container.textContent).toContain("occultation");
    expect(container.querySelectorAll('button[aria-label="rework.wiki.editor.removeTag"]')).toHaveLength(2);
    expect(native.props!.markdown).toBe("# Observation");
  });
});

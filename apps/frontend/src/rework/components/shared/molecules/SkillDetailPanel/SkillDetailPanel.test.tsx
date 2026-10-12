// @vitest-environment happy-dom
// Copyright Thales 2026. Licensed under the Apache License, Version 2.0.
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import SkillDetailPanel from "./SkillDetailPanel";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: { name: string }) =>
      key === "chatbot.skills.panelTitle" ? `Skill: ${values?.name}` : key,
  }),
}));
vi.mock("../ChatSidePanel/ChatSidePanel", () => ({
  default: ({ open, title, children }: { open: boolean; title: string; children: React.ReactNode }) =>
    open ? (
      <aside>
        <h2>{title}</h2>
        {children}
      </aside>
    ) : null,
}));
let root: Root;
let container: HTMLDivElement;
beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});
const detail = {
  skill: { name: "minutes", description: "Prepare meeting minutes", argument_hint: "[notes]" },
  revision: "current",
  content:
    "---\nname: minutes\ndescription: hidden YAML\n---\n## Procedure\nRead **the notes** and [template](references/template.md).\n<script>alert('x')</script>",
};
function render(props: Partial<React.ComponentProps<typeof SkillDetailPanel>> = {}) {
  act(() =>
    root.render(
      <SkillDetailPanel
        open
        name="minutes"
        detail={detail}
        loading={false}
        error={false}
        onClose={vi.fn()}
        onRetry={vi.fn()}
        {...props}
      />,
    ),
  );
}
describe("skill preview content and request states", () => {
  it("renders metadata and sanitized Markdown without raw frontmatter or broken local links", () => {
    render();
    expect(container.querySelector("h2")?.textContent).toBe("Skill: minutes");
    const paragraphs = container.querySelectorAll("p");
    expect(paragraphs[0]?.textContent).toBe("chatbot.skills.arguments [notes]");
    expect(paragraphs[1]?.textContent).toBe("chatbot.skills.description Prepare meeting minutes");
    expect(container.querySelector("h3")).toBeNull();
    expect(container.querySelector("strong")?.textContent).toBe("the notes");
    expect(container.textContent).toContain("[notes]");
    expect(container.textContent).not.toContain("chatbot.skills.currentVersion");
    expect(container.textContent).not.toContain("chatbot.skills.content");
    expect(container.textContent).not.toContain("hidden YAML");
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector('a[href="references/template.md"]')).toBeNull();
    expect(container.textContent).toContain("template");
  });
  it("omits the arguments section when no hint is supplied", () => {
    render({ detail: { ...detail, skill: { name: "minutes", description: "Prepare meeting minutes" } } });
    expect(container.textContent).not.toContain("chatbot.skills.arguments");
    expect(container.querySelector("p")?.textContent).toBe("chatbot.skills.description Prepare meeting minutes");
  });
  it("does not display an old skill or cached content during loading and errors", () => {
    render({ name: "other" });
    expect(container.textContent).not.toContain("the notes");
    render({ loading: true });
    expect(container.textContent).toContain("chatbot.skills.loading");
    expect(container.textContent).not.toContain("the notes");
    const retry = vi.fn();
    render({ error: true, onRetry: retry });
    expect(container.textContent).not.toContain("the notes");
    act(() => container.querySelector<HTMLButtonElement>("button")!.click());
    expect(retry).toHaveBeenCalledOnce();
    render({ open: false });
    expect(container.textContent).toBe("");
  });
});

it("shows a Markdown reference exactly as returned, and escapes non-Markdown file text", () => {
  render({
    file: {
      name: "minutes",
      path: "references/model.md",
      content: "## Reference\n**Stored** [local](other.md)\n<script>bad()</script>",
    },
  });
  expect(container.querySelector("strong")?.textContent).toBe("Stored");
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector("a")).toBeNull();
  expect(container.textContent).not.toContain("Prepare meeting minutes");
  render({ file: { name: "minutes", path: "data.json", content: '<script>exact</script>\n{"x": 1}' } });
  expect(container.querySelector("pre")?.textContent).toBe('<script>exact</script>\n{"x": 1}');
  expect(container.querySelector("script")).toBeNull();
});

it("labels native paginated references as excerpts and preserves the exact returned text", () => {
  const content = "File: /skills/minutes/references/model.md\n2: **Stored** <script>bad()</script>";
  render({ file: { name: "minutes", path: "references/model.md", content, excerpt: true } });
  expect(container.textContent).toContain("chatbot.skills.fileExcerptTitle");
  expect(container.querySelector("pre")?.textContent).toBe(content);
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector("strong")).toBeNull();
});

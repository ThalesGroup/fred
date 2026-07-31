# Help Center content — authoring guide

Every Help Center page is a plain markdown file in this tree. The app derives
the sidebar, routes, breadcrumb and (soon) search from the files — adding or
editing a page never requires touching React code.

## Layout

```
content/
├── fr/<section-id>/<page-id>.md    French pages
├── en/<section-id>/<page-id>.md    English pages (mirror tree, same file names)
└── assets/                          images, shared by both languages
```

- `<section-id>` must be one of the sections declared in `../manifest.ts`
  (`getting-started`, `features`, `guides`, `troubleshooting`, `faq`,
  `architecture`, `changelog`). Adding a _section_ is a manifest change;
  adding a _page_ is just a new file.
- `index.md` is the section's landing page — always present, always first in
  the sidebar. Its URL is the bare section URL (`/help/fr/features`).
- Any other file name becomes the page id and URL segment
  (`agents.md` → `/help/fr/features/agents`). Use short kebab-case names;
  keep them **identical across languages** so the language switch can map a
  page to its twin.

## Frontmatter

Each file starts with a small frontmatter block — one `key: value` per line,
no nesting:

```markdown
---
title: Les concepts clés          (required — sidebar + breadcrumb label)
order: 10                          (sidebar position within the section)
description: Une ligne de résumé.  (optional — shown in search results)
icon: school                       (optional Material Symbols name, default: article)
---
```

`icon` must be one of the names in `shared/utils/Type.ts` (`materialIcons`);
extend that list to adopt a new glyph.

## Body conventions

- Start the body with a single `# Title` matching the frontmatter `title`.
- `##` / `###` headings automatically get shareable anchors — keep headings
  unique within a page, and prefer stable wording (changing a heading breaks
  links pointing at it).
- Images: put the file in `assets/` and reference it as
  `![alt text](assets/my-image.png)`. Screenshots pending capture use an
  explicit placeholder: `![TODO: capture — Prompts page, creation dialog]()`.
- Cross-links between pages use absolute in-app paths, language included:
  `[Key concepts](/help/en/getting-started/concepts)`.
- GFM is supported (tables, task lists), plus fenced `mermaid` diagrams.

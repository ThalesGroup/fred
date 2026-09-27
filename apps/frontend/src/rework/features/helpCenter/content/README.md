# Help Center content — authoring guide

Every Help Center page is a plain markdown file in this tree. The app derives
the sidebar, routes, breadcrumb and (soon) search from the files — adding or
editing a page never requires touching React code.

## Layout

```
content/
├── fr/<section-id>/<page-id>.md    French pages
└── en/<section-id>/<page-id>.md    English pages (mirror tree, same file names)
```

- `<section-id>` must be one of the sections declared in `../manifest.ts` —
  read them there rather than from a list here, which is exactly the kind of
  copy that goes stale. Adding a _section_ is a manifest change; adding a
  _page_ is just a new file.
- **No images.** There is no `assets/` directory and no page references one.
  Screenshots date faster than the interface they describe and were carried for
  a long time as dead placeholders; describe the interface in words instead, or
  add a real directory with real files and update this line.
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
- **Never leave an image placeholder.** The tree carried 25 of them, pointing
  at 13 files in an `assets/` directory that never existed — every one a dead
  link a reader hit before anyone noticed. Describe the interface in words. If
  you genuinely add an image, add the real file and say so in Layout above.
- Cross-links between pages use absolute in-app paths, language included:
  `[Agents](/help/en/features/agents)`. Both language trees hold the same page
  ids, so a link is valid in both once it is valid in one.
- GFM is supported (tables, task lists), plus fenced `mermaid` diagrams.

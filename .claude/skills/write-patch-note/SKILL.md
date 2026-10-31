---
name: write-patch-note
description: Draft a short bilingual, user-facing Fred patch note from merged changes since a version tag, ready for the patch-note announcement editor. Use for release announcements, not operator release notes.
---

# Write a patch note

Generate text to paste into patch-note announcements on Fred platforms. Each locale (`fr` and `en`) needs a separate plain-text title and Markdown body. Do not create, enable, or publish an announcement.

## Select the changes

- Read the active checkout's `AGENTS.md`. Resolve the release endpoint from the user's request or the repository's current release workflow; do not assume a Swift branch. Accept an optional starting version. Otherwise use the highest versioned `code/v*` tag reachable from that endpoint. Never invent a tag when no matching version exists.
- Refresh the selected remote ref and tags when possible; disclose a stale or local-only source. Check that the starting tag is an ancestor of the endpoint. Ask only when the intended release range cannot be established.
- Read the canonical [`apps/frontend/public/release.md`](../../../apps/frontend/public/release.md) for a recap and its issue references. If it already has a draft entry for the release being announced, use that entry as a candidate inventory. An entry for the starting tag describes changes already released and must not be carried into the new note.
- Review first-parent changes in `<tag>..<end point>` so unmerged work and feature-branch intermediate commits stay out. Use commit and PR details, changed code, and user documentation where needed to establish actual shipped behavior. Commit prefixes and file names alone do not prove that a change belongs in the note.
- Group related commits into user-visible outcomes. Do not repeat one feature under multiple bullets or claim a feature is available when it is still gated or incomplete.

## Choose the content

- Write for Fred users. Lead with meaningful features and improvements they can use. Exclude admin-only changes, operator instructions, migrations, security fixes, dependency updates, infrastructure, refactors, tests, and other internal maintenance.
- Mention ordinary user-visible bug fixes in one short sentence total, or omit the section when none qualify. Give a critical user-visible fix its own short sentence only when the evidence supports its severity and the practical effect is worth explaining. Never expose security details.
- Explain the result in everyday language, without commit titles, issue numbers, implementation terms, or promises about a release date. Keep the whole note succinct: one short sentence per feature bullet, no subordinate lists or extended explanations. Combine small related changes and leave out marginal items.
- Keep a natural editorial voice that makes the benefit clear and invites reading without hype. Emojis are optional; use no more than one or two in the whole note, only where they help. Avoid an emoji on every bullet and repetitive sentence openings.
- Use the same verified claims in both languages, written naturally rather than word for word. Give each language a specific, concise, inviting title. Do not invent a destination version; include one only if the user supplied or confirmed it.

## Deliver the notes

Return exactly two locale blocks, French then English. In each block, label the plain-text title and place the Markdown body in its own fenced block, so both fields can be copied directly. Check title/body limits in the current announcement editor and backend validation when available; do not infer them from retired contracts. Do not repeat the title as a body heading. Use simple headings and bullets if they aid scanning. Do not add a preface, conclusion, source links, version-range report, or drafting commentary to the output.

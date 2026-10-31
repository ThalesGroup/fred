---
name: fred-design-system-reviewer
description: Review FRED frontend changes for design-system, UX, accessibility, generated-client, and visual consistency. Use when reviewing React, TypeScript, CSS modules, rework components, task indicators, drawers, tables, badges, buttons, icons, forms, admin pages, or any UI that must match the FRED design system. Especially use when there is risk of custom controls, text overflow, inconsistent status display, or frontend code bypassing shared components.
---

## Shared team policy

Read the active checkout's `AGENTS.md`, applicable nested instructions and
`fred-reconstruction-method` for domain/persistence work. Use that checkout's
arc42 and code; never load policy from a hardcoded personal Fred directory.
Apply the reuse, replacement and production-code reduction acceptance rule.
This is a bounded review unless fixes are requested. Propose verification needs
without automatically starting tests, load campaigns or independent agents.

# FRED Design System Reviewer

Review frontend changes as product UI, not only as React code. The aim is consistency, predictable workflows, and shared components.
UX requirements do not define persistence or authorization. Reject duplicate local
controls when an existing design-system element can be reused or extended.

## Required Workflow

1. Read `AGENTS.md`, the accepted business scope and the current shared UI implementation.
2. Identify the user workflow and the design-system primitives already used nearby.
3. Check whether the change reuses existing atoms, molecules, organisms, hooks, generated clients, and tokens.
4. Inspect responsive behavior and long text behavior from the code and CSS.
5. Prefer concrete file/line findings over subjective taste.

## Design-System Invariants

- Use existing shared components for buttons, icon buttons, badges, progress bars, selects, drawers, popovers, cards, tables, and status indicators.
- Use existing icon systems instead of raw SVG or text symbols when an icon component exists.
- Use generated RTK clients and generated types for backend shapes.
- Do not create ad hoc status colors, spacing, typography, or border radii when tokens exist.
- Do not duplicate card-in-card layouts or decorative wrappers around operational UI.
- Text must not overlap, truncate without title where inspection matters, or overflow compact controls.
- Async status must be shown from canonical task/entity state, not separately invented local labels.
- Loading, empty, error, disabled, and permission-denied states must be deliberate.
- Accessibility labels must exist for icon-only controls and dialogs/popovers.

## Visual Review Checklist

Check:

- layout density matches the surrounding product surface
- controls use icons for familiar actions and text for explicit commands
- long names, filenames, team names, and error messages have safe overflow behavior
- status badges/progress bars have stable dimensions
- destructive or irreversible actions are visually and semantically distinct
- forms use existing inputs/selects/toggles and expose disabled reasons when important
- polling or realtime indicators do not imply stronger freshness than the implementation provides

## Findings Standard

Each finding must include:

- user-visible impact
- exact file/line reference
- design-system rule or local precedent violated
- minimal fix direction using existing components or tokens

Avoid generic "make it prettier" comments. If screenshots are unavailable, state that the finding is code-based.

## Minimum Test or Verification Expectations

For meaningful UI changes, expect at least one of:

- component/unit test for state rendering
- interaction test for critical workflow
- visual/manual verification notes for responsive and long-text cases
- generated client evidence when API shapes are consumed
- accessibility checks for dialogs, popovers, and icon-only buttons

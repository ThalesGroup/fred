# Frontend Coding Guidelines

Mandatory rules for all frontend work in the `frontend/` directory.
Read this before touching any `.tsx`, `.css`, or `.scss` file under `src/rework/`.

This document is the frontend equivalent of [`PYTHON_CODING_GUIDELINES.md`](./PYTHON_CODING_GUIDELINES.md).

---

## 1. Component Architecture

### Hierarchy rule — atoms → molecules → organisms → pages

All new components live under `src/rework/components/shared/` or
`src/rework/components/pages/`. The placement determines what the component
may import:

| Level | Folder | May import from |
|---|---|---|
| Atom | `shared/atoms/` | Nothing from rework (only tokens + external libs) |
| Molecule | `shared/molecules/` | Atoms only |
| Organism | `shared/organisms/` | Atoms + Molecules |
| Page | `pages/` | Atoms + Molecules + Organisms |

**Violation:** importing an organism from a molecule, or a molecule from an atom,
breaks the hierarchy and creates circular dependency risk.

### No MUI in the rework tree

Do not import from `@mui/material`, `@mui/icons-material`, or any other MUI
package inside `src/rework/`. Use existing design system atoms:

- Icons → `@shared/atoms/Icon/Icon.tsx`
- Buttons → `@shared/atoms/Button/Button.tsx`
- Menus → `@shared/molecules/Menu/Menu.tsx`

MUI is only permitted in the legacy `src/components/` tree, which is being
retired.

---

## 2. CSS Rules — Non-Negotiable

### 2.1 CSS modules only

Every component has its own `ComponentName.module.css` or
`ComponentName.module.scss`. No global styles in module files. No `!important`.

### 2.2 Never use hardcoded color values

This is the single most common source of design system breakage.

**Forbidden in any `.module.css` / `.module.scss` file:**

```css
/* ALL of these are forbidden */
color: black;
color: #1a1a2e;
background: rgba(0, 0, 0, 0.4);
box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
border: 1px solid #d6d6de;
```

**Required — use design tokens for everything:**

```css
color: var(--on-surface);
background: var(--scrim);
box-shadow: var(--shadow-m);
border: 1px solid var(--outline-variant);
```

The only accepted exceptions are **decorative** elements with no semantic
meaning (e.g., an animated rainbow gradient whose specific hue values are
deliberately part of the visual design). Such exceptions must have a comment
referencing the design spec entry that justifies them.

### 2.3 Never use `var(token, fallback)` with a color or dimension fallback

Fallbacks mask undefined tokens silently. This is how bugs survive code review.

```css
/* Forbidden — fallback masks a missing or misspelled token */
color: var(--on-surface-retreat, #666);
background: var(--surface-container-high, rgba(0, 0, 0, 0.06));
border-radius: var(--radius-s, 0.75rem);

/* Required — if the token is missing, find or add it */
color: var(--on-surface-retreat);
background: var(--surface-container-high);
border-radius: var(--radius-s);
```

If a token appears to be missing, check the token files before inventing a
fallback. If it genuinely does not exist, add it to the token file.

### 2.4 Always set `color` explicitly on components with their own background

`body` sets `color: var(--on-surface)`, but any component that sets its own
`background-color` must also set its `color` explicitly. Do not rely on
inheritance when the background changes.

```css
/* Wrong — inherits black if ancestor resets color */
.banner {
  background: var(--secondary-container);
}

/* Correct — text is always readable on its background */
.banner {
  background: var(--secondary-container);
  color: var(--on-secondary-container);
}
```

The M3 pairing rule: every `--foo` background pairs with `--on-foo` text.

---

## 3. Token Reference

Verify that a token exists before using it. The authoritative token files are:

| File | Contains |
|---|---|
| `src/styles/colors-semantic-dark.css` | Semantic color tokens (dark theme) |
| `src/styles/colors-semantic-light.css` | Semantic color tokens (light theme) |
| `src/styles/colors-state-semantic.css` | Hover / pressed / disabled / focused state tokens |
| `src/styles/shadow-dark.css` | Shadow + elevation tokens (dark theme) |
| `src/styles/shadow-light.css` | Shadow + elevation tokens (light theme) |
| `src/styles/spacings.css` | `--spacing-*` tokens |
| `src/styles/radius.css` | `--radius-*` tokens |
| `src/styles/typography.css` | `--font-*` tokens |

### Available shadow and overlay tokens

| Token | Use case |
|---|---|
| `--shadow-s` | Small elevation: tooltips, chips |
| `--shadow-m` | Medium elevation: dropdowns, menus, drawers |
| `--shadow-l` | Large elevation: modals, dialogs |
| `--scrim` | Modal / drawer backdrop overlay |

### Semantic color pairing rule

| Background token | Text token |
|---|---|
| `--primary` | `--on-primary` |
| `--primary-container` | `--on-primary-container` |
| `--secondary` | `--on-secondary` |
| `--secondary-container` | `--on-secondary-container` |
| `--tertiary` | `--on-tertiary` |
| `--tertiary-container` | `--on-tertiary-container` |
| `--surface-*` | `--on-surface` |
| `--error-container` | `--on-error-container` |
| `--success-container` | `--on-success-container` |
| `--warning-container` | `--on-warning-container` |

### Available surface container tokens (elevation scale, low → high)

```
--surface-container-lowest
--surface-container-low
--surface-container
--surface-container-high
--surface-container-highest
```

### Disabled state tokens

| Token | Use case |
|---|---|
| `--state-text-disabled` | Text color on disabled components |
| `--state-on-surface-disabled` | Background of disabled components |

---

## 4. Positioning and Browser API Rules

### No experimental CSS APIs without compatibility check

The following APIs are **not yet safe** to use as the primary implementation
mechanism:

- **CSS Anchor Positioning** (`anchor()`, `position-anchor`, `anchor-name`) —
  limited browser support; use `position: absolute` with explicit `top`/`left`
  instead.
- **CSS Popover API** (`popover`, `popovertarget`) on non-`<button>` elements —
  behaviour is inconsistent on `<div>` targets; prefer CSS `:hover` visibility
  control for tooltips.

For tooltips: `position: absolute` + CSS `:hover` on the parent is reliable,
requires no JavaScript, and works in all browsers.

---

## 5. Token Completeness Rule

If a token you need does not exist, **add it to the token file** — do not
work around it with a hardcoded value or a fallback. Adding a token is a
two-line change (one per theme file). This is always the right answer.

When adding a token:
- Add it to both `colors-semantic-light.css` and `colors-semantic-dark.css`
  (or the appropriate shadow/spacing file).
- Choose a value consistent with the M3 elevation or colour scale already
  present in the file.
- Use the existing naming convention: `--category-variant` or
  `--on-category-variant`.

---

## 6. Pre-Merge Checklist

Before marking any frontend PR ready for review, verify:

- [ ] No hardcoded `rgba()`, `rgb()`, `#hex`, or `hsl()` in module CSS (except
  documented decorative exceptions)
- [ ] No `var(token, #fallback)` or `var(token, rgba(...))` patterns
- [ ] Every component with its own `background-color` also sets `color`
  explicitly using the correct M3 pairing
- [ ] All token references resolve (check the token files — do not guess)
- [ ] No MUI imports in `src/rework/`
- [ ] Component placed at the correct hierarchy level (atom/molecule/organism)
- [ ] No experimental browser API used as the sole implementation path
- [ ] `src/styles/` token files updated if a new token was needed

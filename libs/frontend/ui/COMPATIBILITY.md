# UI compatibility inventory

This inventory was reviewed against FRED commit
`c855853371a9baedf7fee22a02ed97c2f80bfde2` before narrowing the package API.
`npm run audit:compatibility` retains the complete per-call path, line, direct/indirect
size evidence, and the shared-helper/dynamic-icon file inventories; this document
records the compatibility decisions, including the manually reviewed spread cases.

## Button sizes

The current TypeScript AST inventory contains 235 `Button` or `IconButton` JSX
instances, including the new direct tests:

| Component    | `2xs` | `small` | `medium` | Indirect |
| ------------ | ----: | ------: | -------: | -------: |
| `Button`     |     1 |      58 |       68 |        0 |
| `IconButton` |    10 |      73 |       16 |        9 |

One nested `IconButtonMenu` configuration in `DocRow.tsx` passed `xs`, although
IconButton has no `xs` CSS rule. It now passes `small`, the documented 32px tier that
preserves the intended rendered size. The nine remaining indirect `IconButton` cases
are fully bounded:

- `DeleteIconButton.tsx` forwards a `ButtonSize`; its callers use only `small`,
  `medium`, or the default.
- `IconButtonMenu.tsx` forwards a complete `IconButtonProps`, so its size is already
  governed by the narrowed component contract.
- `SearchInput.tsx` computes a `ButtonSize` of only `2xs` or `small`, while its input
  continues to accept the shared `ComponentSize`.
- `TogglePanelButton.tsx` fixes `small`; native props cannot override `size`.
- Five direct IconButton tests spread a fixture whose reviewed size is `small`.

`ComponentSize` therefore remains unchanged for TextInput, SearchInput, Select, and
other controls, while Button and IconButton can accurately expose
`2xs | small | medium`.

## Icon categories and custom behavior

- `IconCategory` is declared in `shared/utils/Type.ts` and consumed only by the
  application-facing `Icon.tsx`. Every JSX category argument in the checkout is
  `outlined`; no Rounded or Sharp caller was found.
- `customAgent` is declared by `CustomIconType`; `isCustomIcon` is used only by the
  current Icon implementation. The application compatibility wrapper is retained,
  including its existing custom-path behavior, rather than treating the package's
  narrower contract as authorization to delete it.
- The package exports the same canonical module's Outlined material primitive with
  `MaterialIconType`; it does not export `IconCategory`, `IconType`, custom paths, or
  category selection.

## Dynamic icon names and shared helpers

Validated dynamic strings:

- `pages/ComingSoon.tsx`: deployment `agentIconName` passes through `toIconType`
  with `person` fallback.
- `pages/TeamApplicationsPage/TeamApplicationsPage.tsx`: generated
  `ApplicationSummary.icon` passes through `toIconType` with `widgets` fallback.
- `pages/admin/CapabilitiesPage/CapabilitiesPage.tsx`: generated capability icon
  passes through `toIconType` with `tune` fallback.
- `shared/utils/agentIcon.ts`: deployment `agentIconName` is checked against
  `materialIcons`; keyword-derived results are statically typed `MaterialIconType`.

Trusted or cast dynamic strings retained for application compatibility:

- `TeamAgentEmptyState.tsx` and `TeamContentNavbar.tsx` cast deployment
  `agentIconName` to `IconType`.
- `AgentFormModal/ToolPackCard.tsx` casts the local `ToolPack.icon` string registry.
- `features/helpCenter/content.ts` casts Markdown frontmatter `icon` values.

Typed `IconType` carriers remain in `fileIconSpec.ts`, `AgentFormBody.tsx`,
`LeaderboardSection.tsx`, `ResponsibleAiSection.tsx`, `MainNavBar.tsx`,
`MenuPopoverItem.tsx`, `PageEmptyState.tsx`, `DocRow/docFileType.ts`,
`OriginBadge.tsx`, `UploadWarningBanner.tsx`, `ExpandableInfoContainer.tsx`,
`ServiceNotice.tsx`, `features/capabilities/types.ts`, and `ChatLauncherRail.tsx`.
They use static unions or values returned by the helpers above. No shared type or
coercion helper is removed by this change.

The binary inspection rejected the legacy `infos` entry: it is not a ligature in the
canonical Outlined font. Its only runtime caller was the default icon in
`ServiceNotice.tsx`; that caller now uses the supported `info` ligature. This preserves
the intended visual meaning while preventing raw fallback text and keeps the public
glyph inventory fully backed by the canonical binary.

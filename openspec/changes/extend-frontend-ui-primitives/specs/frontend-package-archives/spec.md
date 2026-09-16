## MODIFIED Requirements

### Requirement: The UI archive exposes a reviewed initial component contract

The `@fred-oss/ui` archive SHALL expose named JavaScript and TypeScript declarations for `Button`, `IconButton`, `Icon`, `TextInput`, `Spinner`, `Dialog`, `Select`, `Chip`, `Tooltip`, and `Checkbox`, together with only the prop, option, and visual types required to use them. `Menu`, `MenuItem`, `Portal`, and viewport helpers SHALL remain internal. The package MUST NOT expose `TextArea`, `Switch`, `PageEmptyState`, DataTable, pagination, Toast, ConfirmationDialog, application components, other overlays, or internal source paths in this change.

`Button` and `IconButton` SHALL accept only their implemented `2xs`, `small`, and `medium` sizes without removing `xs` or any other value from the application-wide `ComponentSize` type used by other controls. `Select` SHALL retain its existing shared size contract and generic value typing.

#### Scenario: A consumer imports every reviewed export

- **WHEN** an external TypeScript application imports each documented component and public type from `@fred-oss/ui`
- **THEN** type checking and production bundling succeed without a deep import or a FRED source alias

#### Scenario: A consumer requests an unsupported button size

- **WHEN** a consumer assigns `xs` or another unimplemented size to `Button` or `IconButton`
- **THEN** TypeScript rejects the value even though other FRED controls may continue to use that value through the shared application type

#### Scenario: A deferred component is deep-imported

- **WHEN** a consumer attempts to import a deferred component or an internal generated module
- **THEN** the package export map prevents that import from becoming a supported public contract

#### Scenario: Generic Select and icon boundaries are type checked

- **WHEN** a consumer uses `SelectOption<T>` and `SelectProps<T>` with an arbitrary value type, or supplies an unsupported icon name or application-only option model import
- **THEN** generic values retain their type, Material Symbols Outlined names are the only supported icon type, and application model paths are rejected

## ADDED Requirements

### Requirement: Additional UI primitives preserve neutral accessible behavior

`Dialog` SHALL retain its action-oriented open/title/children/confirm/cancel contract with caller-configurable labels, without translation-provider requirements. It SHALL expose an accessible title, focus an appropriate control on opening, contain Tab focus while open, restore prior focus on dismissal, and dismiss through Escape or the scrim. `Select` SHALL retain unique option keys, generic values, disabled-option handling, keyboard navigation, accessible naming, and a configurable empty-state message. `Chip` SHALL retain content slots, tones, and a caller-owned or safe default accessible remove-action name. `Tooltip` SHALL retain hover, keyboard-focus, placement, content, and accessible-description behavior and dismiss on Escape. `Checkbox` SHALL retain native input props, ref, controlled/uncontrolled behavior, disabled state, and indeterminate semantics.

#### Scenario: Dialog focus and action contract

- **WHEN** a keyboard user opens a labelled Dialog and then cancels by Escape, scrim, or Cancel
- **THEN** initial focus enters the Dialog, Tab stays within it, the action callbacks remain distinct, and focus returns to the trigger

#### Scenario: Select inside Dialog handles its own keys

- **WHEN** a user opens Select inside Dialog, selects an enabled option, or presses Escape while its menu is open
- **THEN** selection neither confirms nor dismisses Dialog, and the first Escape closes only Select while a later Escape may dismiss Dialog

#### Scenario: Select has no enabled options

- **WHEN** a caller supplies an empty or fully disabled option set and a custom empty message
- **THEN** the configured message is rendered and keyboard navigation cannot select a disabled option

#### Scenario: Chip and Tooltip actions are accessible

- **WHEN** a removable Chip and a Tooltip are rendered with caller content
- **THEN** the remove control has an accessible name, the Tooltip describes its trigger on hover or keyboard focus, and Escape dismisses it

#### Scenario: Checkbox follows native behavior

- **WHEN** a labelled Checkbox is used with native props, a forwarded ref, controlled or uncontrolled checked state, disabled, or indeterminate state
- **THEN** naming, Space activation, ref, checked and mixed accessibility state, and disabled suppression match native input behavior

### Requirement: UI overlay portals retain consumer scope and theme

Portaled Dialog, Select, and Tooltip content SHALL render inside the originating consumer-owned `.fred-ui` root or a caller-owned container within that root when it exists. Their portal ownership and cleanup MUST NOT remove another mounted component's content. Portaled content SHALL inherit a theme from the root or its ancestor and consume the same scoped component styles, design-token values, and local Material Symbols asset. UI styles MUST NOT require shell-global body styling. Existing FRED callers without a `.fred-ui` root MAY retain their current application portal behavior.

#### Scenario: Multiple overlays share a themed root

- **WHEN** Dialog, Select, and Tooltip mount in a light or dark `.fred-ui` root
- **THEN** their visible portaled content stays within that root, reflects its theme, and unmounting one overlay leaves the others intact

#### Scenario: Tooltip is displayed above Dialog

- **WHEN** a Tooltip trigger appears in an open Dialog
- **THEN** its panel is visible above the overlay and its accessible description remains associated with that trigger

#### Scenario: A portal attempts to escape the consumer root

- **WHEN** a package consumer opens an overlay beneath `.fred-ui`
- **THEN** no overlay style or asset request relies on an unscoped body portal, checkout path, or external font service

### Requirement: The extended UI archive and consumers prove all ten exports

UI package generation SHALL use the explicit canonical source allowlist and retain the React peer, Outlined-only icon, CSS containment, complete-asset/license, runtime/declaration closure, and source-isolation guarantees of the existing archive. The actual packed tarball and separately provisioned isolated React consumer MUST validate all ten public components and public types. UI-only validation SHALL use the selected UI candidate and an exact compatible token coordinate from the independently reviewed published baseline; separate provisioning MUST recheck registry bytes and cryptographic provenance, while offline installation and browser smoke MUST not fetch dependencies, use the historical token CI ZIP, or fall back to FRED sources.

#### Scenario: UI archive contains every transitive input

- **WHEN** the expanded UI package is generated, packed, and validated
- **THEN** every public module, declaration, component style, font, applicable license, and notice resolves from the archive, with internal helpers unexported and React externalized

#### Scenario: Declaration references require declarations

- **WHEN** a packed TypeScript declaration refers to an internal target represented only by executable JavaScript
- **THEN** archive validation rejects that reference even if the JavaScript module itself is packed; valid packed `.d.ts` references remain accepted

#### Scenario: UI-only consumer uses a reviewed token baseline

- **WHEN** a UI-only candidate is validated with the separately provisioned compatible token version
- **THEN** its generic consumer installs from prepared caches, type-checks, builds, and runs browser smoke without historical ZIP, workspace link, source path, or network fallback

#### Scenario: Browser exercises expanded behavior in both themes

- **WHEN** the installed package is tested in fresh light and dark browser contexts
- **THEN** Dialog, Select, Chip, Tooltip, and Checkbox interactions, focus, names, disabled states, portal theme, successful local assets, and optional Geist behavior are checked alongside the original five components

#### Scenario: A new canonical input is changed

- **WHEN** a selected component, internal helper, style, package metadata, test orchestration, or asset input changes
- **THEN** CI selects UI package validation without omitting producer-wide regression tests, while unrelated application changes may skip it

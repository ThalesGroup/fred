## MODIFIED Requirements

### Requirement: The UI archive exposes a reviewed initial component contract

The `@fred-oss/ui` archive SHALL expose named JavaScript and TypeScript declarations for `Button`, `IconButton`, `Icon`, `TextInput`, `Spinner`, `Dialog`, `Select`, `Chip`, `Tooltip`, and `Checkbox`, together with only the prop, option, and visual types required to use them. `Menu`, `MenuItem`, `Portal`, and viewport helpers SHALL remain internal. The archive SHALL additionally expose `TextArea`, `Switch`, `ProgressBar`, `IndicatorDot`, `Disclosure`, `Breadcrumb`, `PageHeader`, `SelectableCard`, `FileDropzone`, `ServiceNotice`, `PageEmptyState`, `KpiStatCard`, `DataTable`, `TablePagination`, `InlineDrawer`, `Toast`, `ToastProvider`, `useToast`, and `StatusBadge`, together with the neutral types needed to consume them. Internal resize/storage helpers SHALL remain unexported. Task-specific badges/progress, ingestion StatusChip, ConfirmationDialog, chart molecules, application components, and internal source paths MUST remain outside the public surface.

`Button` and `IconButton` SHALL accept only their implemented `2xs`, `small`, and
`medium` sizes without removing `xs` or any other value from the application-wide
`ComponentSize` type used by other controls. `Select` SHALL retain its existing shared size contract and generic value typing.

#### Scenario: A consumer imports every reviewed export

- **WHEN** an external TypeScript application imports each documented component and
  public type from `@fred-oss/ui`
- **THEN** type checking and production bundling succeed without a deep import or a
  FRED source alias

#### Scenario: A consumer requests an unsupported button size

- **WHEN** a consumer assigns `xs` or another unimplemented size to `Button` or
  `IconButton`
- **THEN** TypeScript rejects the value even though other FRED controls may continue to
  use that value through the shared application type

#### Scenario: A deferred component is deep-imported

- **WHEN** a consumer attempts to import a deferred component or an internal generated
  module
- **THEN** the package export map prevents that import from becoming a supported public
  contract

#### Scenario: Generic Select and icon boundaries are type checked

- **WHEN** a consumer uses `SelectOption<T>` and `SelectProps<T>` with an arbitrary value type, or supplies an unsupported icon name or application-only option model import
- **THEN** generic values retain their type, Material Symbols Outlined names are the only supported icon type, and application model paths are rejected

## ADDED Requirements

### Requirement: Extended UI components have neutral localized contracts

The extended UI surface MUST work without FRED aliases, application models, translation providers, routing, or task stores. Exported declarations MUST NOT reference `IconType`, `OptionModel`, or `react-i18next`. Icon-bearing props SHALL accept only the supported Material Symbols contract. KpiStatCard, DataTable, and TablePagination SHALL accept caller-owned state, selection, and pagination labels, including count-dependent text. Table options SHALL preserve their numeric value typing. Existing FRED consumers SHALL retain their translated labels and current interactions.

#### Scenario: Independent consumer supplies localized labels
- **WHEN** a consumer renders loading/error/no-data KPI states and selectable paginated tables with its own labels
- **THEN** visible text and accessible action names use those labels without a translation provider, and generic row/value types remain intact

#### Scenario: Unsupported public types are rejected
- **WHEN** a consumer supplies an unsupported icon, invalid table value, or unsupported badge tone
- **THEN** TypeScript rejects the assignment without exposing application-only types

### Requirement: Drawer and toast behavior remains independently usable

InlineDrawer SHALL retain its overlay/push, close, and optional pointer-resize behavior, including width bounds and persistence, without application state dependencies. Toast and ToastProvider SHALL retain severity, dismissal, expiry, and error-copy behavior through a caller-supplied copy action. Toast action names SHALL be caller-configurable. FRED SHALL supply its existing clipboard action. Visible content MUST retain consumer-root styles and light/dark theme inheritance.

#### Scenario: Drawer is resized and reopened
- **WHEN** a consumer resizes a push drawer with a persistence key, closes it, and reopens it
- **THEN** its bounded selected width persists, and overlay/push dismissal behavior remains usable

#### Scenario: Toast copy and lifecycle are driven by the consumer
- **WHEN** a consumer displays an error toast and activates its labelled copy or dismiss action, or a timed toast expires
- **THEN** copy invokes the supplied action with the error text and dismissal/expiry removes the correct toast

### Requirement: A generic status badge preserves evaluation status display

StatusBadge SHALL render a label and exactly one of `success`, `error`, `warning`, `info`, or `neutral` using paired design-system color tokens. It MUST NOT depend on domain states or act as a removable input chip. Evaluation StatusPill SHALL use this shared atom while preserving its current labels and tone mapping.

#### Scenario: All badge tones render in both themes
- **WHEN** a consumer renders each supported tone in light and dark themed roots
- **THEN** each label remains readable with token-based foreground/background pairing and no remove action

### Requirement: Hosted application UI extension has packed-consumer evidence

The alpha.3 archive SHALL retain all existing archive, runtime/declaration closure, source-isolation, React peer, asset/license, and scoped-style guarantees. Validators and the installed isolated React consumer SHALL cover every newly public component and relevant public type with positive and type-negative cases. Browser smoke SHALL render every added component in both themes and exercise forms, disclosure, selection/sorting/pagination, file selection, drawer resize/dismissal, and toast copy/dismissal/expiry. Canonical-source changes MUST select package validation in CI. UI release metadata SHALL identify `0.1.0-alpha.3` without changing unrelated package coordinates or bypassing protected publication.

#### Scenario: The expanded packed surface works outside the checkout
- **WHEN** the generated alpha.3 tarball is installed in the separately provisioned isolated consumer
- **THEN** all added exports type-check, build, render, and pass representative interaction checks without source or network fallback

#### Scenario: A transitive input or public export is missing
- **WHEN** a candidate omits an added export, declaration, style, or required internal dependency
- **THEN** archive or isolated-consumer validation rejects the candidate

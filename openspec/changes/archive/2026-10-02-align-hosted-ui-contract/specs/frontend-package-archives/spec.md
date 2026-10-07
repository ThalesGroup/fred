## MODIFIED Requirements

### Requirement: The UI archive exposes a reviewed initial component contract

The `@fred-oss/ui` archive SHALL expose named JavaScript and TypeScript declarations for `Button`, `IconButton`, `Icon`, `TextInput`, `Spinner`, `Dialog`, `Select`, `Chip`, `Tooltip`, and `Checkbox`, together with only the prop, option, and visual types required to use them. `Menu`, `MenuItem`, `Portal`, and viewport helpers SHALL remain internal. The archive SHALL additionally expose `TextArea`, `Switch`, `ProgressBar`, `IndicatorDot`, `Disclosure`, `Breadcrumb`, `PageHeader`, `SelectableCard`, `FileDropzone`, `ServiceNotice`, `PageEmptyState`, `KpiStatCard`, `DataTable`, `InlineDrawer`, `ToastProvider`, `useToast`, and `StatusBadge`, together with the neutral types needed to consume them. Internal resize/storage helpers SHALL remain unexported. Task-specific badges/progress, ingestion StatusChip, ConfirmationDialog, chart molecules, application components, and internal source paths MUST remain outside the public surface.

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

### Requirement: A generic status badge preserves evaluation status display

StatusBadge SHALL render a label and exactly one of `success`, `error`, `warning`, `info`, or `neutral` as an outlined badge whose text and border use that tone's semantic design-system color. It MUST NOT depend on domain states or act as a removable input chip. Hosted applications SHALL own their domain-specific labels and tone mappings; the shared atom MUST remain available after retiring the built-in evaluation views.

#### Scenario: All badge tones render in both themes
- **WHEN** a consumer renders each supported tone in light and dark themed roots
- **THEN** each label remains readable with its tone's semantic color token and no remove action

### Requirement: The hosted UI surface follows its consumers

The `@fred-oss/ui` hosted surface SHALL expose only the components and behavioral variants a hosted application uses. A new export or behavioral variant SHALL be added with the consuming use case. Optional presentational props of a public component remain public. FRED-internal variants of a canonical component MAY remain outside the public types.

#### Scenario: An internal variant is requested by a hosted consumer
- **WHEN** a hosted application needs a prop that is not public
- **THEN** the prop is added to the public type together with that use case and its packed-consumer evidence

#### Scenario: Internal-only props are rejected
- **WHEN** a consumer passes row selection to `DataTable` or a push, resizable or floating layout to `InlineDrawer`
- **THEN** TypeScript rejects the assignment

### Requirement: Hosted overlay drawer and toasts remain independently usable

The public InlineDrawer SHALL be a single overlay drawer accepting `open`, `onClose`, `title`, `closeLabel`, `width`, `headerActions` and children, closing on its close action, backdrop or Escape, without application state dependencies. Nested hosted drawers are not supported. Like FRED's in-app overlay, opening it does not move keyboard focus and the page behind the backdrop remains focusable. ToastProvider and `useToast` SHALL retain severity, dismissal, expiry, and error-copy behavior through a caller-supplied copy action. Toast action names SHALL be caller-configurable. FRED SHALL supply its existing clipboard action. Visible content MUST retain consumer-root styles and light/dark theme inheritance.

#### Scenario: Overlay drawer is dismissed
- **WHEN** a consumer opens the overlay drawer and presses Escape or activates its labelled close action
- **THEN** the drawer closes through the consumer's `onClose`

#### Scenario: Toast copy and lifecycle are driven by the consumer
- **WHEN** a consumer displays an error toast and activates its labelled copy or dismiss action, or a timed toast expires
- **THEN** copy invokes the supplied action with the error text and dismissal/expiry removes the correct toast

### Requirement: Consumers control row activation and outcome presentation

The shared UI SHALL let consumers activate a typed table row by pointer or keyboard without also activating its embedded controls; an auto-repeated activation key SHALL NOT activate the row again. Consumer-owned drawer close labels SHALL determine the accessible close action name. KPI values SHALL support the shared semantic outcome tones, preserving neutral defaults and visible labels/counts.

#### Scenario: Row activation is isolated
- **WHEN** a consumer activates a row cell or focuses the row and presses Enter or Space
- **THEN** the row callback receives that row, while button/link/input/label/select/textarea actions do not additionally activate the row

#### Scenario: Existing selection stays usable
- **WHEN** a selectable table also exposes row activation
- **THEN** background activation calls the row callback and the checkbox remains responsible for selecting that row

#### Scenario: Localized dismissal and outcome colors
- **WHEN** a consumer supplies a localized close label and a supported KPI tone
- **THEN** the drawer close action uses that accessible label and the KPI value uses the corresponding light/dark design tokens

#### Scenario: Existing callers remain compatible
- **WHEN** consumers omit all new optional props
- **THEN** English drawer close name and neutral KPI rendering remain unchanged

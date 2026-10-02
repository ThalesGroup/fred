## ADDED Requirements

### Requirement: Hosted overlay drawer and dismissible toasts remain independently usable

The public InlineDrawer SHALL be a single overlay drawer accepting `open`, `onClose`, `title`, `closeLabel`, `width`, `headerActions` and children, closing on its close action, backdrop or Escape, without application state dependencies. Nested hosted drawers are not supported. Like FRED's in-app overlay, opening it does not move keyboard focus and the page behind the backdrop remains focusable. The overlay never exceeds the viewport width. ToastProvider and `useToast` SHALL retain severity, dismissal and expiry. The dismiss action name SHALL be caller-configurable. The error-copy action stays FRED-internal. Visible content MUST retain consumer-root styles and light/dark theme inheritance.

#### Scenario: Overlay drawer is dismissed
- **WHEN** a consumer opens the overlay drawer and presses Escape or activates its labelled close action
- **THEN** the drawer closes through the consumer's `onClose`

#### Scenario: Toast lifecycle is driven by the consumer
- **WHEN** a consumer displays toasts and activates a labelled dismiss action, or a timed toast expires
- **THEN** dismissal/expiry removes the correct toast

## MODIFIED Requirements

### Requirement: Extended UI components have neutral localized contracts

The extended UI surface MUST work without FRED aliases, application models, translation providers, routing, or task stores. Exported declarations MUST NOT reference `IconType`, `OptionModel`, or `react-i18next`. Icon-bearing props SHALL accept only the supported Material Symbols contract. KpiStatCard and DataTable SHALL accept caller-owned state and pagination labels, including count-dependent text. Table options SHALL preserve their numeric value typing. Internal Dialog, drawer, pagination and empty-state buttons SHALL NOT submit an enclosing form. The public TextArea SHALL be controlled (`value` and `onChange` required) and own its id. Controlled sorting SHALL require `sortState` and `onSortChange` together. Public DataTable labels SHALL be limited to pagination. ProgressBar SHALL accept a caller accessible name and announce the same bounded percentage it displays. The rows-per-page selector SHALL be named by its visible label. Breadcrumb SHALL accept a localized landmark label. FileDropzone SHALL associate and announce its error and accept the same file again after a pick. Switch SHALL NOT accept `type`, `children` or `dangerouslySetInnerHTML`. Existing FRED consumers SHALL retain their translated labels and current interactions.

#### Scenario: Independent consumer supplies localized labels
- **WHEN** a consumer renders loading/error/no-data KPI states and paginated tables with its own labels
- **THEN** visible text and accessible action names use those labels without a translation provider, and generic row/value types remain intact

#### Scenario: Unsupported public types are rejected
- **WHEN** a consumer supplies an unsupported icon, invalid table value, or unsupported badge tone
- **THEN** TypeScript rejects the assignment without exposing application-only types

### Requirement: Hosted application UI extension has packed-consumer evidence

The alpha.3 archive SHALL retain all existing archive, runtime/declaration closure, source-isolation, React peer, asset/license, and scoped-style guarantees. Validators and the installed isolated React consumer SHALL cover every newly public component and relevant public type with positive and type-negative cases. Browser smoke SHALL render every added component in both themes and exercise forms, disclosure, row activation/sorting/pagination, file selection, overlay drawer dismissal, and toast dismissal/expiry. Canonical-source changes MUST select package validation in CI. UI release metadata SHALL identify `0.1.0-alpha.3` without changing unrelated package coordinates or bypassing protected publication.

#### Scenario: The expanded packed surface works outside the checkout
- **WHEN** the generated alpha.3 tarball is installed in the separately provisioned isolated consumer
- **THEN** all added exports type-check, build, render, and pass representative interaction checks without source or network fallback

#### Scenario: A transitive input or public export is missing
- **WHEN** a candidate omits an added export, declaration, style, or required internal dependency
- **THEN** archive or isolated-consumer validation rejects the candidate

### Requirement: Consumers control row activation and outcome presentation

The shared UI SHALL let consumers activate a typed table row by pointer without also activating its embedded controls. Activatable rows SHALL NOT be keyboard focus targets; consumers provide an equivalent control inside the row. Consumer-owned drawer close labels SHALL determine the accessible close action name. KPI values SHALL support the shared semantic outcome tones, preserving neutral defaults and visible labels/counts.

#### Scenario: Row activation is isolated
- **WHEN** a consumer clicks a row cell
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

## REMOVED Requirements

### Requirement: Hosted overlay drawer and toasts remain independently usable
**Reason**: The toast error-copy action is no longer part of the hosted contract; no hosted consumer copies errors.
**Migration**: Use the dismissible ToastProvider/useToast; FRED keeps its internal copy action.

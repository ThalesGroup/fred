## ADDED Requirements

### Requirement: The hosted UI surface follows its consumers

The `@fred-oss/ui` hosted surface SHALL expose only the components and props a hosted application uses. A new export or prop SHALL be added with the consuming use case. FRED-internal variants of a canonical component MAY remain outside the public types.

#### Scenario: An internal variant is requested by a hosted consumer
- **WHEN** a hosted application needs a prop that is not public
- **THEN** the prop is added to the public type together with that use case and its packed-consumer evidence

#### Scenario: Internal-only props are rejected
- **WHEN** a consumer passes row selection to `DataTable` or a push, resizable or floating layout to `InlineDrawer`
- **THEN** TypeScript rejects the assignment

### Requirement: Hosted overlay drawer and toasts remain independently usable

The public InlineDrawer SHALL be a single overlay drawer accepting `open`, `onClose`, `title`, `closeLabel`, `width`, `headerActions` and children, closing on its close action, backdrop or Escape, without application state dependencies. Nested hosted drawers are not supported. ToastProvider and `useToast` SHALL retain severity, dismissal, expiry, and error-copy behavior through a caller-supplied copy action. Toast action names SHALL be caller-configurable. FRED SHALL supply its existing clipboard action. Visible content MUST retain consumer-root styles and light/dark theme inheritance.

#### Scenario: Overlay drawer is dismissed
- **WHEN** a consumer opens the overlay drawer and presses Escape or activates its labelled close action
- **THEN** the drawer closes through the consumer's `onClose`

#### Scenario: Toast copy and lifecycle are driven by the consumer
- **WHEN** a consumer displays an error toast and activates its labelled copy or dismiss action, or a timed toast expires
- **THEN** copy invokes the supplied action with the error text and dismissal/expiry removes the correct toast

## MODIFIED Requirements

### Requirement: Extended UI components have neutral localized contracts

The extended UI surface MUST work without FRED aliases, application models, translation providers, routing, or task stores. Exported declarations MUST NOT reference `IconType`, `OptionModel`, or `react-i18next`. Icon-bearing props SHALL accept only the supported Material Symbols contract. KpiStatCard and DataTable SHALL accept caller-owned state and pagination labels, including count-dependent text. Table options SHALL preserve their numeric value typing. Internal Dialog, drawer and pagination buttons SHALL NOT submit an enclosing form. Switch SHALL NOT accept `type`, `children` or `dangerouslySetInnerHTML`. Existing FRED consumers SHALL retain their translated labels and current interactions.

#### Scenario: Independent consumer supplies localized labels
- **WHEN** a consumer renders loading/error/no-data KPI states and paginated tables with its own labels
- **THEN** visible text and accessible action names use those labels without a translation provider, and generic row/value types remain intact

#### Scenario: Unsupported public types are rejected
- **WHEN** a consumer supplies an unsupported icon, invalid table value, or unsupported badge tone
- **THEN** TypeScript rejects the assignment without exposing application-only types

### Requirement: Hosted application UI extension has packed-consumer evidence

The alpha.3 archive SHALL retain all existing archive, runtime/declaration closure, source-isolation, React peer, asset/license, and scoped-style guarantees. Validators and the installed isolated React consumer SHALL cover every newly public component and relevant public type with positive and type-negative cases. Browser smoke SHALL render every added component in both themes and exercise forms, disclosure, row activation/sorting/pagination, file selection, overlay drawer dismissal, and toast copy/dismissal/expiry. Canonical-source changes MUST select package validation in CI. UI release metadata SHALL identify `0.1.0-alpha.3` without changing unrelated package coordinates or bypassing protected publication.

#### Scenario: The expanded packed surface works outside the checkout
- **WHEN** the generated alpha.3 tarball is installed in the separately provisioned isolated consumer
- **THEN** all added exports type-check, build, render, and pass representative interaction checks without source or network fallback

#### Scenario: A transitive input or public export is missing
- **WHEN** a candidate omits an added export, declaration, style, or required internal dependency
- **THEN** archive or isolated-consumer validation rejects the candidate

### Requirement: Consumers control row activation and outcome presentation

The shared UI SHALL let consumers activate a typed table row by pointer or keyboard without also activating its embedded controls. Consumer-owned drawer close labels SHALL determine the accessible close action name. KPI values SHALL support the shared semantic outcome tones, preserving neutral defaults and visible labels/counts.

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

## REMOVED Requirements

### Requirement: Drawer and toast behavior remains independently usable
**Reason**: Push, resizable and floating drawers and the direct Toast are FRED-internal; no hosted consumer uses them.
**Migration**: Use the overlay InlineDrawer and ToastProvider/useToast.

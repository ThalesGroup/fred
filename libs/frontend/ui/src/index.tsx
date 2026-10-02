// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import CanonicalButton, {
  type ButtonProps as CanonicalButtonProps,
} from "../.generated/src/rework/components/shared/atoms/Button/Button.tsx";
import {
  MaterialIcon,
  type MaterialIconProps,
} from "../.generated/src/rework/components/shared/atoms/Icon/Icon.tsx";
import CanonicalIconButton, {
  type IconButtonProps as CanonicalIconButtonProps,
} from "../.generated/src/rework/components/shared/atoms/IconButton/IconButton.tsx";
import {
  Spinner,
  type SpinnerProps,
} from "../.generated/src/rework/components/shared/atoms/Spinner/Spinner.tsx";
import CanonicalTextInput, {
  type TextInputProps as CanonicalTextInputProps,
} from "../.generated/src/rework/components/shared/atoms/TextInput/TextInput.tsx";
import CanonicalCheckbox, {
  type CheckboxProps,
} from "../.generated/src/rework/components/shared/atoms/Checkbox/Checkbox.tsx";
import CanonicalChip, {
  type ChipProps,
} from "../.generated/src/rework/components/shared/atoms/Chip/Chip.tsx";
import {
  Tooltip,
  type TooltipProps,
} from "../.generated/src/rework/components/shared/atoms/Tooltip/Tooltip.tsx";
import {
  DialogPrimitive,
  type DialogProps,
} from "../.generated/src/rework/components/shared/molecules/Dialog/DialogPrimitive.tsx";
import CanonicalSelect, {
  type SelectOption,
  type SelectProps,
} from "../.generated/src/rework/components/shared/molecules/Select/Select.tsx";
import type {
  ButtonSize,
  ButtonVariant,
  ColorTheme,
  IconButtonVariant,
  MaterialIconType,
} from "../.generated/src/rework/components/shared/utils/Type.ts";
import CanonicalDataTable, {
  type DataTableLabels as CanonicalDataTableLabels,
  type DataTableProps as CanonicalDataTableProps,
  type SortState,
} from "../.generated/src/rework/components/shared/molecules/DataTable/DataTable.tsx";
import CanonicalTextArea, {
  type TextAreaProps as CanonicalTextAreaProps,
} from "../.generated/src/rework/components/shared/atoms/TextArea/TextArea.tsx";
import {
  ToastProvider as CanonicalToastProvider,
  type ToastProviderProps as CanonicalToastProviderProps,
} from "../.generated/src/rework/components/shared/molecules/Toast/ToastProvider.tsx";
import {
  InlineDrawer as CanonicalInlineDrawer,
  type InlineDrawerProps as CanonicalInlineDrawerProps,
} from "../.generated/src/rework/components/shared/molecules/InlineDrawer/InlineDrawer.tsx";
import type { PropsWithChildren, ReactElement } from "react";
import "../.generated/base.css";

export type IconProps = MaterialIconProps;

export interface ButtonProps extends Omit<CanonicalButtonProps, "icon"> {
  icon?: MaterialIconProps;
}

export interface IconButtonProps extends Omit<
  CanonicalIconButtonProps,
  "icon"
> {
  icon: MaterialIconProps;
}

export interface TextInputProps extends Omit<CanonicalTextInputProps, "icon"> {
  icon?: MaterialIconProps;
}

export function Icon(props: MaterialIconProps) {
  return <MaterialIcon {...props} />;
}

export function Button({ icon, ...props }: ButtonProps) {
  return <CanonicalButton {...props} icon={icon} />;
}

export function IconButton({ icon, ...props }: IconButtonProps) {
  return <CanonicalIconButton {...props} icon={icon} />;
}

export function TextInput({ icon, ...props }: TextInputProps) {
  return <CanonicalTextInput {...props} icon={icon} />;
}

export { Spinner };
export {
  CanonicalCheckbox as Checkbox,
  CanonicalChip as Chip,
  DialogPrimitive as Dialog,
  CanonicalSelect as Select,
  Tooltip,
};
export type {
  ButtonSize,
  ButtonVariant,
  ColorTheme,
  IconButtonVariant,
  MaterialIconType,
  SpinnerProps,
  CheckboxProps,
  ChipProps,
  DialogProps,
  SelectOption,
  SelectProps,
  TooltipProps,
};

// Controlled only: the character counter reads `value`, and the label owns the id.
export type TextAreaProps = Omit<
  CanonicalTextAreaProps,
  "value" | "defaultValue" | "onChange" | "id"
> & {
  value: string;
  onChange: NonNullable<CanonicalTextAreaProps["onChange"]>;
};
export const TextArea: (props: TextAreaProps) => ReactElement =
  CanonicalTextArea;

export { default as Switch } from "../.generated/src/rework/components/shared/atoms/Switch/Switch.tsx";
export type {
  SwitchProps,
  SwitchSize,
} from "../.generated/src/rework/components/shared/atoms/Switch/Switch.tsx";

export { default as ProgressBar } from "../.generated/src/rework/components/shared/atoms/ProgressBar/ProgressBar.tsx";
export type { ProgressBarProps } from "../.generated/src/rework/components/shared/atoms/ProgressBar/ProgressBar.tsx";

export { IndicatorDot } from "../.generated/src/rework/components/shared/atoms/IndicatorDot/IndicatorDot.tsx";
export type {
  IndicatorDotProps,
  IndicatorStatus,
} from "../.generated/src/rework/components/shared/atoms/IndicatorDot/IndicatorDot.tsx";

export { default as Disclosure } from "../.generated/src/rework/components/shared/atoms/Disclosure/Disclosure.tsx";
export type { DisclosureProps } from "../.generated/src/rework/components/shared/atoms/Disclosure/Disclosure.tsx";

export { default as StatusBadge } from "../.generated/src/rework/components/shared/atoms/StatusBadge/StatusBadge.tsx";
export type {
  StatusBadgeProps,
  StatusBadgeTone,
} from "../.generated/src/rework/components/shared/atoms/StatusBadge/StatusBadge.tsx";

export { Breadcrumb } from "../.generated/src/rework/components/shared/molecules/Breadcrumb/Breadcrumb.tsx";
export type {
  BreadcrumbProps,
  BreadcrumbSegment,
} from "../.generated/src/rework/components/shared/molecules/Breadcrumb/Breadcrumb.tsx";

export { default as PageHeader } from "../.generated/src/rework/components/shared/molecules/PageHeader/PageHeader.tsx";
export type { PageHeaderProps } from "../.generated/src/rework/components/shared/molecules/PageHeader/PageHeader.tsx";

export { default as SelectableCard } from "../.generated/src/rework/components/shared/molecules/SelectableCard/SelectableCard.tsx";
export type { SelectableCardProps } from "../.generated/src/rework/components/shared/molecules/SelectableCard/SelectableCard.tsx";

export { default as FileDropzone } from "../.generated/src/rework/components/shared/molecules/FileDropzone/FileDropzone.tsx";
export type { FileDropzoneProps } from "../.generated/src/rework/components/shared/molecules/FileDropzone/FileDropzone.tsx";

export { default as ServiceNotice } from "../.generated/src/rework/components/shared/molecules/ServiceNotice/ServiceNotice.tsx";
export type { ServiceNoticeProps } from "../.generated/src/rework/components/shared/molecules/ServiceNotice/ServiceNotice.tsx";

export { default as PageEmptyState } from "../.generated/src/rework/components/shared/molecules/PageEmptyState/PageEmptyState.tsx";
export type {
  PageEmptyStateProps,
  PageEmptyStateAction,
} from "../.generated/src/rework/components/shared/molecules/PageEmptyState/PageEmptyState.tsx";

export { default as KpiStatCard } from "../.generated/src/rework/components/shared/molecules/KpiStatCard/KpiStatCard.tsx";
export type { KpiStatCardProps } from "../.generated/src/rework/components/shared/molecules/KpiStatCard/KpiStatCard.tsx";

// Hosted consumers need display, sorting, pagination and row activation, not selection.
export type DataTableLabels = Pick<CanonicalDataTableLabels, "pagination">;
// Controlled sorting needs both props; omitting both keeps internal sorting.
type DataTableSortProps =
  | { sortState?: undefined; onSortChange?: undefined }
  | {
      sortState: SortState | null;
      onSortChange: (next: SortState | null) => void;
    };
export type DataTableProps<T> = Omit<
  CanonicalDataTableProps<T>,
  | "selectable"
  | "selectedKeys"
  | "onSelectionChange"
  | "labels"
  | "sortState"
  | "onSortChange"
> & { labels?: Partial<DataTableLabels> } & DataTableSortProps;
export const DataTable: <T>(props: DataTableProps<T>) => ReactElement =
  CanonicalDataTable;
export type {
  DataTableColumn,
  DataTableRowSize,
  ServerPagination,
  SortState,
  SortDirection,
} from "../.generated/src/rework/components/shared/molecules/DataTable/DataTable.tsx";

export type { TablePaginationLabels } from "../.generated/src/rework/components/shared/molecules/TablePagination/TablePagination.tsx";

// Hosted drawers are single overlays; push, resize and floating layouts stay FRED-internal.
export type InlineDrawerProps = PropsWithChildren<
  Pick<
    CanonicalInlineDrawerProps,
    "open" | "onClose" | "title" | "closeLabel" | "width" | "headerActions"
  >
>;
export const InlineDrawer: (props: InlineDrawerProps) => ReactElement =
  CanonicalInlineDrawer;

export type { ToastSeverity } from "../.generated/src/rework/components/shared/molecules/Toast/Toast.tsx";

// Hosted toasts are dismissed, not copied; the copy action stays FRED-internal.
export type ToastProviderProps = Omit<
  CanonicalToastProviderProps,
  "onCopy" | "copyLabel"
>;
export const ToastProvider: (props: ToastProviderProps) => ReactElement =
  CanonicalToastProvider;
export { useToast } from "../.generated/src/rework/components/shared/molecules/Toast/ToastProvider.tsx";
export type {
  ToastInput,
  ToastContextValue,
} from "../.generated/src/rework/components/shared/molecules/Toast/ToastProvider.tsx";

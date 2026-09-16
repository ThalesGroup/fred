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

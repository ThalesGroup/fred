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
export type {
  ButtonSize,
  ButtonVariant,
  ColorTheme,
  IconButtonVariant,
  MaterialIconType,
  SpinnerProps,
};

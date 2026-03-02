import { IconProps } from "@shared/atoms/Icon/Icon.tsx";

export interface OptionModel<T = string> {
  value: T;
  label: string;
  icon?: IconProps;
  disabled?: boolean;
  metadata?: Record<string, unknown>;
  onClick?: () => void;
}

import { IconProps } from "@shared/atoms/Icon/Icon.tsx";

export interface OptionModel<T = string> {
  value: T;
  label: string;
  key: string;
  icon?: IconProps;
  disabled?: boolean;
}

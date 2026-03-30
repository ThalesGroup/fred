import { IconProps } from "@shared/atoms/Icon/Icon.tsx";

export interface OptionModel<T = string> {
  value: T;
  label: string;
  key: string;
  icon?: IconProps;
  disabled?: boolean;
  /** Short description shown in a simple tooltip on hover. */
  tooltip?: string;
  /**
   * When set alongside `tooltip`, renders a detailed tooltip with this as the
   * bold title and `tooltip` as the indented description body.
   */
  tooltipLabel?: string;
}

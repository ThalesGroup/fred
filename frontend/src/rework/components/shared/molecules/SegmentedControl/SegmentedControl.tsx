import styles from "./SegmentedControl.module.scss";
import ButtonGroupItem from "@shared/atoms/ButtonGroup/ButtonGroupItem/ButtonGroupItem.tsx";
import Tooltip from "@shared/atoms/Tooltip/Tooltip.tsx";
import { ComponentSize, ColorTheme } from "@shared/utils/Type.ts";
import { OptionModel } from "@models/Option.model.ts";

/**
 * Layout of the label relative to the button group.
 * - `"vertical"`   — label above buttons (default, good for standalone controls)
 * - `"horizontal"` — label inline to the left of buttons (good for compact rows)
 */
type SegmentedControlDirection = "vertical" | "horizontal";

interface SegmentedControlProps<T> {
  options: OptionModel<T>[];
  value: T;
  onChange: (value: T) => void;
  size: ComponentSize;
  color: ColorTheme;
  label?: string;
  hint?: string;
  /** Controls whether the label sits above or inline with the buttons. Defaults to "vertical". */
  direction?: SegmentedControlDirection;
}

export default function SegmentedControl<T>({
  options,
  value,
  onChange,
  size,
  color,
  label,
  hint,
  direction = "vertical",
}: SegmentedControlProps<T>) {
  return (
    <div className={styles["segmented-control"]} data-direction={direction}>
      {label && <span className={styles["label"]}>{label}</span>}
      <div className={styles["button-group"]}>
        {options.map((option) => {
          const item = (
            <ButtonGroupItem
              key={option.key}
              label={option.label}
              icon={option.icon}
              size={size}
              color={color}
              selected={option.value === value}
              disabled={option.disabled}
              onClick={() => !option.disabled && onChange(option.value)}
            />
          );
          if (option.tooltipLabel && option.tooltip) {
            return (
              <Tooltip key={option.key} variant="detailed" label={option.tooltipLabel} description={option.tooltip} placement="bottom">
                {item}
              </Tooltip>
            );
          }
          if (option.tooltip) {
            return (
              <Tooltip key={option.key} title={option.tooltip} placement="bottom">
                {item}
              </Tooltip>
            );
          }
          return item;
        })}
      </div>
      {hint && <span className={styles["hint"]}>{hint}</span>}
    </div>
  );
}

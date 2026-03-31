import { cloneElement, CSSProperties, HTMLAttributes, ReactElement, useId, useRef } from "react";
import styles from "./Tooltip.module.scss";

interface TooltipProps {
  text: string;
  children: ReactElement<HTMLAttributes<HTMLElement>>;
}

export const Tooltip = ({ text, children }: TooltipProps) => {
  const tooltipId = useId();
  const popoverRef = useRef<HTMLDivElement>(null);
  const anchorName = `--anchor-${tooltipId.replace(/:/g, "")}`;

  const childProps = children.props as HTMLAttributes<HTMLElement>;

  const tooltipHandlers = {
    style: {
      ...childProps.style,
      anchorName: anchorName,
    } as CSSProperties,
    onMouseEnter: () => popoverRef.current?.showPopover(),
    onMouseLeave: () => popoverRef.current?.hidePopover(),
    onFocus: () => popoverRef.current?.showPopover(),
    onBlur: () => popoverRef.current?.hidePopover(),
  };

  return (
    <>
      {cloneElement(children, tooltipHandlers)}

      <div
        ref={popoverRef}
        id={tooltipId}
        popover="manual"
        style={{ positionAnchor: anchorName } as CSSProperties}
        className={styles["tooltip-content"]}
      >
        {text}
      </div>
    </>
  );
};

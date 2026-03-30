import styles from "./Tooltip.module.scss";
import { Portal } from "@shared/utils/Portal.tsx";
import { useCallback, useEffect, useRef, useState } from "react";

export type TooltipPlacement =
  | "top" | "top-start" | "top-end"
  | "bottom" | "bottom-start" | "bottom-end"
  | "left" | "left-start"
  | "right" | "right-start";

const DELAY_MS = 800;
const GAP_PX = 8;

interface TooltipBaseProps {
  children: React.ReactNode;
  placement?: TooltipPlacement;
  maxWidth?: number;
}

interface SimpleTooltipProps extends TooltipBaseProps {
  variant?: "simple";
  title: string;
}

interface DetailedTooltipProps extends TooltipBaseProps {
  variant: "detailed";
  label: string;
  description: string;
  disabledReason?: string;
}

export type TooltipProps = SimpleTooltipProps | DetailedTooltipProps;

function computePosition(rect: DOMRect, placement: TooltipPlacement): React.CSSProperties {
  switch (placement) {
    case "top":
      return { top: rect.top - GAP_PX, left: rect.left + rect.width / 2, transform: "translateX(-50%) translateY(-100%)" };
    case "top-start":
      return { top: rect.top - GAP_PX, left: rect.left, transform: "translateY(-100%)" };
    case "top-end":
      return { top: rect.top - GAP_PX, left: rect.right, transform: "translateX(-100%) translateY(-100%)" };
    case "bottom":
      return { top: rect.bottom + GAP_PX, left: rect.left + rect.width / 2, transform: "translateX(-50%)" };
    case "bottom-start":
      return { top: rect.bottom + GAP_PX, left: rect.left };
    case "bottom-end":
      return { top: rect.bottom + GAP_PX, left: rect.right, transform: "translateX(-100%)" };
    case "left":
      return { top: rect.top + rect.height / 2, left: rect.left - GAP_PX, transform: "translateX(-100%) translateY(-50%)" };
    case "left-start":
      return { top: rect.top, left: rect.left - GAP_PX, transform: "translateX(-100%)" };
    case "right":
      return { top: rect.top + rect.height / 2, left: rect.right + GAP_PX, transform: "translateY(-50%)" };
    case "right-start":
      return { top: rect.top, left: rect.right + GAP_PX };
  }
}

export default function Tooltip(props: TooltipProps) {
  const { children, placement = "top", maxWidth } = props;
  const [isOpen, setIsOpen] = useState(false);
  const [bubbleStyle, setBubbleStyle] = useState<React.CSSProperties>({});
  const anchorRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const open = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      if (anchorRef.current) {
        const rect = anchorRef.current.getBoundingClientRect();
        setBubbleStyle({ position: "fixed", ...computePosition(rect, placement) });
      }
      setIsOpen(true);
    }, DELAY_MS);
  }, [placement]);

  const close = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    setIsOpen(false);
  }, []);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return (
    <div
      ref={anchorRef}
      className={styles["tooltip-anchor"]}
      onMouseEnter={open}
      onMouseLeave={close}
      onFocus={open}
      onBlur={close}
    >
      {children}
      {isOpen && (
        <Portal id="tooltip-root">
          <div
            className={styles["bubble"]}
            role="tooltip"
            data-placement={placement}
            style={{ ...bubbleStyle, ...(maxWidth ? { maxWidth } : {}) }}
          >
            <div className={styles["arrow"]} data-placement={placement} />
            {props.variant === "detailed" ? (
              <div className={styles["content"]}>
                <span className={styles["label"]}>{props.label}</span>
                <span className={styles["description"]}>{props.description}</span>
                {props.disabledReason && (
                  <span className={styles["disabled-reason"]}>{props.disabledReason}</span>
                )}
              </div>
            ) : (
              <span className={styles["title"]}>{(props as SimpleTooltipProps).title}</span>
            )}
          </div>
        </Portal>
      )}
    </div>
  );
}

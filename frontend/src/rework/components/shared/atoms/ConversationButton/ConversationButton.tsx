import { ComponentPropsWithoutRef, PropsWithChildren } from "react";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";
import styles from "./ConversationButton.module.scss";

interface ConversationButtonProps extends PropsWithChildren<ComponentPropsWithoutRef<"button">> {
  icon?: IconProps;
}

export default function ConversationButton({ children, icon, ...props }: ConversationButtonProps) {
  return (
    <button className={styles["conversation-btn"]} {...props}>
      {icon && (
        <span className={styles["conversation-btn-icon"]}>
          <Icon {...icon} />
        </span>
      )}
      {children}
    </button>
  );
}

import React, { ComponentPropsWithoutRef } from "react";
import Icon, { IconProps } from "@shared/atoms/Icon/Icon.tsx";
import styles from "./ConversationButton.module.scss";

interface ConversationButtonProps extends ComponentPropsWithoutRef<"button"> {
  children: React.ReactNode;
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

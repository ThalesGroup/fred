import { getInitials } from "../../../../../utils/getInitials.ts";
import styles from "./UserAvatar.module.scss";

export interface UserAvatarProps {
  name: string;
  size: "x-small" | "small" | "medium" | "large";
  tooltip?: boolean;
}

export default function UserAvatar({ name, size, tooltip = false, ...props }: UserAvatarProps) {
  return (
    <div className={styles["user-avatar"]} data-size={size} {...props}>
      {getInitials(name)}
      {tooltip && (
        <span className={styles["user-avatar-tooltip"]}>
        </span>
      )}
    </div>
  );
}

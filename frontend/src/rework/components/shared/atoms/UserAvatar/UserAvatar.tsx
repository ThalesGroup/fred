import { getInitials } from "../../../../../utils/getInitials.ts";
import styles from "./UserAvatar.module.scss";

export interface UserAvatarProps {
  name: string;
  size: "x-small" | "small" | "medium" | "large";
}

export default function UserAvatar({ name, size, ...props }: UserAvatarProps) {
  return (
    <div className={styles["user-avatar"]} data-size={size} {...props}>
      {getInitials(name)}
    </div>
  );
}

import { getInitials } from "../../../../../utils/getInitials.ts";
import styles from "./UserAvatar.module.css";

export interface UserAvatarProps {
  name: string;
  size: "x-small" | "small" | "medium" | "large";
}

export default function UserAvatar({ name, size, ...props }: UserAvatarProps) {
  return (
    <div className={styles.userAvatar} data-size={size} {...props}>
      {getInitials(name)}
    </div>
  );
}

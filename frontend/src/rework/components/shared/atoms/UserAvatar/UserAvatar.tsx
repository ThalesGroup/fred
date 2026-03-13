import { getInitials } from "../../../../../utils/getInitials.ts";
import styles from "./UserAvatar.module.scss";

interface UserAvatarProps {
  name: string;
  size: "x-small" | "small" | "medium" | "large";
}

export default function UserAvatar({ name, size }: UserAvatarProps) {
  return (
    <div className={styles["user-avatar"]} data-size={size}>
      {getInitials(name)}
    </div>
  );
}

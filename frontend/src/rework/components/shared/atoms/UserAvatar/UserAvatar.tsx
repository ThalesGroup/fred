import {getInitials} from "../../../../../utils/getInitials.ts";
import styles from "./UserAvatar.module.scss";

interface UserAvatarProps {
    name: string;
}

export default function UserAvatar({ name }: UserAvatarProps) {
    return (
        <div className={styles["user-avatar"]}>{getInitials(name)}</div>
    )
}
import styles from "./AvatarGroup.module.scss";
import UserAvatar, { UserAvatarProps } from "@shared/atoms/UserAvatar/UserAvatar.tsx";
import {Tooltip} from "@shared/atoms/Tooltip/Tooltip.tsx";

interface AvatarGroupProps {
  avatars: UserAvatarProps[];
  tooltip?: boolean;
}

export default function AvatarGroup({ avatars, tooltip = false }: AvatarGroupProps) {
  return (
    <div className={styles["user-avatar-container"]}>
      {avatars.map((avatar, index) => (
        <Tooltip key={index} text={avatar.name}>
            <UserAvatar tooltip={tooltip} {...avatar} />
        </Tooltip>
      ))}
    </div>
  );
}

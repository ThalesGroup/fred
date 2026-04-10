import styles from "./AvatarGroup.module.scss";
import UserAvatar, { UserAvatarProps } from "@shared/atoms/UserAvatar/UserAvatar.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";

interface AvatarGroupProps {
  avatars: Omit<UserAvatarProps, "size">[];
}

export default function AvatarGroup({ avatars }: AvatarGroupProps) {
  return (
    <div className={styles.userAvatarContainer}>
      {avatars.length > 4 && <UserAvatar name={`+ ${(avatars.length - 4).toString()}`} size={"small"} />}
      {avatars.slice(0, 4).map((avatar, index) => (
        <Tooltip key={index} text={avatar.name}>
          <UserAvatar size={"small"} {...avatar} />
        </Tooltip>
      ))}
    </div>
  );
}

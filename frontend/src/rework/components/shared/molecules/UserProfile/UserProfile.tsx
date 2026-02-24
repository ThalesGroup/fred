import styles from "./UserProfile.module.scss";
import { KeyCloakService } from "../../../../../security/KeycloakService.ts";
import UserAvatar from "@shared/atoms/UserAvatar/UserAvatar.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";

export default function UserProfile() {
  const userFullName = KeyCloakService.GetUserFullName();
  const username = KeyCloakService.GetUserName();

  return (
    <div className={styles["user-profile"]}>
      <UserAvatar name={userFullName} />
      <span className={styles["user-identity"]}>
        <span className={styles["user-identity-name"]}>{userFullName}</span>
        <span className={styles["user-identity-id"]}>{username}</span>
      </span>
        <IconButton
          color={"primary"}
          variant={"icon"}
          size={"medium"}
          icon={{ category: "outlined", type: "Settings", filled: true }}
        />
    </div>
  );
}

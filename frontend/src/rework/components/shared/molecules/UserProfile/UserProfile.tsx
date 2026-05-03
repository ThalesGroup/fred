import styles from "./UserProfile.module.scss";
import { KeyCloakService } from "../../../../../security/KeycloakService.ts";
import UserAvatar from "@shared/atoms/UserAvatar/UserAvatar.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { useNavigate } from "react-router-dom";

export default function UserProfile() {
  const navigate = useNavigate();
  const userFullName = KeyCloakService.GetUserFullName();
  const username = KeyCloakService.GetUserName();

  return (
    <div className={styles["user-profile"]}>
      <UserAvatar name={userFullName} size={"medium"} />
      <span className={styles["user-identity"]}>
        <span className={styles["user-identity-name"]}>{userFullName}</span>
        <span className={styles["user-identity-id"]}>{username}</span>
      </span>
      <span className={styles["user-settings-button"]}>
        <IconButton
          color={"on-surface-retreat"}
          variant={"icon"}
          size={"medium"}
          icon={{ category: "outlined", type: "settings", filled: true }}
          onClick={() => navigate("/settings")}
          aria-label="Open user settings"
        />
      </span>
    </div>
  );
}

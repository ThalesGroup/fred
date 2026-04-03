import styles from "./UserProfile.module.scss";
import { KeyCloakService } from "../../../../../security/KeycloakService.ts";
import UserAvatar from "@shared/atoms/UserAvatar/UserAvatar.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { useState } from "react";
import { FullPageModal } from "@shared/molecules/FullPageModal/FullPageModal.tsx";
import UserSettingsPage from "@components/pages/UserSettingsPage/UserSettingsPage.tsx";

export default function UserProfile() {
  const [isUserSettingsOpen, setIsUserSettingsOpen] = useState(false);
  const userFullName = KeyCloakService.GetUserFullName();
  const username = KeyCloakService.GetUserName();

  return (
    <>
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
            icon={{ category: "outlined", type: "Settings", filled: true }}
            onClick={() => setIsUserSettingsOpen(true)}
            aria-label="Open user settings"
          />
        </span>
      </div>
      <FullPageModal
        isOpen={isUserSettingsOpen}
        onClose={() => setIsUserSettingsOpen(false)}
        id={"user-settings-modal"}
      >
        <UserSettingsPage modalInteraction={{ close: () => setIsUserSettingsOpen(false) }} />
      </FullPageModal>
    </>
  );
}

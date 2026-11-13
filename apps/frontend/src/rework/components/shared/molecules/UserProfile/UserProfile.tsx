// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import styles from "./UserProfile.module.scss";
import { KeyCloakService } from "../../../../../security/KeycloakService.ts";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import UserAvatar from "@shared/atoms/UserAvatar/UserAvatar.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import MenuPopover from "@shared/molecules/MenuPopover/MenuPopover.tsx";
import { useGetMyAvatarQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { usePatchNoteHistory } from "../../../../features/announcements/usePatchNoteHistory";
import { PatchNoteDialog } from "@shared/molecules/PatchNoteDialog/PatchNoteDialog";
import MenuPopoverItem from "@shared/molecules/MenuPopover/MenuPopoverItem.tsx";

import { useWorkingOrganization } from "@core/hooks/useWorkingOrganization";

/** Only the admitted section reads the working context; logout stays available before admission. */
export default function UserProfile({
  admitted = false,
  agentManagement = false,
  platformArea = false,
  organizationArea = false,
}: {
  admitted?: boolean;
  agentManagement?: boolean;
  platformArea?: boolean;
  organizationArea?: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { contactSupportLink } = useFrontendProperties();
  const [open, setOpen] = useState(false);
  const { currentData: pictureUrl } = useGetMyAvatarQuery(undefined, {
    skip: !admitted,
    refetchOnMountOrArgChange: 60,
  });
  const { notes: patchNotes } = usePatchNoteHistory(!admitted || platformArea || organizationArea || agentManagement);
  const [readingPatchNotes, setReadingPatchNotes] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const userFullName =
    KeyCloakService.GetUserFullName() || KeyCloakService.GetUserName() || KeyCloakService.GetUserId();
  const userEmail = KeyCloakService.GetUserMail();

  useEffect(() => {
    if (!open) return;
    const onPointer = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className={styles.container} ref={containerRef}>
      {open && (
        <div
          className={styles.popoverWrap}
          onKeyDown={(event) => {
            if (event.key === "Tab") return setOpen(false);
            const items = [
              ...event.currentTarget.querySelectorAll<HTMLButtonElement>('button[role^="menuitem"]:not([disabled])'),
            ];
            const index = items.indexOf(document.activeElement as HTMLButtonElement);
            const next = { ArrowDown: index + 1, ArrowUp: index - 1, Home: 0, End: items.length - 1 }[event.key];
            if (next === undefined || !items.length) return;
            event.preventDefault();
            items[(next + items.length) % items.length].focus();
          }}
        >
          <MenuPopover
            className={styles.popoverBox}
            headerTitle={userFullName}
            headerSubtitle={userEmail}
            groups={[
              admitted
                ? [
                    <MenuPopoverItem
                      key="profile"
                      icon={{ category: "outlined", type: "person" }}
                      label={t("rework.profileMenu.profile")}
                      onClick={() => {
                        setOpen(false);
                        navigate("/settings");
                      }}
                    />,
                    ...(!platformArea && patchNotes.length > 0
                      ? [
                          <MenuPopoverItem
                            key="whatsNew"
                            icon={{ category: "outlined", type: "new_releases" }}
                            label={t("rework.profileMenu.whatsNew")}
                            onClick={() => {
                              setOpen(false);
                              setReadingPatchNotes(true);
                            }}
                          />,
                        ]
                      : []),
                  ]
                : [],
              admitted ? [<WorkingOrganizationMenu key="organization" onClose={() => setOpen(false)} />] : [],
              admitted && contactSupportLink
                ? [
                    <MenuPopoverItem
                      key="support"
                      icon={{ category: "outlined", type: "contact_support" }}
                      label={t("rework.profileMenu.contactSupport")}
                      onClick={() => {
                        setOpen(false);
                        window.open(contactSupportLink, "_blank", "noopener,noreferrer");
                      }}
                    />,
                  ]
                : [],
              [
                <MenuPopoverItem
                  key="logout"
                  icon={{ category: "outlined", type: "logout" }}
                  label={t("rework.userSettings.disconnect")}
                  danger
                  onClick={KeyCloakService.CallLogout}
                />,
              ],
            ]}
          />
        </div>
      )}

      <Tooltip text={t("rework.profileMenu.trigger", { name: userFullName })} placement="right">
        <button
          type="button"
          className={styles.trigger}
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-haspopup="menu"
          aria-label={t("rework.profileMenu.trigger", { name: userFullName })}
        >
          <UserAvatar name={userFullName} size="small" imageUrl={admitted ? pictureUrl || undefined : undefined} />
        </button>
      </Tooltip>
      {admitted && !platformArea && (
        <PatchNoteDialog open={readingPatchNotes} notes={patchNotes} onClose={() => setReadingPatchNotes(false)} />
      )}
    </div>
  );
}

function WorkingOrganizationMenu({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const id = useId();
  const context = useWorkingOrganization();
  const choices = context.organizations;
  return (
    <div role="group" aria-labelledby={id}>
      <div id={id} className={styles.organizationLabel}>
        {t("rework.profileMenu.workingOrganization")}
      </div>
      {context.error || context.loading || !choices.length ? (
        <p className={styles.organizationLabel} role="status">
          {t(context.loading ? "common.loading" : "rework.manager.unavailable")}
        </p>
      ) : choices.length === 1 && context.organization ? (
        <div className={styles.organizationName} title={context.organization.name}>
          {context.organization.name}
        </div>
      ) : (
        choices.map((organization) => (
          <MenuPopoverItem
            key={organization.id}
            role="menuitemradio"
            label={organization.name}
            icon={{ category: "outlined", type: "groups" }}
            selected={organization.id === context.organizationId}
            trailingIcon={organization.id === context.organizationId ? "check" : undefined}
            onClick={() => {
              if (context.selectOrganization(organization.id)) {
                onClose();
                if (organization.id !== context.organizationId) navigate("/home");
              }
            }}
          />
        ))
      )}
    </div>
  );
}

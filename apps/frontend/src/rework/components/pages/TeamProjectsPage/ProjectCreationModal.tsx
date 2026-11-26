// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import TextInput from "@shared/atoms/TextInput/TextInput";
import AvatarUploadCard from "@shared/molecules/AvatarUploadCard/AvatarUploadCard";
import NavigationMenu from "@shared/molecules/NavigationMenu/NavigationMenu";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import SettingsModal from "@shared/organisms/SettingsModal/SettingsModal";
import TeamDescriptionField from "@shared/organisms/TeamSettingsPanel/TeamSettingsParameters/TeamDescriptionField";
import TeamDiscoveryFields from "@shared/organisms/TeamSettingsPanel/TeamSettingsParameters/TeamDiscoveryFields";
import {
  RetentionFields,
  retentionChoice,
  type RetentionMode,
} from "@shared/organisms/TeamSettingsPanel/TeamSettingsParameters/TeamConversationRetention";
import { normalizeApiError } from "@core/errors/normalizeApiError";
import { isValidTeamDescription, MAX_TEAM_NAME_LENGTH } from "@core/utils/teamFields";
import {
  useCreateSpaceMutation,
  usePutTeamAvatarMutation,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import {
  useTeamConversationRetentionQuery,
  type TeamJoiningMode,
  type TeamVisibility,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { KeyCloakService } from "../../../../security/KeycloakService";
import SpaceMemberPicker, { type PendingMember } from "../TeamSettingsPage/SpaceMemberPicker";
import styles from "./ProjectCreationModal.module.css";

// Sections are listed in order; a later section (a business workflow, say) adds an entry here.
const SECTIONS = [
  { key: "parameters", icon: "tune" },
  { key: "members", icon: "group" },
] as const;
type Section = (typeof SECTIONS)[number]["key"];

/** The team Owner names a new project's parameters and initial members, then creates it in one request. */
export default function ProjectCreationModal({
  teamId,
  teamName,
  onClose,
}: {
  teamId: string;
  teamName?: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const { showError } = useToast();
  const [section, setSection] = useState<Section>("parameters");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState<TeamVisibility>("hidden");
  const [joiningMode, setJoiningMode] = useState<TeamJoiningMode>("invite_only");
  const [retentionMode, setRetentionMode] = useState<RetentionMode>("inherit");
  const [retentionSeconds, setRetentionSeconds] = useState("");
  const [avatar, setAvatar] = useState<File>();
  const [members, setMembers] = useState<PendingMember[]>([]);
  const [attempted, setAttempted] = useState(false);
  const [error, setError] = useState<string>();
  const [create, creation] = useCreateSpaceMutation();
  const [uploadAvatar, uploading] = usePutTeamAvatarMutation();
  // The team's own delay is what a project follows by default, under the same organization ceiling.
  const teamRetention = useTeamConversationRetentionQuery({ id: teamId }, { refetchOnMountOrArgChange: true });
  const ceiling = teamRetention.currentData?.organization_ceiling_seconds;
  const teamSeconds = teamRetention.currentData?.configured_seconds ?? undefined;

  const preview = useMemo(() => (avatar ? URL.createObjectURL(avatar) : undefined), [avatar]);
  useEffect(() => () => (preview ? URL.revokeObjectURL(preview) : undefined), [preview]);

  const trimmedName = name.trim();
  const nameValid = [...trimmedName].length > 0 && [...trimmedName].length <= MAX_TEAM_NAME_LENGTH;
  const descriptionValid = isValidTeamDescription(description);
  const retention = retentionChoice(retentionMode, retentionSeconds, ceiling);
  const hasOwner = members.some((member) => member.roles.includes("owner"));
  // The avatar is uploaded once the project exists, which only one of its direct Owners may do.
  const ownsProject = (selection: PendingMember[]) => {
    const userId = KeyCloakService.GetUserId();
    return selection.some((member) => member.user.id === userId && member.roles.includes("owner"));
  };
  const canSetAvatar = ownsProject(members);
  const changeMembers = (selection: PendingMember[]) => {
    setMembers(selection);
    if (!ownsProject(selection)) setAvatar(undefined);
  };
  const invalid: Record<Section, boolean> = {
    parameters: !nameValid || !descriptionValid || !retention.valid,
    members: !hasOwner,
  };
  const busy = creation.isLoading || uploading.isLoading;

  const submit = async () => {
    if (busy) return;
    setAttempted(true);
    setError(undefined);
    const firstInvalid = SECTIONS.find(({ key }) => invalid[key]);
    if (firstInvalid) {
      setSection(firstInvalid.key);
      return;
    }
    let projectId: string;
    try {
      projectId = (
        await create({
          createSpace: {
            kind: "project",
            parent_id: teamId,
            name: trimmedName,
            description: description.trim(),
            visibility,
            joining_mode: joiningMode,
            conversation_retention_seconds: retention.configured ?? undefined,
            // A person given no role joins as a plain member.
            members: members.map((member) => ({
              user: member.user.id,
              roles: member.roles.length ? member.roles : ["member"],
            })),
          },
        }).unwrap()
      ).id;
    } catch (failure) {
      const { status, detail } = normalizeApiError(failure);
      if (status === 409 && detail?.startsWith("a space with this name")) {
        setSection("parameters");
        setError(t("rework.projectParameters.name.alreadyTaken"));
      } else if (status === 409 && detail?.startsWith("the user must first be a member")) {
        setSection("members");
        setError(t("rework.projectCreation.notEligible"));
      } else {
        setError(t("rework.projectCreation.failed"));
      }
      return;
    }
    if (avatar && canSetAvatar) {
      try {
        await uploadAvatar({ id: projectId, fileUpload: { file: avatar } }).unwrap();
      } catch {
        showError({ summary: t("rework.projectCreation.avatarFailed") });
      }
    }
    onClose();
  };

  return (
    <SettingsModal
      isOpen
      onClose={() => {
        if (!busy) onClose();
      }}
      id="project-creation-modal"
      title={t("rework.projectCreation.title")}
      subtitle={teamName ? t("rework.projectCreation.subtitle", { team: teamName }) : undefined}
      actions={
        <>
          <Button color="primary" variant="outlined" size="medium" disabled={busy} onClick={onClose}>
            {t("rework.cancel")}
          </Button>
          <Button
            color={attempted && (invalid.parameters || invalid.members) ? "warning" : "primary"}
            variant="filled"
            size="medium"
            disabled={busy}
            onClick={() => void submit()}
          >
            {t("rework.create")}
          </Button>
        </>
      }
    >
      <div className={styles.layout}>
        <nav className={styles.nav} aria-label={t("rework.projectCreation.sectionsAria")}>
          <NavigationMenu
            items={SECTIONS.map(({ key, icon }) => ({
              type: "button",
              label: t(`rework.projectCreation.sections.${key}`),
              icon: { category: "outlined", type: icon },
              selected: section === key,
              hasError: attempted && invalid[key],
              onClick: () => setSection(key),
            }))}
          />
        </nav>
        <div className={styles.form}>
          {attempted && (invalid.parameters || invalid.members) && (
            <span role="alert" className={styles.error}>
              {t("rework.projectCreation.validation")}
            </span>
          )}
          {error && (
            <span role="alert" className={styles.error}>
              {error}
            </span>
          )}
          {section === "parameters" ? (
            <>
              <TextInput
                label={t("rework.projectParameters.name.label")}
                explanation={t("rework.projectParameters.name.support")}
                value={name}
                required
                disabled={busy}
                error={attempted && !nameValid ? t("rework.projectCreation.nameRequired") : undefined}
                onChange={(event) => setName(event.target.value)}
              />
              <TeamDescriptionField
                project
                value={description}
                disabled={busy}
                invalid={(attempted || description !== "") && !descriptionValid}
                onChange={setDescription}
              />
              {canSetAvatar && (
                <AvatarUploadCard
                  title={t("rework.projectParameters.avatar")}
                  hint={t("rework.teamSettings.parameters.teamAvatar.hint")}
                  importLabel={t("rework.teamSettings.parameters.teamAvatar.import")}
                  emptyLabel={t("rework.teamSettings.parameters.teamAvatar.noAvatar")}
                  imageUrl={preview}
                  uploading={busy}
                  deleting={busy}
                  onUpload={async (file) => setAvatar(file)}
                  deleteLabel={t("common.delete")}
                  onDelete={() => setAvatar(undefined)}
                />
              )}
              <span className={styles.heading}>{t("rework.teamDiscovery.settingsTitle")}</span>
              <span className={styles.hint}>{t("rework.projectParameters.settingsHint")}</span>
              <TeamDiscoveryFields
                project
                visibility={visibility}
                joiningMode={joiningMode}
                disabled={busy}
                onVisibilityChange={setVisibility}
                onJoiningModeChange={setJoiningMode}
              />
              <span className={styles.heading}>{t("rework.teamRetention.title")}</span>
              <span className={styles.hint}>{t("rework.teamRetention.explanation")}</span>
              <RetentionFields
                mode={retentionMode}
                seconds={retentionSeconds}
                ceiling={ceiling}
                inheritedFromTeamSeconds={teamSeconds}
                disabled={busy}
                onModeChange={setRetentionMode}
                onSecondsChange={setRetentionSeconds}
              />
            </>
          ) : (
            <>
              <SpaceMemberPicker
                spaceId={teamId}
                source="roster"
                eligibility={t("rework.projectCreation.membersHint")}
                pending={members}
                onPendingChange={changeMembers}
                disabled={busy}
              />
              {attempted && !hasOwner && (
                <span role="alert" className={styles.error}>
                  {t("rework.projectCreation.ownerRequired")}
                </span>
              )}
            </>
          )}
        </div>
      </div>
    </SettingsModal>
  );
}

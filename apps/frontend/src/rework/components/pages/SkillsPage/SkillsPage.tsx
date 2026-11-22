// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useSpaceAccess } from "@core/hooks/useSpaceAccess";
import Button from "@shared/atoms/Button/Button";
import TextArea from "@shared/atoms/TextArea/TextArea";
import TextInput from "@shared/atoms/TextInput/TextInput";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { SkillFileView } from "@shared/molecules/SkillFileView/SkillFileView";
import { SwitchRow } from "@shared/molecules/SwitchRow/SwitchRow";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useMySpacesQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import {
  useSkillScopeQuery,
  useCreateSkillMutation,
  useGetSkillQuery,
  useDeleteSkillMutation,
  usePutSkillMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import MarketplaceProposalDialog from "../marketplace/MarketplaceProposalDialog";
import ResourceCard from "@shared/organisms/PromptCard/ResourceCard";
import SearchInput from "@shared/molecules/SearchInput/SearchInput";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState";
import { FullPageModal } from "@shared/molecules/FullPageModal/FullPageModal";
import Chip from "@shared/atoms/Chip/Chip";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import layout from "../PromptsPage/PromptsPage.module.scss";
import styles from "./SkillsPage.module.css";

export default function SkillsPage() {
  const { teamId } = useParams();
  const { t } = useTranslation();
  const spaces = useMySpacesQuery(undefined, { refetchOnMountOrArgChange: true });
  const space = spaces.currentData?.find((s) => (teamId === "personal" ? s.kind === "personal" : s.id === teamId));
  if (spaces.isError) return <ServiceNotice icon="info" title={t("rework.manager.unavailable")} />;
  if (!spaces.currentData) return <p role="status">{t("common.loading")}</p>;
  if (!space) return <ServiceNotice icon="lock" title={t("rework.weaverAgents.scopeUnavailable")} />;
  return (
    <SpaceSkills key={space.id} spaceId={space.id} spaceName={space.name} collectiveSpace={space.kind !== "personal"} />
  );
}

function SpaceSkills({
  spaceId,
  spaceName,
  collectiveSpace,
}: {
  spaceId: string;
  spaceName: string;
  collectiveSpace: boolean;
}) {
  const { t } = useTranslation();
  const read = useSpaceAccess(spaceId, "read");
  const write = useSpaceAccess(spaceId, "write");
  const list = useSkillScopeQuery(
    { spaceId },
    {
      ...crossSessionRefreshOptions(!read.allowed),
      refetchOnMountOrArgChange: true,
    },
  );
  useRefetchOnWindowFocus(list.refetch, !read.allowed);
  const [params] = useSearchParams();
  const [selected, setSelected] = useState<string | undefined>(params.get("resource") ?? undefined);
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState("");
  const skills = list.isError ? [] : (list.currentData?.skills ?? []);
  const selectedSkill = skills.find((skill) => skill.skill_id === selected);
  const inherited = selectedSkill && selectedSkill.space_id !== spaceId;
  const detail = useGetSkillQuery(
    { spaceId: selectedSkill?.space_id ?? spaceId, skillId: selected ?? "" },
    { skip: !selectedSkill || !read.allowed, refetchOnMountOrArgChange: true },
  );
  const [remove, removing] = useDeleteSkillMutation();
  const [error, setError] = useState(false);
  const { showConfirmationDialog } = useConfirmationDialog();
  const filtered = skills.filter((skill) =>
    [skill.name, skill.description, skill.space_name].some((value) =>
      value.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()),
    ),
  );
  const editable = read.allowed && write.allowed && !inherited;
  const removeSelected = () => {
    if (!editable || !selectedSkill) return;
    showConfirmationDialog({
      title: t("rework.spaceSkills.remove"),
      message: t("rework.spaceSkills.removeConfirm", { name: selectedSkill.name }),
      criticalAction: true,
      onConfirm: async () => {
        setError(false);
        try {
          await remove({ spaceId, skillId: selectedSkill.skill_id }).unwrap();
          setSelected(undefined);
          await list.refetch();
        } catch {
          setError(true);
        }
      },
    });
  };
  return (
    <div className={layout.pageContainer}>
      <PageHeader
        title={t("rework.spaceSkills.title")}
        subtitle={spaceName}
        actions={
          <>
            {read.allowed && write.allowed && (
              <Button
                size="small"
                variant="filled"
                color="primary"
                icon={{ category: "outlined", type: "add" }}
                onClick={() => setCreating(true)}
              >
                {t("rework.spaceSkills.new")}
              </Button>
            )}
            <div className={layout.searchBar}>
              <SearchInput
                value={search}
                onChange={setSearch}
                placeholder={t("rework.spaceSkills.searchPlaceholder")}
                clearAriaLabel={t("rework.teams.prompts.clearSearch")}
                size="xs"
              />
            </div>
          </>
        }
      />
      {error && <p role="alert">{t("rework.spaceSkills.failed")}</p>}
      {read.error || list.isError ? (
        <ServiceNotice icon="info" title={t("rework.manager.unavailable")} />
      ) : !read.settled ? (
        <p role="status">{t("common.loading")}</p>
      ) : !read.allowed ? (
        <ServiceNotice icon="lock" title={t("rework.spaceMembers.forbidden")} />
      ) : !list.currentData ? (
        <p role="status">{t("common.loading")}</p>
      ) : (
        <>
          {!skills.length ? (
            <PageEmptyState icon="school" message={t("rework.spaceSkills.empty")} />
          ) : !filtered.length ? (
            <div className={layout.emptyState}>{t("rework.teams.prompts.emptySearch")}</div>
          ) : (
            <div className={layout.promptList}>
              {filtered.map((skill) => (
                <ResourceCard
                  key={skill.skill_id}
                  title={skill.name}
                  label={skill.space_name}
                  command={`/${skill.name}`}
                  description={skill.description}
                  notice={
                    skill.space_id !== spaceId ? t("rework.inheritedResource", { space: skill.space_name }) : undefined
                  }
                  onOpen={() => setSelected(skill.skill_id)}
                />
              ))}
            </div>
          )}
          <FullPageModal
            isOpen={Boolean(selected)}
            onClose={() => setSelected(undefined)}
            id="skill-view-modal"
            background="scrim"
          >
            <div className={layout.modalCard}>
              <div className={layout.modalHeader}>
                <span id="skill-view-modal-title" className={layout.modalTitle}>
                  {selectedSkill?.name ?? t("rework.spaceSkills.title")}
                </span>
                <Button size="small" variant="text" color="on-surface" onClick={() => setSelected(undefined)}>
                  {t("common.close")}
                </Button>
              </div>
              {inherited && <Chip label={t("rework.inheritedResource", { space: selectedSkill.space_name })} />}
              {!selectedSkill || detail.isError ? (
                <ServiceNotice icon="info" title={t("rework.manager.unavailable")} />
              ) : !detail.currentData || detail.isFetching ? (
                <p role="status">{t("common.loading")}</p>
              ) : (
                <SkillFiles
                  key={`${selected}:${detail.currentData.expected_revision}:${editable}`}
                  spaceId={selectedSkill.space_id}
                  name={selectedSkill.name}
                  skillId={selectedSkill.skill_id}
                  files={detail.currentData.files}
                  revision={detail.currentData.expected_revision ?? null}
                  editable={editable}
                  discoverable={detail.currentData.discoverable ?? false}
                  collectiveSpace={collectiveSpace}
                  refresh={async () => {
                    await detail.refetch();
                    await list.refetch();
                  }}
                />
              )}
              {selectedSkill && editable && (
                <Button
                  size="small"
                  variant="text"
                  color="error"
                  disabled={removing.isLoading}
                  onClick={removeSelected}
                >
                  {t("rework.spaceSkills.remove")}
                </Button>
              )}
            </div>
          </FullPageModal>
          {write.allowed && (
            <FullPageModal
              isOpen={creating}
              onClose={() => setCreating(false)}
              id="skill-create-modal"
              background="scrim"
            >
              <NewSkill
                spaceId={spaceId}
                onClose={() => setCreating(false)}
                onCreated={async () => {
                  await list.refetch();
                }}
              />
            </FullPageModal>
          )}
        </>
      )}
    </div>
  );
}

/** Agent Skills frontmatter from plain fields; the Control Plane validates the package. */
export function skillDocument(name: string, description: string, instructions: string) {
  return `---\nname: ${name}\ndescription: ${JSON.stringify(description.trim())}\n---\n\n${instructions.trim()}\n`;
}

function NewSkill({
  spaceId,
  onCreated,
  onClose,
}: {
  spaceId: string;
  onCreated: () => Promise<void>;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [error, setError] = useState(false);
  const [create, creating] = useCreateSkillMutation();
  return (
    <section className={layout.modalCard}>
      <h2 id="skill-create-modal-title" className={layout.modalTitle}>
        {t("rework.spaceSkills.new")}
      </h2>
      {error && <p role="alert">{t("rework.spaceSkills.failed")}</p>}
      <TextInput
        label={t("rework.spaceSkills.name")}
        explanation={t("rework.spaceSkills.nameHint")}
        value={name}
        onChange={(event) => setName(event.target.value.trim())}
      />
      <TextInput
        label={t("rework.spaceSkills.description")}
        value={description}
        onChange={(event) => setDescription(event.target.value)}
      />
      <TextArea
        label={t("rework.spaceSkills.instructions")}
        aria-label={t("rework.spaceSkills.instructions")}
        value={instructions}
        onChange={(event) => setInstructions(event.target.value)}
      />
      <div className={styles.actions}>
        <Button
          size="small"
          variant="filled"
          color="primary"
          disabled={creating.isLoading || !name || !description.trim() || !instructions.trim()}
          onClick={async () => {
            setError(false);
            try {
              await create({
                spaceId,
                createSkill: { name, files: { "SKILL.md": skillDocument(name, description, instructions) } },
              }).unwrap();
              await onCreated();
              onClose();
              setName("");
              setDescription("");
              setInstructions("");
            } catch {
              setError(true);
            }
          }}
        >
          {t("rework.spaceSkills.create")}
        </Button>
        <Button size="small" variant="text" color="primary" disabled={creating.isLoading} onClick={() => onClose()}>
          {t("rework.spaceSkills.cancel")}
        </Button>
      </div>
    </section>
  );
}

function SkillFiles({
  skillId,
  spaceId,
  name,
  files,
  revision,
  editable,
  discoverable,
  collectiveSpace,
  refresh,
}: {
  spaceId: string;
  skillId: string;
  name: string;
  files: Record<string, string>;
  revision: string | null;
  editable: boolean;
  discoverable: boolean;
  collectiveSpace: boolean;
  refresh: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const [proposing, setProposing] = useState(false);
  const [path, setPath] = useState("SKILL.md");
  const [draft, setDraft] = useState(files);
  const [visible, setVisible] = useState(discoverable);
  const [editing, setEditing] = useState(false);
  const [newPath, setNewPath] = useState("");
  const [error, setError] = useState(false);
  const [save, saving] = usePutSkillMutation();
  const shown = editing ? draft : files;
  return (
    <section>
      {error && <p role="alert">{t("rework.spaceSkills.failed")}</p>}
      <SkillFileView files={shown} path={path} onPathChange={setPath}>
        {editing ? (
          <>
            {collectiveSpace && (
              <SwitchRow
                label={t("rework.resourceDiscovery.visible")}
                description={t("rework.resourceDiscovery.visibilityHint")}
                checked={visible}
                disabled={saving.isLoading}
                onChange={setVisible}
              />
            )}
            <TextArea
              label={path}
              value={draft[path] ?? ""}
              onChange={(event) => setDraft({ ...draft, [path]: event.target.value })}
              aria-label={path}
            />
            <div className={styles.actions}>
              <TextInput
                label={t("rework.spaceSkills.filePath")}
                explanation={t("rework.spaceSkills.filePathHint")}
                value={newPath}
                onChange={(event) => setNewPath(event.target.value.trim())}
              />
              <Button
                size="small"
                variant="text"
                color="primary"
                disabled={!newPath || newPath in draft}
                onClick={() => {
                  setDraft({ ...draft, [newPath]: "" });
                  setPath(newPath);
                  setNewPath("");
                }}
              >
                {t("rework.spaceSkills.addFile")}
              </Button>
              <Button
                size="small"
                variant="text"
                color="error"
                disabled={path === "SKILL.md"}
                onClick={() => {
                  const { [path]: _removed, ...rest } = draft;
                  setDraft(rest);
                  setPath("SKILL.md");
                }}
              >
                {t("rework.spaceSkills.removeFile")}
              </Button>
            </div>
          </>
        ) : undefined}
      </SkillFileView>
      {proposing && revision && (
        <MarketplaceProposalDialog
          sourceName={name}
          source={{ kind: "skill", source_space_id: spaceId, source_resource_id: skillId, expected_revision: revision }}
          onClose={() => setProposing(false)}
        />
      )}
      {editable && (
        <div className={styles.actions}>
          <Button
            size="small"
            color="primary"
            variant="text"
            disabled={editing || !revision}
            onClick={() => setProposing(true)}
          >
            {t("rework.localMarketplace.propose")}
          </Button>
          <Button
            size="small"
            variant="text"
            color="primary"
            disabled={saving.isLoading}
            onClick={() => {
              setDraft(files);
              setVisible(discoverable);
              if (editing && !(path in files)) setPath("SKILL.md");
              setEditing(!editing);
            }}
          >
            {t(editing ? "rework.spaceSkills.cancel" : "rework.spaceSkills.edit")}
          </Button>
          {editing && (
            <Button
              size="small"
              variant="filled"
              color="primary"
              disabled={saving.isLoading}
              onClick={async () => {
                setError(false);
                try {
                  await save({
                    spaceId,
                    skillId,
                    putSkill: {
                      files: draft,
                      expected_revision: revision,
                      discoverable: visible === discoverable ? undefined : visible,
                    },
                  }).unwrap();
                  await refresh();
                  setEditing(false);
                } catch {
                  setError(true);
                }
              }}
            >
              {t("rework.spaceSkills.save")}
            </Button>
          )}
        </div>
      )}
    </section>
  );
}

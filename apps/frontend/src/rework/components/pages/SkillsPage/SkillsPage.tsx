// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useSpaceAccess } from "@core/hooks/useSpaceAccess";
import Button from "@shared/atoms/Button/Button";
import TextArea from "@shared/atoms/TextArea/TextArea";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { MarkdownRenderer } from "@shared/molecules/MarkdownRenderer/MarkdownRenderer";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useMySpacesQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import {
  useListSkillsQuery,
  useDefaultSkillsQuery,
  useGetSkillQuery,
  useInstallSkillMutation,
  useDeleteSkillMutation,
  usePutSkillMutation,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import MarketplaceProposalDialog from "../marketplace/MarketplaceProposalDialog";
import styles from "./SkillsPage.module.css";

export default function SkillsPage() {
  const { teamId } = useParams();
  const { t } = useTranslation();
  const spaces = useMySpacesQuery(undefined, { refetchOnMountOrArgChange: true });
  const space = spaces.currentData?.find((s) => (teamId === "personal" ? s.kind === "personal" : s.id === teamId));
  if (spaces.isError) return <ServiceNotice icon="info" title={t("rework.manager.unavailable")} />;
  if (!spaces.currentData) return <p role="status">{t("common.loading")}</p>;
  if (!space) return <ServiceNotice icon="lock" title={t("rework.weaverAgents.scopeUnavailable")} />;
  return <SpaceSkills key={space.id} spaceId={space.id} spaceName={space.name} />;
}

function SpaceSkills({ spaceId, spaceName }: { spaceId: string; spaceName: string }) {
  const { t } = useTranslation();
  const read = useSpaceAccess(spaceId, "read");
  const write = useSpaceAccess(spaceId, "write");
  const list = useListSkillsQuery({ spaceId }, { skip: !read.allowed, refetchOnMountOrArgChange: true });
  const defaults = useDefaultSkillsQuery(undefined, { skip: !write.allowed });
  const [params] = useSearchParams();
  const [selected, setSelected] = useState<string | undefined>(params.get("resource") ?? undefined);
  const detail = useGetSkillQuery(
    { spaceId, skillId: selected ?? "" },
    { skip: !selected || !read.allowed, refetchOnMountOrArgChange: true },
  );
  const [install, installing] = useInstallSkillMutation();
  const [remove, removing] = useDeleteSkillMutation();
  const busy = installing.isLoading || removing.isLoading;
  const [error, setError] = useState(false);
  const { showConfirmationDialog } = useConfirmationDialog();
  const mutate = async (action: () => Promise<unknown>) => {
    setError(false);
    try {
      await action();
      await list.refetch();
    } catch {
      setError(true);
    }
  };
  return (
    <div className={styles.page}>
      <PageHeader title={t("rework.spaceSkills.title")} subtitle={spaceName} />
      <p>{t("rework.spaceSkills.scope")}</p>
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
          {!list.currentData.length && <p>{t("rework.spaceSkills.empty")}</p>}
          <ul className={styles.list}>
            {list.currentData.map((skill) => (
              <li key={skill.skill_id}>
                <Button size="small" variant="text" color="primary" onClick={() => setSelected(skill.skill_id)}>
                  {skill.name}
                </Button>
                <p>{skill.summary.description}</p>
                {write.allowed && (
                  <Button
                    size="small"
                    variant="text"
                    color="error"
                    disabled={busy}
                    onClick={() =>
                      showConfirmationDialog({
                        title: t("rework.spaceSkills.remove"),
                        message: t("rework.spaceSkills.removeConfirm", { name: skill.name }),
                        criticalAction: true,
                        onConfirm: () => {
                          void mutate(async () => {
                            await remove({ spaceId, skillId: skill.skill_id }).unwrap();
                            if (selected === skill.skill_id) setSelected(undefined);
                          });
                        },
                      })
                    }
                  >
                    {t("rework.spaceSkills.remove")}
                  </Button>
                )}
              </li>
            ))}
          </ul>
          {selected &&
            (detail.isError ? (
              <p role="alert">{t("rework.spaceSkills.failed")}</p>
            ) : !detail.currentData ? (
              <p role="status">{t("common.loading")}</p>
            ) : (
              <SkillFiles
                key={`${selected}:${detail.currentData.expected_revision}`}
                spaceId={spaceId}
                name={list.currentData.find((s) => s.skill_id === selected)?.name ?? ""}
                skillId={selected}
                files={detail.currentData.files}
                revision={detail.currentData.expected_revision ?? null}
                editable={write.allowed}
                refresh={async () => {
                  await detail.refetch();
                  await list.refetch();
                }}
              />
            ))}
        </>
      )}
      {write.allowed && (
        <section>
          <h2>{t("rework.spaceSkills.defaults")}</h2>
          <p>{t("rework.spaceSkills.installExplanation")}</p>
          {defaults.isError && <p role="alert">{t("rework.spaceSkills.failed")}</p>}
          <ul className={styles.list}>
            {defaults.currentData?.map((skill) => (
              <li key={skill.name}>
                <strong>{skill.name}</strong>
                <p>{skill.description}</p>
                <Button
                  size="small"
                  variant="outlined"
                  color="primary"
                  disabled={busy || !list.currentData || list.currentData.some((s) => s.name === skill.name)}
                  onClick={() => void mutate(() => install({ spaceId, name: skill.name }).unwrap())}
                >
                  {t("rework.spaceSkills.install")}
                </Button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function SkillFiles({
  skillId,
  spaceId,
  name,
  files,
  revision,
  editable,
  refresh,
}: {
  spaceId: string;
  skillId: string;
  name: string;
  files: Record<string, string>;
  revision: string | null;
  editable: boolean;
  refresh: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const [proposing, setProposing] = useState(false);
  const [path, setPath] = useState("SKILL.md");
  const [draft, setDraft] = useState(files);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState(false);
  const [save, saving] = usePutSkillMutation();
  return (
    <section>
      <h2>{name}</h2>
      <div className={styles.actions}>
        {Object.keys(files).map((file) => (
          <Button size="small" key={file} variant="text" color="primary" onClick={() => setPath(file)}>
            {file}
          </Button>
        ))}
      </div>
      {error && <p role="alert">{t("rework.spaceSkills.failed")}</p>}
      {editing ? (
        <TextArea
          label={path}
          value={draft[path]}
          onChange={(event) => setDraft({ ...draft, [path]: event.target.value })}
          aria-label={path}
        />
      ) : (
        <MarkdownRenderer text={draft[path]} fullWidth localLinksAsText />
      )}
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
                  await save({ spaceId, skillId, putSkill: { files: draft, expected_revision: revision } }).unwrap();
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

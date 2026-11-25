// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { downloadManagerDocument } from "@rework/features/imports/managerDocuments";
import { useMarketplaceSession } from "./marketplace";
import { useTranslation } from "react-i18next";
import { PromptContent } from "../PromptsPage/PromptViewDialog/PromptViewDialog";
import { SkillFileView } from "@shared/molecules/SkillFileView/SkillFileView";
import { formatBytes } from "@shared/utils/formatBytes";
import Chip from "@shared/atoms/Chip/Chip";
import Disclosure from "@shared/atoms/Disclosure/Disclosure";
import { TOOL_PACK_SECTIONS } from "../TeamAgentsPage/AgentFormModal/toolPacks";
import type { MarketplacePackage } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./Marketplace.module.css";

/** Render the returned snapshot as text; never execute submitted markdown or configuration. */
export default function MarketplacePackageView({
  value,
  canDownload = true,
}: {
  value: MarketplacePackage;
  canDownload?: boolean;
}) {
  const { t, i18n } = useTranslation();
  const { showError } = useToast();
  const active = useMarketplaceSession();
  const [downloading, setDownloading] = useState<string>();
  if (value.kind === "prompt") return <PromptContent detail={value.content} />;
  if (value.kind === "skill") return <SkillFileView files={value.content.files} />;
  const { capabilities, role, usage_statement, tuning_field_values } = value.content;
  const instructions: unknown = tuning_field_values["prompts.system"];
  const capabilityLabels = TOOL_PACK_SECTIONS.flatMap((section) => section.packs.flatMap((pack) => pack.includes));
  const exportedCapabilities = Object.entries(capabilities).map(([id, capability]) => ({
    id,
    label: t(capabilityLabels.find((item) => item.capabilityId === id)?.labelKey ?? `capability.${id}.name`, {
      defaultValue: id,
    }),
    files: Object.entries(capability.files),
  }));
  return (
    <div className={styles.content}>
      {role && (
        <section>
          <h3>{t("rework.teams.formAgent.fields.role.label")}</h3>
          <span className={styles.text}>{role}</span>
        </section>
      )}
      {usage_statement && (
        <section>
          <h3>{t("rework.teams.formAgent.fields.usageStatement.label")}</h3>
          <span className={styles.text}>{usage_statement}</span>
        </section>
      )}
      <section>
        <h3>{t("rework.localMarketplace.instructions")}</h3>
        {typeof instructions === "string" && instructions.trim() ? (
          <pre className={styles.text} tabIndex={0}>
            {instructions}
          </pre>
        ) : (
          <span className={styles.identity}>{t("rework.localMarketplace.noInstructions")}</span>
        )}
      </section>
      <section>
        <h3>{t("rework.localMarketplace.capabilities")}</h3>
        {Object.keys(capabilities).length ? (
          <div className={styles.actions}>
            {exportedCapabilities.map(({ id, label }) => (
              <Chip key={id} label={label} />
            ))}
          </div>
        ) : (
          <span className={styles.identity}>{t("rework.localMarketplace.noCapabilities")}</span>
        )}
      </section>
      {exportedCapabilities.map(({ id, label, files }) =>
        files.length ? (
          <Disclosure key={id} title={t("rework.localMarketplace.files", { capability: label })}>
            <ul>
              {files.map(([path, file]) => (
                <li key={path}>
                  {file.name} · {file.mime} · {formatBytes(file.size, i18n.language)}
                  <IconButton
                    size="small"
                    variant="icon"
                    color="on-surface-retreat"
                    icon={{ category: "outlined", type: "download" }}
                    aria-label={t("chatbot.artifactLinks.downloadAria", { name: file.name })}
                    title={t("chatbot.artifactLinks.downloadAria", { name: file.name })}
                    loading={downloading === file.document_id}
                    disabled={!canDownload || !!downloading}
                    onClick={async () => {
                      if (!active() || !canDownload || downloading) return;
                      setDownloading(file.document_id);
                      try {
                        await downloadManagerDocument({ id: file.document_id, name: file.name, size: file.size });
                      } catch {
                        if (active())
                          showError({ summary: t("chatbot.artifactLinks.downloadFailed", { name: file.name }) });
                      } finally {
                        if (active()) setDownloading(undefined);
                      }
                    }}
                  />
                </li>
              ))}
            </ul>
          </Disclosure>
        ) : null,
      )}
    </div>
  );
}

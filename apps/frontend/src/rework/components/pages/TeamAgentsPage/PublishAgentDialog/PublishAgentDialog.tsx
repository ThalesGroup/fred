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

import Checkbox from "@shared/atoms/Checkbox/Checkbox.tsx";
import { Dialog } from "@shared/molecules/Dialog/Dialog.tsx";
import { helpPagePath } from "@rework/features/helpCenter/content";
import { isHelpLang } from "@rework/features/helpCenter/manifest";
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import styles from "./PublishAgentDialog.module.css";

interface PublishAgentDialogProps {
  open: boolean;
  agentName: string;
  republish: boolean;
  /** Capabilities whose configuration files an importer receives a copy of. */
  fileNames: string[];
  /** Both absent when the team's marketplace data is missing: no quota line. */
  publishedCount?: number;
  quota?: number;
  isSubmitting?: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

/** Every publication and republication goes through this warning. */
export default function PublishAgentDialog({
  open,
  agentName,
  republish,
  fileNames,
  publishedCount,
  quota,
  isSubmitting = false,
  onCancel,
  onConfirm,
}: PublishAgentDialogProps) {
  const { t, i18n } = useTranslation();
  const [understood, setUnderstood] = useState(false);
  const checkboxId = useId();
  const uiLang = i18n.language.split("-")[0];
  const helpLang = isHelpLang(uiLang) ? uiLang : "fr";
  // Slug of the marketplace heading in each language's agents.md.
  const helpAnchor = helpLang === "en" ? "the-agents-marketplace" : "la-marketplace-des-agents";

  useEffect(() => {
    if (open) setUnderstood(false);
  }, [open]);

  return (
    <Dialog
      open={open}
      title={t(
        republish
          ? "rework.agentMarketplace.publishDialog.titleRepublish"
          : "rework.agentMarketplace.publishDialog.title",
        {
          name: agentName,
        },
      )}
      confirmLabel={t(
        republish
          ? "rework.agentMarketplace.publishDialog.confirmRepublish"
          : "rework.agentMarketplace.publishDialog.confirm",
      )}
      confirmDisabled={!understood || isSubmitting}
      onConfirm={onConfirm}
      onCancel={onCancel}
    >
      <div className={styles.body}>
        <p>{t("rework.agentMarketplace.publishDialog.visibility")}</p>
        {fileNames.length > 0 && (
          <p>{t("rework.agentMarketplace.publishDialog.files", { names: fileNames.join(", ") })}</p>
        )}
        {publishedCount !== undefined && quota !== undefined && (
          <p className={styles.quota}>
            {t(
              // A republish doesn't take a new slot, so only a first publication can be the last one.
              !republish && publishedCount === quota - 1
                ? "rework.agentMarketplace.publishDialog.quotaLast"
                : "rework.agentMarketplace.publishDialog.quota",
              { count: publishedCount, quota },
            )}
          </p>
        )}
        <Link
          className={styles.helpLink}
          to={`${helpPagePath(helpLang, "features", "agents")}#${helpAnchor}`}
          target="_blank"
          rel="opener"
        >
          {t("rework.agentMarketplace.publishDialog.learnMore")}
        </Link>
        <div className={styles.acknowledge}>
          <Checkbox id={checkboxId} checked={understood} onChange={(event) => setUnderstood(event.target.checked)} />
          <label htmlFor={checkboxId}>{t("rework.agentMarketplace.publishDialog.understand")}</label>
        </div>
      </div>
    </Dialog>
  );
}

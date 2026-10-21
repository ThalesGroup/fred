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

import Button from "@shared/atoms/Button/Button.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import AgentMarketplaceBar, {
  formatMarketplaceDate,
  MarketplaceCounter,
} from "@shared/molecules/AgentMarketplaceBar/AgentMarketplaceBar.tsx";
import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { AgentMarketplaceState } from "../../../../../slices/legacyControlPlane/legacyControlPlaneOpenApi.ts";
import styles from "./AgentCard.module.scss";

const REMOVAL_REASONS = ["deactivated", "suspended", "switch_off", "team_private", "removed_by_platform_admin"];

interface TeamMarketplaceStateProps {
  marketplace: AgentMarketplaceState | null | undefined;
  /** Editors and the team admin: Modified and Removed are theirs to see. */
  showDetailedState: boolean;
  /** Editors and the team admin may hide a Removed state for the team. */
  canHide: boolean;
  onHide: () => void;
}

/** The team card's marketplace state, in the shared bottom bar. */
export default function TeamMarketplaceState({
  marketplace,
  showDetailedState,
  canHide,
  onHide,
}: TeamMarketplaceStateProps) {
  const { t, i18n } = useTranslation();
  const [popoverOpen, setPopoverOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const popoverId = useId();

  useEffect(() => {
    if (!popoverOpen) return;
    const onMouseDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setPopoverOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPopoverOpen(false);
    };
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [popoverOpen]);

  const showRemoved = marketplace?.state === "removed" && showDetailedState;
  if (!marketplace || (marketplace.state !== "published" && !showRemoved)) {
    return null;
  }
  if (marketplace.state === "removed") {
    const reason = REMOVAL_REASONS.includes(marketplace.removed_reason ?? "")
      ? t(`rework.agentMarketplace.removed.reasons.${marketplace.removed_reason}`)
      : t("rework.agentMarketplace.removed.reasons.unknown");
    return (
      <AgentMarketplaceBar aria-label={t("rework.agentMarketplace.barLabel")}>
        <div ref={containerRef} className={styles.marketplaceRemoved}>
          <button
            type="button"
            className={styles.marketplaceStateButton}
            aria-expanded={popoverOpen}
            aria-controls={popoverId}
            onClick={() => setPopoverOpen((open) => !open)}
          >
            <Icon category="outlined" type="do_not_disturb_on" />
            {t("rework.agentMarketplace.removed.label")}
          </button>
          {popoverOpen && (
            <div
              id={popoverId}
              className={styles.marketplacePopover}
              role="dialog"
              aria-label={t("rework.agentMarketplace.removed.label")}
            >
              <p className={styles.marketplacePopoverReason}>{reason}</p>
              {marketplace.removed_at && (
                <p className={styles.marketplacePopoverMeta}>
                  {t("rework.agentMarketplace.removed.date", {
                    date: formatMarketplaceDate(marketplace.removed_at, i18n.language),
                  })}
                </p>
              )}
              {marketplace.removed_message && (
                <p className={styles.marketplacePopoverMessage}>
                  {t("rework.agentMarketplace.removed.message", { message: marketplace.removed_message })}
                </p>
              )}
              {canHide && (
                <div className={styles.marketplacePopoverActions}>
                  <Button
                    color="primary"
                    variant="text"
                    size="small"
                    onClick={() => {
                      setPopoverOpen(false);
                      onHide();
                    }}
                  >
                    {t("rework.agentMarketplace.removed.hide")}
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      </AgentMarketplaceBar>
    );
  }

  const modified = showDetailedState && !!marketplace.modified;
  const likes = marketplace.like_count ?? 0;
  const imports = marketplace.import_count ?? 0;
  const label = modified ? (
    <Tooltip text={t("rework.agentMarketplace.modified.tooltip")}>
      <span className={styles.marketplaceStateLabel} tabIndex={0}>
        <Icon category="outlined" type="warning" />
        {t("rework.agentMarketplace.modified.label")}
      </span>
    </Tooltip>
  ) : (
    <Tooltip text={t("rework.agentMarketplace.publishedTooltip")}>
      <span className={styles.marketplacePublishedChip} tabIndex={0}>
        <Icon category="outlined" type="storefront" />
        {t("rework.agentMarketplace.published")}
      </span>
    </Tooltip>
  );
  return (
    <AgentMarketplaceBar tone={modified ? "warning" : "neutral"} aria-label={t("rework.agentMarketplace.barLabel")}>
      <span className={styles.marketplaceCounters}>
        <MarketplaceCounter
          icon="favorite"
          count={likes}
          label={t("rework.agentMarketplace.likes", { count: likes })}
        />
        <MarketplaceCounter
          icon="download"
          count={imports}
          label={t("rework.agentMarketplace.imports", { count: imports })}
        />
      </span>
      <span className={styles.marketplaceTrailing}>{label}</span>
    </AgentMarketplaceBar>
  );
}

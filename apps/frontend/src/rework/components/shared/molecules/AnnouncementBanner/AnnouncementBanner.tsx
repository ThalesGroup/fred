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

// ---------------------------------------------------------------------------
// One platform announcement, rendered as a full-width banner.
// Severity fixes the icon and accent; the admin authors only text. The stack
// that owns ordering and dismissal state lives in
// features/announcements/AnnouncementStack.tsx — this component renders one
// announcement and reports when the user closes it.
// ---------------------------------------------------------------------------

import { memo, useState } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import Button from "@shared/atoms/Button/Button";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import { MarkdownRenderer } from "@shared/molecules/MarkdownRenderer/MarkdownRenderer";
import { SEVERITY_ICONS, type Severity } from "@shared/utils/severity";
import { resolveAnnouncementText } from "../../../../features/announcements/announcementText";
import type { Announcement } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./AnnouncementBanner.module.css";

// Must match the transition duration in AnnouncementBanner.module.css
// (.collapse): the DOM node is removed only after the eased collapse has
// finished.
export const HIDE_TRANSITION_MS = 300;

interface AnnouncementBannerProps {
  announcement: Announcement;
  /** Called once the exit animation has finished, not when it starts. */
  onDismissed?: (announcement: Announcement) => void;
  /**
   * Render as a preview of the live banner — the admin page's list.
   *
   * Everything still renders, including the close button, because the point of
   * the preview is to show exactly what users will get. What changes is that
   * the strip stops being a real announcement: dismissal no-ops (collapsing a
   * row in the admin list would leave a hole), the close button leaves the tab
   * order and the accessibility tree rather than offering a dead control, and
   * the strip is not a live region — a list of ten would otherwise announce
   * all ten on load. "More info" stays live, so an admin can check that their
   * long description reads well before enabling the announcement.
   */
  preview?: boolean;
}

function AnnouncementBanner({ announcement, onDismissed, preview = false }: AnnouncementBannerProps) {
  const { t, i18n } = useTranslation();
  const [hiding, setHiding] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);

  const severity = announcement.severity as Severity;
  const title = resolveAnnouncementText(announcement.title, i18n.language);
  const short = resolveAnnouncementText(announcement.description_short, i18n.language);
  const long = resolveAnnouncementText(announcement.description_long, i18n.language);

  // Fixed-delay removal rather than a transitionend listener: under
  // prefers-reduced-motion the transition never fires an end event (the
  // collapse snaps), while the timeout removes the node either way.
  const dismiss = () => {
    if (preview) return;
    setHiding(true);
    window.setTimeout(() => onDismissed?.(announcement), HIDE_TRANSITION_MS);
  };

  return (
    <>
      <div
        className={hiding ? `${styles.collapse} ${styles.collapsing}` : styles.collapse}
        // Screen readers drop the banner as soon as the exit starts; sighted
        // users watch the eased collapse for HIDE_TRANSITION_MS more.
        aria-hidden={hiding || undefined}
      >
        <div className={styles.collapseInner}>
          <div
            className={styles.banner}
            data-severity={severity}
            role={preview ? undefined : "status"}
            aria-live={preview ? undefined : "polite"}
          >
            <div className={styles.inner}>
              {/* Icon and text are one group with their own rhythm, so the
                  space to the actions can stay wider than the one inside it. */}
              <div className={styles.lede}>
                <span className={styles.icon} aria-hidden>
                  <Icon category="outlined" type={SEVERITY_ICONS[severity] ?? "info"} />
                </span>
                <div className={styles.text}>
                  {title && <span className={styles.title}>{title}</span>}
                  {short && (
                    <span className={styles.short}>
                      {/* Inline: a banner's short description is one or two
                          lines of phrasing content, not a paragraph block. */}
                      <MarkdownRenderer text={short} inline />
                    </span>
                  )}
                </div>
              </div>
              <div className={styles.actions}>
                {long && (
                  <Button
                    color="on-surface"
                    variant="text"
                    size="small"
                    className={styles.actionButton}
                    onClick={() => setDialogOpen(true)}
                  >
                    {t("rework.announcements.banner.moreInfo")}
                  </Button>
                )}
                {announcement.dismissible && (
                  <IconButton
                    size="small"
                    variant="icon"
                    className={styles.actionButton}
                    icon={{ category: "outlined", type: "close" }}
                    aria-label={t("rework.announcements.banner.dismiss")}
                    onClick={dismiss}
                    // Visible but inert in a preview: it has to be there for
                    // the admin to see, and must not be reachable as a control.
                    tabIndex={preview ? -1 : undefined}
                    aria-hidden={preview || undefined}
                  />
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
      {long && (
        <Dialog
          open={dialogOpen}
          title={title ?? ""}
          confirmLabel={t("rework.announcements.dialog.close")}
          onConfirm={() => setDialogOpen(false)}
          onCancel={() => setDialogOpen(false)}
          hideCancel
        >
          <MarkdownRenderer text={long} />
        </Dialog>
      )}
    </>
  );
}

// Memoized: the stack refetches every 60 s and RTK hands back a fresh array
// even when the content is identical. Without this, every poll re-runs
// MarkdownRenderer's remark/rehype pipeline for every visible banner.
export default memo(AnnouncementBanner);

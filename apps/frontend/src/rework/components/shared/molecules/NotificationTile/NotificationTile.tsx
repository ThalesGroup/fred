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

import { useId } from "react";
import Button from "@shared/atoms/Button/Button.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { IndicatorDot } from "@shared/atoms/IndicatorDot/IndicatorDot.tsx";
import type { ColorTheme, IconType } from "@shared/utils/Type.ts";
import styles from "./NotificationTile.module.scss";

export type NotificationCategory = "action_required" | "information";

export interface NotificationTileAction {
  id: string;
  label: string;
  primary?: boolean;
  /** Defaults to `primary`. */
  color?: ColorTheme;
  onClick: () => void;
}

export interface NotificationTileProps {
  icon: IconType;
  category: NotificationCategory;
  title: string;
  /** One line under the title, e.g. who asks when the title names the team. */
  subtitle?: string;
  body?: string;
  /** Already formatted ("5 min ago"); `dateTime` feeds the `<time>` element. */
  time: string;
  dateTime: string;
  /** The full date, shown on hovering the time. */
  dateTitle?: string;
  /** New since the list was last opened: a dot before the time, named by `unreadLabel`. */
  unread?: boolean;
  unreadLabel?: string;
  /** Replaces the actions once someone acted on the subject. */
  handledLabel?: string;
  actions?: NotificationTileAction[];
  /** Disables the actions while one of them is in flight. */
  busy?: boolean;
  dismissLabel: string;
  /** False for a pending decision: the user answers it, they don't discard it. */
  dismissible?: boolean;
  /** Label of the outlined button that opens the subject; no button without it. */
  viewLabel?: string;
  onView?: () => void;
  onDismiss: () => void;
}

/** One notification in a list: only its buttons are interactive, not the card. */
export default function NotificationTile({
  icon,
  category,
  title,
  subtitle,
  body,
  time,
  dateTime,
  dateTitle,
  unread = false,
  unreadLabel,
  handledLabel,
  actions = [],
  busy = false,
  dismissLabel,
  dismissible = true,
  viewLabel,
  onView,
  onDismiss,
}: NotificationTileProps) {
  const view = viewLabel && onView ? { label: viewLabel, onClick: onView } : undefined;
  // Every tile has the same buttons: the title tells screen readers whose they are.
  const titleId = useId();
  return (
    <li className={styles.tile} data-dismissible={dismissible || undefined}>
      <span className={styles.icon} data-category={category}>
        <Icon category="outlined" type={icon} />
      </span>
      <div className={styles.text}>
        <div className={styles.lines}>
          <p id={titleId} className={styles.title} title={title}>
            {title}
          </p>
          {subtitle && (
            <p className={styles.subtitle} title={subtitle}>
              {subtitle}
            </p>
          )}
          {body && (
            <p className={styles.body} title={body}>
              {body}
            </p>
          )}
          <span className={styles.metaRow}>
            {unread && <IndicatorDot status="unread" label={unreadLabel} />}
            <time className={styles.meta} dateTime={dateTime} title={dateTitle}>
              {time}
            </time>
          </span>
        </div>
        {handledLabel && (
          <p className={styles.handled}>
            <span className={styles.handledIcon}>
              <Icon category="outlined" type="check_circle" />
            </span>
            <span className={styles.handledLabel} title={handledLabel}>
              {handledLabel}
            </span>
          </p>
        )}
        {(view || (!handledLabel && actions.length > 0)) && (
          <div className={styles.actions}>
            {view && (
              <Button
                type="button"
                color="primary"
                variant="outlined"
                size="small"
                aria-describedby={titleId}
                onClick={view.onClick}
              >
                {view.label}
              </Button>
            )}
            {!handledLabel &&
              actions.map((action) => (
                <Button
                  key={action.id}
                  type="button"
                  color={action.color ?? "primary"}
                  variant={action.primary ? "filled" : "outlined"}
                  size="small"
                  disabled={busy}
                  aria-describedby={titleId}
                  onClick={action.onClick}
                >
                  {action.label}
                </Button>
              ))}
          </div>
        )}
      </div>
      {dismissible && (
        <div className={styles.trail}>
          <IconButton
            type="button"
            variant="icon"
            size="medium"
            color="on-surface-retreat"
            icon={{ category: "outlined", type: "close" }}
            aria-label={dismissLabel}
            aria-describedby={titleId}
            onClick={onDismiss}
          />
        </div>
      )}
    </li>
  );
}

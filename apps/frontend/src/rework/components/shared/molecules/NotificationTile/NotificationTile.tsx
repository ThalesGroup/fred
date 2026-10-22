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
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
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
  body?: string;
  /** Already formatted ("5 min ago"); `dateTime` feeds the `<time>` element. */
  time: string;
  dateTime: string;
  /** Replaces the actions once someone acted on the subject. */
  handledLabel?: string;
  actions?: NotificationTileAction[];
  /** Disables the actions while one of them is in flight. */
  busy?: boolean;
  dismissLabel: string;
  /** False for a pending decision: the user answers it, they don't discard it. */
  dismissible?: boolean;
  onOpen: () => void;
  onDismiss: () => void;
}

/**
 * One notification in a list. The title button stretches over the whole tile, so
 * a click anywhere opens it; the actions and the always-visible close button sit
 * above that hit area.
 */
export default function NotificationTile({
  icon,
  category,
  title,
  body,
  time,
  dateTime,
  handledLabel,
  actions = [],
  busy = false,
  dismissLabel,
  dismissible = true,
  onOpen,
  onDismiss,
}: NotificationTileProps) {
  return (
    <li className={styles.tile} data-dismissible={dismissible || undefined}>
      <span className={styles.icon} data-category={category}>
        <Icon category="outlined" type={icon} />
      </span>
      <div className={styles.text}>
        <button type="button" className={styles.hit} onClick={onOpen}>
          {title}
        </button>
        {body && <p className={styles.body}>{body}</p>}
        <time className={styles.meta} dateTime={dateTime}>
          {time}
        </time>
        {handledLabel ? (
          <p className={styles.handled}>
            <span className={styles.handledIcon}>
              <Icon category="outlined" type="check_circle" />
            </span>
            {handledLabel}
          </p>
        ) : (
          actions.length > 0 && (
            <div className={styles.actions}>
              {actions.map((action) => (
                <Button
                  key={action.id}
                  type="button"
                  color={action.color ?? "primary"}
                  variant={action.primary ? "filled" : "outlined"}
                  size="small"
                  disabled={busy}
                  onClick={action.onClick}
                >
                  {action.label}
                </Button>
              ))}
            </div>
          )
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
            onClick={onDismiss}
          />
        </div>
      )}
    </li>
  );
}

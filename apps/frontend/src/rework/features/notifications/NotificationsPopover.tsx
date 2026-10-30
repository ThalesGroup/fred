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

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { Spinner } from "@shared/atoms/Spinner/Spinner.tsx";
import MenuPopover from "@shared/molecules/MenuPopover/MenuPopover.tsx";
import NotificationTile from "@shared/molecules/NotificationTile/NotificationTile.tsx";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
import { relativeTime } from "../tasks/taskLabels";
import {
  useClearNotificationsMutation,
  useDeleteNotificationMutation,
  useMarkNotificationsSeenMutation,
  useNotificationsQuery,
} from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import { renderNotification, type NotificationItem } from "./notificationTypes";
import styles from "./NotificationsPopover.module.scss";

/** The backend's page size cap. */
const NOTIFICATIONS_PAGE_SIZE = 50;

interface TileHandlers {
  /** The View button or an action. */
  interact: (notification: NotificationItem, to: string | null) => void;
  onDismiss: (notification: NotificationItem) => void;
  isUnread: (notification: NotificationItem) => boolean;
}

function NotificationListItem({ notification, handlers }: { notification: NotificationItem; handlers: TileHandlers }) {
  const { t, i18n } = useTranslation();
  const rendered = renderNotification(notification, t);
  // No View button when an action already opens the same place.
  const link = rendered.link;
  const showView = !!link && !rendered.actions.some((action) => action.kind === "navigate" && action.to === link);
  return (
    <NotificationTile
      icon={rendered.icon}
      category={rendered.category}
      title={rendered.title}
      body={rendered.body}
      time={relativeTime(new Date(notification.created_at).getTime(), t)}
      dateTime={notification.created_at}
      dateTitle={new Date(notification.created_at).toLocaleString(i18n.language, {
        dateStyle: "full",
        timeStyle: "short",
      })}
      unread={handlers.isUnread(notification)}
      unreadLabel={t("rework.notifications.unread")}
      handledLabel={rendered.handledLabel}
      actions={rendered.actions.map((action) => ({
        id: action.id,
        label: action.label,
        primary: action.primary,
        onClick: () => handlers.interact(notification, action.to),
      }))}
      dismissLabel={t("rework.notifications.dismiss")}
      viewLabel={showView ? t("rework.notifications.actions.view") : undefined}
      onView={() => handlers.interact(notification, rendered.link)}
      onDismiss={() => handlers.onDismiss(notification)}
    />
  );
}

function LoadMore({ cursor, onLoadMore }: { cursor: string | null | undefined; onLoadMore: () => void }) {
  const { t } = useTranslation();
  if (!cursor) return null;
  return (
    <li className={styles.loadMore}>
      <Button type="button" color="primary" variant="text" size="small" onClick={onLoadMore}>
        {t("rework.notifications.loadMore")}
      </Button>
    </li>
  );
}

/**
 * The pages after the first, each fetched from the current cursor of the page
 * before it, so a delete or an arrival above shifts them instead of duplicating
 * or skipping a row.
 */
function NotificationPageItems({
  before,
  remaining,
  onLoadMore,
  handlers,
}: {
  before: string;
  remaining: number;
  onLoadMore: () => void;
  handlers: TileHandlers;
}) {
  const { data } = useNotificationsQuery({ limit: NOTIFICATIONS_PAGE_SIZE, before });
  const next = data?.next_cursor;
  return (
    <>
      {data?.items.map((notification) => (
        <NotificationListItem key={notification.id} notification={notification} handlers={handlers} />
      ))}
      {remaining > 0 && next ? (
        <NotificationPageItems before={next} remaining={remaining - 1} onLoadMore={onLoadMore} handlers={handlers} />
      ) : (
        <LoadMore cursor={next} onLoadMore={onLoadMore} />
      )}
    </>
  );
}

interface NotificationsPopoverProps {
  id: string;
  /** `refocus`: return focus to the bell (Escape, back button), not after a navigation. */
  onClose: (refocus: boolean) => void;
}

/**
 * The bell's popover: the caller's notifications, newest first. Opening it marks
 * as seen every notification up to the newest one it listed, so one arriving
 * while it is open still badges.
 */
export default function NotificationsPopover({ id, onClose }: NotificationsPopoverProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  // Focus lands on the title on opening and whenever the focused tile goes away.
  const titleRef = useRef<HTMLHeadingElement>(null);
  const [openedAt] = useState(() => Date.now());
  const [morePages, setMorePages] = useState(0);
  const seenPosted = useRef(false);

  const firstPage = useNotificationsQuery({ limit: NOTIFICATIONS_PAGE_SIZE }, { refetchOnMountOrArgChange: true });
  const [markSeen] = useMarkNotificationsSeenMutation();
  const [deleteNotification] = useDeleteNotificationMutation();
  const [clearNotifications, { isLoading: clearing }] = useClearNotificationsMutation();

  const items = firstPage.data?.items;
  // Only an answer fetched since this opening may mark anything seen.
  const fresh = (firstPage.fulfilledTimeStamp ?? 0) >= openedAt && !firstPage.isFetching;

  // Unseen when this opening first listed them: marking them seen must not
  // drop their dot at once, only the next opening does.
  const [unreadAtOpen, setUnreadAtOpen] = useState<ReadonlySet<string> | null>(null);
  if (fresh && items && unreadAtOpen === null) {
    setUnreadAtOpen(new Set(items.filter((notification) => !notification.seen_at).map(({ id }) => id)));
  }

  useEffect(() => titleRef.current?.focus(), []);

  useEffect(() => {
    if (!fresh || !items || seenPosted.current) return;
    seenPosted.current = true;
    if (items.some((notification) => !notification.seen_at)) {
      void markSeen({ markNotificationsSeenRequest: { up_to: items[0].id } });
    }
  }, [fresh, items, markSeen]);

  const handlers: TileHandlers = {
    // Acting on a tile is done with it.
    interact: (notification, to) => {
      handlers.onDismiss(notification);
      if (!to) return;
      onClose(false);
      navigate(to);
    },
    onDismiss: (notification) => {
      // The clicked button has focus; hand it to the neighbouring tile.
      const tile = document.activeElement?.closest("li");
      const neighbour = (tile?.nextElementSibling ?? tile?.previousElementSibling)?.querySelector("button");
      void deleteNotification({ notificationId: notification.id });
      (neighbour ?? titleRef.current)?.focus();
    },
    isUnread: (notification) => !notification.seen_at || Boolean(unreadAtOpen?.has(notification.id)),
  };

  const clearAll = async () => {
    try {
      await clearNotifications().unwrap();
      setMorePages(0);
    } finally {
      titleRef.current?.focus();
    }
  };

  const loadMore = () => setMorePages((count) => count + 1);
  const clearable = Boolean(items?.length);

  let content;
  if (!items) {
    content = firstPage.isError ? (
      <p className={styles.status}>{t("rework.notifications.loadError")}</p>
    ) : (
      <div className={styles.status}>
        <Spinner />
      </div>
    );
  } else if (items.length === 0) {
    content = (
      <PageEmptyState
        icon="notifications_off"
        message={t("rework.notifications.empty.title")}
        description={t("rework.notifications.empty.description")}
      />
    );
  } else {
    content = (
      <ul className={styles.list}>
        {items.map((notification) => (
          <NotificationListItem key={notification.id} notification={notification} handlers={handlers} />
        ))}
        {morePages > 0 && firstPage.data?.next_cursor ? (
          <NotificationPageItems
            before={firstPage.data.next_cursor}
            remaining={morePages - 1}
            onLoadMore={loadMore}
            handlers={handlers}
          />
        ) : (
          <LoadMore cursor={firstPage.data?.next_cursor} onLoadMore={loadMore} />
        )}
      </ul>
    );
  }

  return (
    <div className={styles.wrap} id={id}>
      <MenuPopover
        className={styles.panel}
        role="dialog"
        aria-label={t("rework.notifications.title")}
        header={
          <div className={styles.header}>
            <IconButton
              type="button"
              className={styles.back}
              variant="icon"
              size="medium"
              color="on-surface-retreat"
              icon={{ category: "outlined", type: "arrow_back" }}
              aria-label={t("rework.notifications.close")}
              onClick={() => onClose(true)}
            />
            <h2 ref={titleRef} className={styles.title} tabIndex={-1}>
              {t("rework.notifications.title")}
            </h2>
            <Button
              type="button"
              color="primary"
              variant="text"
              size="small"
              disabled={!clearable || clearing}
              onClick={() => void clearAll()}
            >
              {t("rework.notifications.clearAll")}
            </Button>
          </div>
        }
        groups={[
          [
            <div key="content" className={styles.content}>
              {content}
            </div>,
          ],
        ]}
      />
    </div>
  );
}

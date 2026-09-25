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
// The banners at the top of the authenticated app.
// Owns what AnnouncementBanner deliberately does not: which announcements are
// live, in what order, and which ones this browser has already dismissed.
// Mounted inside GcuGuard/BootstrapGuard (see App.tsx), above the routed
// content in the `.appContent` flex column: banners push the page down instead
// of covering it, and being inside the guards is what keeps them off the
// terms-acceptance and root-bootstrap screens. Do not gate this on
// `useAuth().isAuthenticated` — it is `!!GetUserRoles()`, and that call always
// returns an array, so it is never false.
// ---------------------------------------------------------------------------

import { useCallback, useMemo, useState } from "react";
import AnnouncementBanner from "@shared/molecules/AnnouncementBanner/AnnouncementBanner";
import { SEVERITY_RANK, type Severity } from "@shared/utils/severity";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { useActiveAnnouncementsQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Announcement } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { dismissalKey, isDismissedIn, markDismissed, readDismissedSet } from "./announcementDismissal";
import styles from "./AnnouncementStack.module.css";

/** Most severe first; oldest first within one severity. */
function bySeverityThenAge(a: Announcement, b: Announcement): number {
  const rank = SEVERITY_RANK[a.severity as Severity] - SEVERITY_RANK[b.severity as Severity];
  if (rank !== 0) return rank;
  return a.created_at.localeCompare(b.created_at);
}

export default function AnnouncementStack() {
  // An admin in another session can enable an announcement at any moment, and
  // RTK tag invalidation only reaches the store that issued the mutation —
  // hence the shared cross-session refresh contract rather than a bespoke timer.
  const { data, refetch } = useActiveAnnouncementsQuery(undefined, crossSessionRefreshOptions(false));
  useRefetchOnWindowFocus(refetch, false);

  // Dismissals are mirrored in React state as well as localStorage so the
  // banner leaves immediately even when storage is unavailable. Keyed exactly
  // like the stored entries — on the id alone, an announcement edited while the
  // tab stayed open would never come back.
  const [dismissedThisView, setDismissedThisView] = useState<ReadonlySet<string>>(new Set());

  const onDismissed = useCallback((announcement: Announcement) => {
    markDismissed(announcement.id, announcement.content_version);
    setDismissedThisView((current) =>
      new Set(current).add(dismissalKey(announcement.id, announcement.content_version)),
    );
  }, []);

  // Memoized on the delivered set: a poll that returns identical content still
  // hands back a fresh array, and re-rendering the banners re-runs the markdown
  // parser for every description — once a minute, in every open tab, forever.
  const visible = useMemo(() => {
    const dismissed = readDismissedSet();
    return (data ?? [])
      .filter(
        (announcement) =>
          !dismissedThisView.has(dismissalKey(announcement.id, announcement.content_version)) &&
          !isDismissedIn(dismissed, announcement.id, announcement.content_version),
      )
      .sort(bySeverityThenAge);
  }, [data, dismissedThisView]);

  if (visible.length === 0) return null;

  return (
    <div className={styles.stack}>
      {visible.map((announcement) => (
        <AnnouncementBanner key={announcement.id} announcement={announcement} onDismissed={onDismissed} />
      ))}
    </div>
  );
}

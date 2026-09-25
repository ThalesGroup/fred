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
// Stays the first flex child of `.appShell` (see App.tsx) so banners push the
// routed content down instead of covering it — but skips the query and renders
// nothing until the user is authenticated: announcements are admin-authored
// content served from an authenticated route, never shown on the
// terms-acceptance or root-bootstrap screens.
// ---------------------------------------------------------------------------

import { useCallback, useState } from "react";
import AnnouncementBanner from "@shared/molecules/AnnouncementBanner/AnnouncementBanner";
import { SEVERITY_RANK, type Severity } from "@shared/utils/severity";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { useAuth } from "../../../security/AuthContext";
import { useActiveAnnouncementsQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { Announcement } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { isDismissed, markDismissed } from "./announcementDismissal";
import styles from "./AnnouncementStack.module.css";

/** Most severe first; oldest first within one severity. */
function bySeverityThenAge(a: Announcement, b: Announcement): number {
  const rank = SEVERITY_RANK[a.severity as Severity] - SEVERITY_RANK[b.severity as Severity];
  if (rank !== 0) return rank;
  return a.created_at.localeCompare(b.created_at);
}

export default function AnnouncementStack() {
  const { isAuthenticated } = useAuth();
  // An admin in another session can enable an announcement at any moment, and
  // RTK tag invalidation only reaches the store that issued the mutation —
  // hence the shared cross-session refresh contract rather than a bespoke timer.
  const { data, refetch } = useActiveAnnouncementsQuery(undefined, crossSessionRefreshOptions(!isAuthenticated));
  useRefetchOnWindowFocus(refetch, !isAuthenticated);

  // Dismissals are mirrored in React state as well as localStorage so the
  // banner leaves immediately even when storage is unavailable.
  const [dismissedThisView, setDismissedThisView] = useState<Set<string>>(new Set());

  const onDismissed = useCallback((announcement: Announcement) => {
    markDismissed(announcement.id, announcement.content_version);
    setDismissedThisView((current) => new Set(current).add(announcement.id));
  }, []);

  const visible = (isAuthenticated ? (data ?? []) : [])
    .filter(
      (announcement) =>
        !dismissedThisView.has(announcement.id) && !isDismissed(announcement.id, announcement.content_version),
    )
    .sort(bySeverityThenAge);

  if (visible.length === 0) return null;

  return (
    <div className={styles.stack}>
      {visible.map((announcement) => (
        <AnnouncementBanner key={announcement.id} announcement={announcement} onDismissed={onDismissed} />
      ))}
    </div>
  );
}

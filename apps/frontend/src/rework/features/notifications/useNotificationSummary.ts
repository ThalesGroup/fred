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

// The bell's unseen count, kept fresh by light polling rather than a held-open
// connection: the browser's six connections per origin are already contested.
// Polling stops while the tab is hidden and catches up the moment it returns.

import { useEffect, useState } from "react";
import { useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { useNotificationSummaryQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements";

export const NOTIFICATION_POLL_INTERVAL_MS = 15_000;

const tabVisible = () => typeof document === "undefined" || document.visibilityState !== "hidden";

/** The caller's unseen notification count; 0 until the first answer. */
export function useNotificationSummary(): number {
  const [visible, setVisible] = useState(tabVisible);
  // A tab opened in the background sends nothing until it is first shown.
  const [started, setStarted] = useState(visible);
  const { data, refetch } = useNotificationSummaryQuery(undefined, {
    skip: !started,
    pollingInterval: visible ? NOTIFICATION_POLL_INTERVAL_MS : 0,
  });

  useEffect(() => {
    const onVisibilityChange = () => {
      const nowVisible = tabVisible();
      setVisible(nowVisible);
      if (!nowVisible) return;
      if (started) void refetch();
      else setStarted(true);
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => document.removeEventListener("visibilitychange", onVisibilityChange);
  }, [refetch, started]);
  useRefetchOnWindowFocus(refetch, !started);

  return data?.unseen_count ?? 0;
}

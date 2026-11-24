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

import { useContext, useEffect, useMemo, useRef } from "react";
import { useHref, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useCurrentUserPreference } from "../../../app/userPreferences";
import { useFrontendProperties } from "../../../hooks/useFrontendProperties";
import { ApplicationContext } from "../../../app/ApplicationContextProvider";
import { uiThemeSiteName } from "../../../app/uiThemes";
import { usePatchNoteSettled } from "../announcements/patchNoteSettled";
import { isTourAvailable, isTourRunning, showNotice, startTour, stopTour, type TourTextOptions } from "./runTour";
import { markTourDone, nextTutorialTour, skipTutorial, type CompletedTours } from "./tourProgress";
import { CHAT_TOUR, REPLAY_HINT, findTour } from "./tours";
import { clearTourRequest, openTutorialDialog, requestTour, useTutorialState } from "./tutorialStore";
import { useTutorialEnabled } from "./useTutorialEnabled";

// Waits for the tour's first anchor (the page may still be loading), then gives up quietly.
const POLL_MS = 250;
const MAX_POLLS = 20;
const NO_TOURS: CompletedTours = {};

/** Texts every tour shares: translations, the platform's name, Help Center links. */
export function useTourTexts(): TourTextOptions {
  const { t, i18n } = useTranslation();
  const { siteDisplayName } = useFrontendProperties();
  const { uiTheme } = useContext(ApplicationContext);
  const helpBase = useHref("/help");
  const lang = i18n.language?.startsWith("fr") ? "fr" : "en";
  const site = uiThemeSiteName(uiTheme, siteDisplayName);
  return useMemo(
    () => ({
      t: (key: string, options?: Record<string, string>) => t(key, options),
      values: { site },
      helpHref: (page: string) => `${helpBase}/${lang}/${page}`,
    }),
    [t, site, helpBase, lang],
  );
}

/**
 * The one place tours start: the tour picked in the tutorial dialog, else the next
 * unfinished starter tour once its page is on screen (after the startup patch notes).
 */
export function useTutorialRunner(): void {
  const texts = useTourTexts();
  const { pathname } = useLocation();
  const { requestedTourId, requestCount } = useTutorialState();
  // The admin switch only governs starting on its own; a tour picked in the dialog always plays.
  const tutorialEnabled = useTutorialEnabled();
  const patchNoteSettled = usePatchNoteSettled();
  const initialized = useCurrentUserPreference("initialized", undefined);
  const completed = useCurrentUserPreference("completed_tours", NO_TOURS);
  const autoTour =
    tutorialEnabled && patchNoteSettled && initialized !== undefined ? nextTutorialTour(completed) : undefined;
  const tour = (requestedTourId ? findTour(requestedTourId) : undefined) ?? autoTour;
  const requested = tour !== undefined && tour.id === requestedTourId;
  // The pick whose "where to go" notice was already shown.
  const noticeFor = useRef<number | null>(null);

  useEffect(() => {
    if (!tour || isTourRunning(tour.id)) return;
    const { t } = texts;
    let polls = 0;
    const timer = window.setInterval(() => {
      polls += 1;
      const ready = isTourAvailable(tour);
      // A picked tour off its page waits, across navigation, until the user gets there.
      if (!ready && requested && tour.whereKey && noticeFor.current !== requestCount) {
        noticeFor.current = requestCount;
        showNotice(t("rework.onboarding.pending.title"), t(tour.whereKey), t("rework.onboarding.gotIt"));
      }
      if (!ready && polls < MAX_POLLS) return;
      window.clearInterval(timer);
      if (!ready) return;
      startTour(tour, {
        ...texts,
        onFinish: (done) => {
          if (requested) clearTourRequest();
          if (done) {
            markTourDone(tour);
            // The end of the starter tutorial opens what is left to discover; a chained
            // tour starts the next one once driver.js has torn this one down.
            if (tour.id === CHAT_TOUR.id) openTutorialDialog("discover");
            const next = tour.next;
            if (next) window.setTimeout(() => requestTour(next), 0);
            return;
          }
          if (tour.group !== "starter") return;
          skipTutorial();
          // Once driver.js has torn the skipped tour down: show where to replay it.
          window.setTimeout(() => startTour(REPLAY_HINT, { ...texts, onFinish: () => undefined }), 0);
        },
      });
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [tour, requested, requestCount, pathname, texts]);

  // Leaving the page ends a tour bound to it; a tour that guides across pages goes on.
  useEffect(() => {
    if (!tour || tour.spansPages) return;
    return () => stopTour(tour.id);
  }, [tour, pathname]);
}

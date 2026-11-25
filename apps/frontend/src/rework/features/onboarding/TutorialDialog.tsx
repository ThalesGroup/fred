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

import { useTranslation } from "react-i18next";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import Button from "@shared/atoms/Button/Button";
import Icon from "@shared/atoms/Icon/Icon";
import { useCurrentUserPreference } from "../../../app/userPreferences";
import { isTourDone, restartTutorial, type CompletedTours } from "./tourProgress";
import { usePersonalSpaceFeatures } from "./usePersonalSpaceFeatures";
import { DISCOVER_TOURS, STARTER_TOURS, type TourDefinition, type TourGroup } from "./tours";
import { closeTutorialDialog, openTutorialDialog, requestTour, useTutorialState } from "./tutorialStore";
import styles from "./TutorialDialog.module.css";

const TABS: readonly TourGroup[] = ["starter", "discover"];
const TOURS_BY_TAB = { starter: STARTER_TOURS, discover: DISCOVER_TOURS };
const NO_TOURS: CompletedTours = {};

/** A tour needing a feature is listed once the personal space is known to offer it. */
export const isOffered = (tour: TourDefinition, features: ReadonlySet<string>, loaded: boolean): boolean => {
  if (!tour.requiresFeature) return true;
  const required = Array.isArray(tour.requiresFeature) ? tour.requiresFeature : [tour.requiresFeature];
  return loaded && required.every((feature) => features.has(feature));
};

/** The tutorial's table of contents: every tour, done or not, playable where the user is. */
export function TutorialDialog({ site }: { site: string }) {
  const { t } = useTranslation();
  const { dialogTab } = useTutorialState();
  const { features, loaded } = usePersonalSpaceFeatures(dialogTab === null);
  const completed = useCurrentUserPreference("completed_tours", NO_TOURS);
  if (dialogTab === null) return null;

  const tours = TOURS_BY_TAB[dialogTab].filter((tour) => isOffered(tour, features, loaded));
  const doneCount = tours.filter((tour) => isTourDone(completed, tour)).length;

  return (
    <Dialog
      open
      title={t("rework.onboarding.dialog.title", { site })}
      confirmLabel={t("rework.onboarding.dialog.close")}
      onConfirm={closeTutorialDialog}
      onCancel={closeTutorialDialog}
      hideCancel
      maxWidth={760}
      dense
      footerStart={
        <Button
          color="primary"
          variant="text"
          size="small"
          onClick={() => {
            closeTutorialDialog();
            restartTutorial();
          }}
        >
          {t("rework.onboarding.dialog.restart")}
        </Button>
      }
    >
      <div className={styles.body}>
        <div className={styles.header}>
          <ButtonGroup
            size="small"
            color="secondary"
            variant="radio"
            aria-label={t("rework.onboarding.dialog.tabsAria")}
            selectedIndex={TABS.indexOf(dialogTab)}
            onSelectedIndexChange={(index) => openTutorialDialog(TABS[index] ?? "starter")}
            items={TABS.map((tab) => ({ label: t(`rework.onboarding.dialog.tabs.${tab}`) }))}
          />
          <span className={styles.progress}>
            {t("rework.onboarding.dialog.progress", { done: String(doneCount), total: String(tours.length) })}
          </span>
        </div>
        <ul className={styles.list}>
          {tours.map((tour) => {
            const done = isTourDone(completed, tour);
            return (
              <li key={tour.id}>
                <button
                  type="button"
                  className={styles.row}
                  onClick={() => requestTour(tour.id)}
                  data-done={done || undefined}
                >
                  <span className={styles.icon} aria-hidden="true">
                    <Icon category="outlined" type={tour.icon ?? "school"} />
                  </span>
                  <span className={styles.text}>
                    <span className={styles.label}>{t(`rework.onboarding.${tour.id}.label`)}</span>
                    <span className={styles.summary}>{t(`rework.onboarding.${tour.id}.summary`)}</span>
                  </span>
                  <span className={styles.status} aria-label={t(`rework.onboarding.dialog.${done ? "done" : "todo"}`)}>
                    <Icon category="outlined" type={done ? "check_circle" : "radio_button_unchecked"} filled={done} />
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </Dialog>
  );
}

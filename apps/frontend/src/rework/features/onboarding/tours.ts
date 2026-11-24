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

import type { IconType } from "@shared/utils/Type";
import { TOUR_ANCHORS, type TourAnchor } from "./tourAnchors";

export type TourSide = "top" | "right" | "bottom" | "left";

/** "starter" tours play on their own at first sign-in; "discover" ones only from the tutorial dialog. */
export type TourGroup = "starter" | "discover";

export interface TourStep {
  /** i18n key segment: texts live at `rework.onboarding.<tourId>.<key>.{title,body}`. */
  key: string;
  /** No anchor: a centred popover. A missing or hidden anchor skips the step. */
  anchor?: TourAnchor;
  side?: TourSide;
  /** Help Center page (`<section>/<page>`) linked as "Learn more". */
  helpPage?: string;
}

export interface TourDefinition {
  /** Stored in the user's `completed_tours` preference: never rename a shipped id. */
  id: string;
  /** Bump when the tour changes enough to be shown again to users who saw it. */
  version: number;
  steps: TourStep[];
  /** Listed in the tutorial dialog under this tab, with `rework.onboarding.<id>.{label,summary}`. */
  group?: TourGroup;
  /** Material icon of the tour's row in the tutorial dialog. */
  icon?: IconType;
  /** i18n key telling where the tour can run, shown while its first anchor is off screen. */
  whereKey?: string;
  /** i18n key of the last step's button; defaults to `rework.onboarding.done`. */
  doneKey?: string;
}

const IN_A_CONVERSATION = "rework.onboarding.where.chat";

export const WELCOME_TOUR: TourDefinition = {
  id: "welcome",
  version: 1,
  group: "starter",
  icon: "map",
  steps: [
    { key: "intro", helpPage: "getting-started/first-steps" },
    { key: "panel", anchor: TOUR_ANCHORS.navPanel, side: "right" },
    { key: "home", anchor: TOUR_ANCHORS.navHome, side: "right" },
    { key: "marketplace", anchor: TOUR_ANCHORS.navMarketplace, side: "right" },
    { key: "help", anchor: TOUR_ANCHORS.navHelp, side: "right" },
    { key: "profile", anchor: TOUR_ANCHORS.profileMenu, side: "right" },
  ],
};

export const CHAT_TOUR: TourDefinition = {
  id: "chat",
  version: 1,
  group: "starter",
  icon: "chat",
  whereKey: IN_A_CONVERSATION,
  steps: [
    { key: "composer", anchor: TOUR_ANCHORS.chatComposer, side: "top", helpPage: "getting-started/first-conversation" },
    { key: "actions", anchor: TOUR_ANCHORS.chatActions, side: "top" },
    { key: "panels", anchor: TOUR_ANCHORS.chatPanels, side: "left" },
    { key: "newConversation", anchor: TOUR_ANCHORS.chatNewConversation, side: "bottom" },
  ],
};

export const ADVANCED_CHAT_TOUR: TourDefinition = {
  id: "advanced-chat",
  version: 1,
  group: "discover",
  icon: "auto_awesome",
  whereKey: IN_A_CONVERSATION,
  steps: [
    { key: "commands", anchor: TOUR_ANCHORS.chatComposer, side: "top", helpPage: "features/commands" },
    { key: "attachments", anchor: TOUR_ANCHORS.chatActions, side: "top" },
    { key: "tools", anchor: TOUR_ANCHORS.chatTools, side: "top" },
    { key: "reasoning", anchor: TOUR_ANCHORS.chatReasoning, side: "top" },
    { key: "trace", anchor: TOUR_ANCHORS.chatTrace, side: "bottom", helpPage: "features/chat" },
    { key: "title", anchor: TOUR_ANCHORS.chatTitle, side: "bottom" },
  ],
};

/** Shown after a skipped starter tour: where to replay the tutorial. Not listed anywhere. */
export const REPLAY_HINT: TourDefinition = {
  id: "replay-hint",
  version: 1,
  doneKey: "rework.onboarding.gotIt",
  steps: [{ key: "profile", anchor: TOUR_ANCHORS.profileMenu, side: "right" }],
};

/** Played in order at first sign-in: a tour only starts once every tour before it is done. */
export const STARTER_TOURS: readonly TourDefinition[] = [WELCOME_TOUR, CHAT_TOUR];

/** Offered in the tutorial dialog only. Add a tour here to list it. */
export const DISCOVER_TOURS: readonly TourDefinition[] = [ADVANCED_CHAT_TOUR];

export const LISTED_TOURS: readonly TourDefinition[] = [...STARTER_TOURS, ...DISCOVER_TOURS];

export const findTour = (id: string): TourDefinition | undefined => LISTED_TOURS.find((tour) => tour.id === id);

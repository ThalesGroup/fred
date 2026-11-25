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
import {
  CAP_DOCUMENT_ACCESS,
  CAP_DOCUMENT_SIMILARITY,
  CAP_TEAM_WIKI,
} from "@components/pages/TeamAgentsPage/AgentFormModal/toolPacks";
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
  /** Moves on when the user clicks the anchor; the popover then only offers the close cross. */
  clickToContinue?: boolean;
  /** The anchor appears after an earlier click (a dialog opening): wait for it. */
  waitFor?: boolean;
  /** Moves on once the user has typed this text into the anchor (e.g. "/"). */
  typeToContinue?: string;
  /** Resolved when reached, and skipped at once if its anchor is not there (no waiting). */
  lazy?: boolean;
  /** Shown but not usable during the tour (a detour the user can take afterwards). */
  lookOnly?: boolean;
  /** Moves on once the user closes the anchor by completing it (a form validated): no Next. */
  continueWhenGone?: boolean;
  /** Moves on once one of these anchors appears, which the user's own action causes (no Next). */
  continueWhenShown?: TourAnchor | TourAnchor[];
  /** A sample file under `public/tutorial/`, offered as a download button in the popover. */
  download?: string;
  /** Reads this step's texts from another tour (`rework.onboarding.<textFrom>.<key>`). */
  textFrom?: string;
  /** Lets the user send a chat message while this step is on screen (sending is held back otherwise). */
  allowSend?: boolean;
  /** Leaves the keyboard focus where it is (the composer), so what the user is typing
   * keeps its menu open instead of losing focus to the popover; nothing scrolls either. */
  keepFocus?: boolean;
  /** Example values to copy into the form: `<base>.suggest.<field>.{label,value}`. */
  suggestions?: string[];
  /** Decided when the tour starts, from what is on screen: false drops the step. */
  when?: (onScreen: (anchor: TourAnchor) => boolean) => boolean;
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
  /** Anchor that marks the tour's page; without it the tour plays anywhere (centred start). */
  page?: TourAnchor;
  /** Listed only when the personal space offers this capability id, or all of these (see usePersonalSpaceFeatures). */
  requiresFeature?: string | string[];
  /** Guides the user across pages: navigating keeps it running instead of ending it. */
  spansPages?: boolean;
  /** i18n key telling where the tour can run, shown while its page is not on screen. */
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
  page: TOUR_ANCHORS.chatComposer,
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
  version: 3,
  group: "discover",
  icon: "auto_awesome",
  page: TOUR_ANCHORS.chatComposer,
  whereKey: IN_A_CONVERSATION,
  steps: [
    {
      key: "typeSlash",
      anchor: TOUR_ANCHORS.chatComposer,
      side: "top",
      typeToContinue: "/",
      keepFocus: true,
      helpPage: "features/commands",
    },
    {
      key: "menu",
      anchor: TOUR_ANCHORS.chatCommandMenu,
      side: "right",
      waitFor: true,
      keepFocus: true,
    },
    {
      key: "skill",
      anchor: TOUR_ANCHORS.chatSkills,
      side: "right",
      lazy: true,
      clickToContinue: true,
      keepFocus: true,
    },
    { key: "send", anchor: TOUR_ANCHORS.chatComposer, side: "top", keepFocus: true },
    { key: "attachments", anchor: TOUR_ANCHORS.chatActions, side: "top" },
    { key: "tools", anchor: TOUR_ANCHORS.chatTools, side: "top" },
    { key: "reasoning", anchor: TOUR_ANCHORS.chatReasoning, side: "top" },
    { key: "trace", anchor: TOUR_ANCHORS.chatTrace, side: "bottom", helpPage: "features/chat" },
    { key: "title", anchor: TOUR_ANCHORS.chatTitle, side: "bottom" },
  ],
};

// Where a path starts from decides which navigation steps it needs.
type OnScreen = (anchor: TourAnchor) => boolean;
type PageCheck = (onScreen: OnScreen) => boolean;
const inPersonalSpace: PageCheck = (onScreen) => onScreen(TOUR_ANCHORS.personalHeader);
const inTeam: PageCheck = (onScreen) => onScreen(TOUR_ANCHORS.teamHeader);
const onHome: PageCheck = (onScreen) => onScreen(TOUR_ANCHORS.personalSpaceEntry);

/**
 * Steps leading, from anywhere, into the personal space, then to its `page` (reached by
 * `nav`) when given. Entering the space lands on its agents.
 */
function toPersonalSpace(target?: { page: TourAnchor; nav: TourAnchor }): TourStep[] {
  const steps: TourStep[] = [
    {
      key: "goHome",
      anchor: TOUR_ANCHORS.navHome,
      side: "right",
      clickToContinue: true,
      when: (onScreen) => !onHome(onScreen) && !inPersonalSpace(onScreen),
    },
    {
      key: "openPersonal",
      anchor: TOUR_ANCHORS.personalSpaceEntry,
      side: "right",
      waitFor: true,
      clickToContinue: true,
      when: (onScreen) => !inPersonalSpace(onScreen),
    },
  ];
  if (!target) return steps;
  const { page, nav } = target;
  return [
    ...steps,
    {
      key: "openPage",
      anchor: nav,
      side: "right",
      waitFor: true,
      clickToContinue: true,
      when: (onScreen) =>
        !(inPersonalSpace(onScreen) && onScreen(page)) && (inPersonalSpace(onScreen) || nav !== TOUR_ANCHORS.navAgents),
    },
  ];
}

export const TEAM_TOUR: TourDefinition = {
  id: "team",
  version: 2,
  group: "discover",
  icon: "groups",
  spansPages: true,
  steps: [
    {
      key: "goHome",
      anchor: TOUR_ANCHORS.navHome,
      side: "right",
      clickToContinue: true,
      when: (onScreen) => !onHome(onScreen) && !inTeam(onScreen),
    },
    {
      key: "openTeam",
      anchor: TOUR_ANCHORS.homeTeamList,
      side: "right",
      waitFor: true,
      clickToContinue: true,
      when: (onScreen) => !inTeam(onScreen),
    },
    {
      key: "header",
      anchor: TOUR_ANCHORS.teamHeader,
      side: "right",
      waitFor: true,
      helpPage: "features/teams-and-permissions",
    },
    { key: "agents", anchor: TOUR_ANCHORS.navAgents, side: "right", lazy: true },
    { key: "resources", anchor: TOUR_ANCHORS.navResources, side: "right", lazy: true },
    { key: "prompts", anchor: TOUR_ANCHORS.navPrompts, side: "right", lazy: true },
    { key: "wiki", anchor: TOUR_ANCHORS.navWiki, side: "right", lazy: true },
    { key: "conversations", anchor: TOUR_ANCHORS.conversations, side: "right", lazy: true },
    { key: "settings", anchor: TOUR_ANCHORS.teamSettings, side: "right", lazy: true },
  ],
};

export const PERSONAL_SPACE_TOUR: TourDefinition = {
  id: "personal-space",
  version: 2,
  group: "discover",
  icon: "person",
  spansPages: true,
  steps: [
    ...toPersonalSpace(),
    {
      key: "header",
      anchor: TOUR_ANCHORS.personalHeader,
      side: "right",
      waitFor: true,
      helpPage: "getting-started/first-steps",
    },
    { key: "agents", anchor: TOUR_ANCHORS.navAgents, side: "right", lazy: true },
    { key: "resources", anchor: TOUR_ANCHORS.navResources, side: "right", lazy: true },
    { key: "prompts", anchor: TOUR_ANCHORS.navPrompts, side: "right", lazy: true },
    { key: "usage", anchor: TOUR_ANCHORS.personalUsage, side: "right", lazy: true },
  ],
};

// Shared with the agent-creation tour: same screens, same words.
const AGENT_TEXTS = "create-agent";

/**
 * Agent creation, from the agents page: the user fills each section of the form and
 * moves on by opening the next tab, then creates the agent. `own` is the tour whose
 * texts and example values fill the form (a document agent for the RAG tour).
 */
function agentCreationSteps(own: string, { withAssistant = true } = {}): TourStep[] {
  const shared = own === AGENT_TEXTS ? undefined : AGENT_TEXTS;
  return [
    {
      key: "create",
      textFrom: shared,
      anchor: TOUR_ANCHORS.agentCreate,
      side: "bottom",
      waitFor: true,
      clickToContinue: true,
    },
    {
      key: "template",
      textFrom: shared,
      anchor: TOUR_ANCHORS.agentTemplates,
      side: "top",
      waitFor: true,
      clickToContinue: true,
    },
    {
      key: "general",
      anchor: TOUR_ANCHORS.agentFormBody,
      side: "left",
      waitFor: true,
      suggestions: ["name", "role", "description"],
      // Any later section counts: a template may have no Prompts or no Capabilities tab.
      continueWhenShown: [
        TOUR_ANCHORS.agentInstructions,
        TOUR_ANCHORS.agentCapabilities,
        TOUR_ANCHORS.agentCommitments,
      ],
    },
    {
      key: "instructions",
      anchor: TOUR_ANCHORS.agentFormBody,
      side: "left",
      waitFor: true,
      suggestions: ["instructions"],
      continueWhenShown: [TOUR_ANCHORS.agentCapabilities, TOUR_ANCHORS.agentCommitments],
    },
    {
      key: "capabilities",
      anchor: TOUR_ANCHORS.agentFormBody,
      helpPage: "features/capabilities",
      side: "left",
      waitFor: true,
      continueWhenShown: TOUR_ANCHORS.agentCommitments,
    },
    ...(withAssistant
      ? [
          {
            key: "assistant",
            textFrom: shared,
            anchor: TOUR_ANCHORS.agentAssistant,
            side: "top",
            waitFor: true,
            lookOnly: true,
          } satisfies TourStep,
        ]
      : []),
    {
      key: "commitments",
      anchor: TOUR_ANCHORS.agentModal,
      side: "left",
      waitFor: true,
      suggestions: ["usage"],
      continueWhenGone: true,
    },
  ];
}

/** A whole path, from anywhere, to a first agent in the personal space. */
export const CREATE_AGENT_TOUR: TourDefinition = {
  id: "create-agent",
  version: 4,
  group: "discover",
  icon: "smart_toy",
  spansPages: true,
  steps: [
    { key: "intro", helpPage: "features/agents" },
    ...toPersonalSpace({ page: TOUR_ANCHORS.agentsPage, nav: TOUR_ANCHORS.navAgents }),
    ...agentCreationSteps(AGENT_TEXTS),
  ],
};

/** A whole path, from anywhere, to a first prompt in the personal space, then a test. */
export const PROMPTS_TOUR: TourDefinition = {
  id: "prompts",
  version: 3,
  group: "discover",
  icon: "edit_note",
  spansPages: true,
  steps: [
    { key: "intro", helpPage: "features/prompts" },
    ...toPersonalSpace({ page: TOUR_ANCHORS.promptsPage, nav: TOUR_ANCHORS.navPrompts }),
    { key: "create", anchor: TOUR_ANCHORS.promptCreate, side: "bottom", waitFor: true, clickToContinue: true },
    {
      key: "form",
      anchor: TOUR_ANCHORS.promptModal,
      side: "left",
      waitFor: true,
      helpPage: "features/commands",
      suggestions: ["name", "command", "description", "text"],
      continueWhenGone: true,
    },
    { key: "test" },
  ],
};

/** A whole path, from anywhere, to a first page of the personal space's wiki. */
export const WIKI_TOUR: TourDefinition = {
  id: "wiki",
  version: 4,
  group: "discover",
  icon: "book_2",
  requiresFeature: CAP_TEAM_WIKI,
  spansPages: true,
  steps: [
    { key: "intro" },
    ...toPersonalSpace({ page: TOUR_ANCHORS.wikiTree, nav: TOUR_ANCHORS.navWiki }),
    { key: "tree", anchor: TOUR_ANCHORS.wikiTree, side: "right", waitFor: true },
    { key: "newPage", anchor: TOUR_ANCHORS.wikiNewPage, side: "right", waitFor: true, clickToContinue: true },
    {
      key: "title",
      anchor: TOUR_ANCHORS.wikiNewPageDialog,
      side: "bottom",
      waitFor: true,
      suggestions: ["title"],
      continueWhenGone: true,
    },
    { key: "edit", anchor: TOUR_ANCHORS.wikiEdit, side: "bottom", waitFor: true, clickToContinue: true },
    {
      key: "content",
      anchor: TOUR_ANCHORS.wikiEditor,
      side: "left",
      waitFor: true,
      suggestions: ["content"],
      continueWhenGone: true,
    },
    { key: "rules", anchor: TOUR_ANCHORS.wikiRules, side: "right", waitFor: true },
  ],
};

const notInAFolder = (onScreen: OnScreen) => !onScreen(TOUR_ANCHORS.resourcesUpload);

/**
 * Consulting documents: the intro sets RAG (resources an agent searches) against an
 * attachment (one conversation); the tour then walks through RAG.
 */
export const RAG_TOUR: TourDefinition = {
  id: "rag",
  version: 5,
  group: "discover",
  icon: "description",
  // The "Team documents" pack needs both: reading documents and searching them.
  requiresFeature: [CAP_DOCUMENT_ACCESS, CAP_DOCUMENT_SIMILARITY],
  spansPages: true,
  steps: [
    { key: "intro", helpPage: "guides/build-rag-assistant" },
    { key: "download", download: "aurora-station-discoveries.md" },
    ...toPersonalSpace({ page: TOUR_ANCHORS.resourcesPage, nav: TOUR_ANCHORS.navResources }),
    {
      key: "newFolder",
      anchor: TOUR_ANCHORS.resourcesNewFolder,
      side: "bottom",
      waitFor: true,
      clickToContinue: true,
      when: notInAFolder,
    },
    {
      key: "folderName",
      anchor: TOUR_ANCHORS.folderModal,
      side: "right",
      waitFor: true,
      suggestions: ["name"],
      continueWhenGone: true,
      when: notInAFolder,
    },
    {
      key: "openFolder",
      anchor: TOUR_ANCHORS.resourcesExplorer,
      side: "top",
      waitFor: true,
      continueWhenShown: TOUR_ANCHORS.resourcesUpload,
      when: notInAFolder,
    },
    { key: "upload", anchor: TOUR_ANCHORS.resourcesUpload, side: "bottom", waitFor: true, clickToContinue: true },
    { key: "drop", anchor: TOUR_ANCHORS.uploadDrawer, side: "right", waitFor: true, continueWhenGone: true },
    { key: "processing" },
    { key: "goAgents", anchor: TOUR_ANCHORS.navAgents, side: "right", waitFor: true, clickToContinue: true },
    ...agentCreationSteps("rag", { withAssistant: false }),
    { key: "openAgent", anchor: TOUR_ANCHORS.agentList, side: "top", waitFor: true, clickToContinue: true },
    {
      key: "ask",
      anchor: TOUR_ANCHORS.chatComposer,
      side: "top",
      waitFor: true,
      keepFocus: true,
      allowSend: true,
      suggestions: ["question"],
      // Resumes on the complete answer, then walks through it.
      continueWhenShown: TOUR_ANCHORS.chatAnswer,
    },
    // Shown, not usable yet: the walkthrough ends before the user explores the answer.
    { key: "answer", anchor: TOUR_ANCHORS.chatAnswer, side: "top", waitFor: true, lookOnly: true },
    { key: "sources", anchor: TOUR_ANCHORS.chatSources, side: "top", lazy: true, lookOnly: true },
    { key: "trace", anchor: TOUR_ANCHORS.chatTrace, side: "bottom", lazy: true, lookOnly: true },
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
export const DISCOVER_TOURS: readonly TourDefinition[] = [
  ADVANCED_CHAT_TOUR,
  TEAM_TOUR,
  PERSONAL_SPACE_TOUR,
  CREATE_AGENT_TOUR,
  RAG_TOUR,
  PROMPTS_TOUR,
  WIKI_TOUR,
];

export const LISTED_TOURS: readonly TourDefinition[] = [...STARTER_TOURS, ...DISCOVER_TOURS];

export const findTour = (id: string): TourDefinition | undefined => LISTED_TOURS.find((tour) => tour.id === id);

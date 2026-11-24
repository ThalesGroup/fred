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

// Every element a guided tour points at carries `data-tour="<anchor>"`.
// Tours never use CSS classes or DOM structure, so restyling a page keeps them working.
export const TOUR_ANCHORS = {
  navPanel: "nav-panel",
  navHome: "nav-home",
  navMarketplace: "nav-marketplace",
  navHelp: "nav-help",
  profileMenu: "profile-menu",
  chatComposer: "chat-composer",
  chatActions: "chat-actions",
  chatPanels: "chat-panels",
  chatNewConversation: "chat-new-conversation",
  chatTools: "chat-tools",
  chatReasoning: "chat-reasoning",
  chatTrace: "chat-trace",
  chatTitle: "chat-title",
  chatCommandMenu: "chat-command-menu",
  chatSkills: "chat-skills",
  homeTeamList: "home-team-list",
  teamHeader: "team-header",
  personalHeader: "personal-header",
  navAgents: "nav-agents",
  navResources: "nav-resources",
  navPrompts: "nav-prompts",
  navWiki: "nav-wiki",
  conversations: "conversations",
  teamSettings: "team-settings",
  personalUsage: "personal-usage",
  agentsPage: "agents-page",
  agentCreate: "agent-create",
  agentList: "agent-list",
  promptsPage: "prompts-page",
  promptCreate: "prompt-create",
  promptFilters: "prompt-filters",
  wikiTree: "wiki-tree",
  wikiNewPage: "wiki-new-page",
  wikiRules: "wiki-rules",
  wikiReview: "wiki-review",
  personalSpaceEntry: "personal-space-entry",
  agentTemplates: "agent-templates",
  agentForm: "agent-form",
  agentToolsTab: "agent-tools-tab",
  agentAssistant: "agent-assistant",
  agentPromptsTab: "agent-prompts-tab",
  agentInstructions: "agent-instructions",
  agentCommitmentsTab: "agent-commitments-tab",
  agentCommitments: "agent-commitments",
  promptDescription: "prompt-description",
  wikiTitleInput: "wiki-title-input",
  wikiCreateConfirm: "wiki-create-confirm",
  wikiEdit: "wiki-edit",
  wikiEditorBody: "wiki-editor-body",
  wikiSave: "wiki-save",
  agentCapabilities: "agent-capabilities",
  agentAdvanced: "agent-advanced",
  agentSubmit: "agent-submit",
  promptName: "prompt-name",
  promptCommand: "prompt-command",
  promptText: "prompt-text",
  promptSubmit: "prompt-submit",
} as const;

export type TourAnchor = (typeof TOUR_ANCHORS)[keyof typeof TOUR_ANCHORS];

export const tourAnchorSelector = (anchor: TourAnchor): string => `[data-tour="${anchor}"]`;

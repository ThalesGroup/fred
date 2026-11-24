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
} as const;

export type TourAnchor = (typeof TOUR_ANCHORS)[keyof typeof TOUR_ANCHORS];

export const tourAnchorSelector = (anchor: TourAnchor): string => `[data-tour="${anchor}"]`;

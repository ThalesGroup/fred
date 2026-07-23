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

import type { MaterialIconType } from "./Type.ts";

/**
 * Ordered keyword → icon rules for `guessAgentIcon` (#2076 follow-up).
 *
 * Deterministic keyword heuristic, not an LLM call: cheap, instant, and
 * reproducible, at the cost of missing an abstractly-worded mission with no
 * matching keyword (falls through to the site default in that case). Order
 * matters — more specific domains are listed before generic catch-alls so a
 * narrower match wins (e.g. "legal contract review" hits `legal` before the
 * generic `writing` rule could claim "review").
 *
 * Keywords are matched case-insensitively as plain substrings against the
 * agent's name + role + description combined, in both French and English —
 * the two languages this app ships translations for.
 */
const AGENT_ICON_RULES: { icon: MaterialIconType; keywords: string[] }[] = [
  {
    icon: "gavel",
    keywords: ["legal", "juridique", "contrat", "contract", "compliance", "conformité", "droit", "law"],
  },
  {
    icon: "shield",
    keywords: ["sécurité", "securite", "security", "secure", "vulnérab", "vulnerab", "threat", "menace", "pentest"],
  },
  {
    icon: "support_agent",
    keywords: ["support", "assistance", "helpdesk", "help desk", "service client", "customer service", "sav"],
  },
  {
    icon: "translate",
    keywords: ["traduc", "translat", "langue", "language"],
  },
  {
    icon: "payments",
    keywords: ["finance", "financ", "facture", "invoice", "budget", "comptab", "accounting", "paiement", "payment"],
  },
  {
    icon: "code",
    keywords: [
      "code",
      "coding",
      "dévelop",
      "develop",
      "programm",
      "github",
      "software",
      "logiciel",
      "devops",
      "ingénieur",
      "engineer",
    ],
  },
  {
    icon: "database",
    keywords: ["base de données", "database", "sql", "entrepôt de données", "data warehouse"],
  },
  {
    icon: "analytics",
    keywords: ["analytic", "analyse", "statistiq", "statistic", "dashboard", "kpi", "métrique", "metric"],
  },
  {
    icon: "campaign",
    keywords: ["marketing", "campagne", "campaign", "publicité", "advertis", "réseaux sociaux", "social media"],
  },
  {
    icon: "groups",
    keywords: ["rh", "ressources humaines", "recrut", "recruit", "onboarding", "talent"],
  },
  {
    icon: "travel_explore",
    keywords: ["recherche", "research", "veille", "explorat", "investigat"],
  },
  {
    icon: "picture_as_pdf",
    keywords: ["pdf"],
  },
  {
    icon: "slideshow",
    keywords: ["présentation", "presentation", "slide", "powerpoint", "ppt"],
  },
  {
    icon: "video_file",
    keywords: ["vidéo", "video"],
  },
  {
    icon: "audio_file",
    keywords: ["audio", "podcast", "voix", "voice"],
  },
  {
    icon: "image",
    keywords: ["image", "photo", "visuel"],
  },
  {
    icon: "edit_calendar",
    keywords: ["planning", "calendar", "calendrier", "schedul", "rendez-vous", "réunion", "meeting"],
  },
  {
    icon: "mail",
    keywords: ["email", "e-mail", "courriel"],
  },
  {
    icon: "summarize",
    keywords: ["résum", "summar", "synthèse", "synthesis"],
  },
  {
    icon: "edit_note",
    keywords: ["rédac", "writ", "draft", "contenu", "content", "blog", "article"],
  },
  {
    icon: "admin_panel_settings",
    keywords: ["admin", "gouvernance", "governance", "politique", "policy"],
  },
  {
    icon: "search",
    keywords: ["search", "rechercher", "lookup", "requête"],
  },
];

/**
 * Guess a Material Symbol for an agent card from its name, role, and
 * description — a best-effort visual hint, not a guarantee of relevance.
 *
 * Falls back to `fallback` (normally the site's configured default agent
 * icon) when no keyword rule matches.
 */
export function guessAgentIcon(
  displayName: string,
  role: string,
  description: string,
  fallback: MaterialIconType,
): MaterialIconType {
  const haystack = `${displayName} ${role} ${description}`.toLowerCase();
  const match = AGENT_ICON_RULES.find((rule) => rule.keywords.some((keyword) => haystack.includes(keyword)));
  return match?.icon ?? fallback;
}

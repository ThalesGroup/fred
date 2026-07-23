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
 * Keyword → icon rules for `guessAgentIcon` (#2076 follow-up).
 *
 * The 40 categories cover the day-to-day activities of a digital-services
 * company (ESN) — office work, engineering, finance, HR, legal, sales — the
 * intended audience for these ReAct assistants. Deliberately not exhaustive
 * of every possible profession (e.g. no aviation/medical/food-service
 * categories): a keyword-matching heuristic degrades in quality well before
 * it degrades in speed (see #2076 discussion) — collisions between
 * lookalike keywords across unrelated categories get more likely, and more
 * order-dependent, as the rule count grows. 40 well-differentiated, broadly
 * relevant categories is judged the right size for this audience; adding
 * niche categories on a one-off basis is a trap; extend deliberately.
 *
 * Each rule is scored by how many of its distinct keywords appear in the
 * agent's name + role + description (case-insensitive substring match) —
 * not just whether at least one does. The highest-scoring rule wins; ties
 * keep the first one in array order, so near-duplicate categories should
 * still be ordered by which reading feels more central to the role. This
 * scoring (vs. the earlier first-match-wins) is what gives icon selection
 * more diversity: an agent whose description leans heavily into one
 * category's vocabulary no longer loses to an earlier rule that happens to
 * match on a single incidental word.
 */
const AGENT_ICON_RULES: { icon: MaterialIconType; keywords: string[] }[] = [
  // ── Engineering / IT ──────────────────────────────────────────────────
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
      "ingénieur",
      "engineer",
      "api",
    ],
  },
  {
    icon: "cloud",
    keywords: ["cloud", "devops", "kubernetes", "infrastructure", "infra", "déploiement", "deployment", "serveur"],
  },
  {
    icon: "database",
    keywords: ["base de données", "database", "sql", "entrepôt de données", "data warehouse"],
  },
  {
    icon: "architecture",
    keywords: ["architecture", "conception technique", "technical design", "urbanisation", "schéma technique"],
  },
  {
    icon: "bug_report",
    keywords: ["test", "qa", "qualité logicielle", "bug", "anomalie", "recette", "non-régression", "regression"],
  },
  {
    icon: "shield",
    keywords: [
      "sécurité",
      "securite",
      "security",
      "secure",
      "cybersécurité",
      "vulnérab",
      "vulnerab",
      "threat",
      "menace",
      "pentest",
    ],
  },
  {
    icon: "sync_alt",
    keywords: ["intégration", "integration", "synchronis", "sync", "etl", "flux de données", "data pipeline"],
  },

  // ── Data / Analysis ───────────────────────────────────────────────────
  {
    icon: "analytics",
    keywords: ["analytic", "analyse", "statistiq", "statistic", "dashboard", "kpi", "métrique", "metric"],
  },
  {
    icon: "table_chart",
    keywords: ["tableur", "spreadsheet", "excel", "reporting", "rapport chiffré", "tableau de données"],
  },
  {
    icon: "find_in_page",
    keywords: ["recherche documentaire", "document search", "rag", "corpus", "base documentaire", "knowledge base"],
  },
  {
    icon: "travel_explore",
    keywords: ["veille", "market research", "recherche", "research", "explorat", "investigat", "innovation"],
  },

  // ── Writing / Documents / Media ───────────────────────────────────────
  {
    icon: "edit_note",
    keywords: ["rédac", "writ", "draft", "contenu", "content", "blog", "article"],
  },
  {
    icon: "summarize",
    keywords: ["résum", "summar", "synthèse", "synthesis"],
  },
  {
    icon: "translate",
    keywords: ["traduc", "translat", "langue", "language"],
  },
  {
    icon: "description",
    keywords: ["document", "documentation", "rapport", "report", "compte rendu"],
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
    icon: "image",
    keywords: ["image", "photo", "visuel", "design graphique"],
  },
  {
    icon: "video_file",
    keywords: ["vidéo", "video"],
  },
  {
    icon: "audio_file",
    keywords: ["audio", "podcast", "voix", "voice", "transcription"],
  },
  {
    icon: "folder",
    keywords: ["fichier", "file", "classement", "gestion documentaire", "archivage"],
  },

  // ── Office / Productivity ─────────────────────────────────────────────
  {
    icon: "mail",
    keywords: ["email", "e-mail", "courriel"],
  },
  {
    icon: "edit_calendar",
    keywords: ["planning", "calendar", "calendrier", "schedul", "rendez-vous", "réunion", "meeting"],
  },
  {
    icon: "assignment",
    keywords: [
      "gestion de projet",
      "project management",
      "tâche",
      "planification de projet",
      "jalons",
      "milestone",
      // "pilote"/"piloter"/"pilotage" are French business jargon for project
      // steering ("comité de pilotage", "piloter un projet") — nothing to do
      // with aviation, and squarely relevant to an ESN (#2076 discussion).
      "pilote",
      "piloter",
      "pilotage",
      "chef de projet",
    ],
  },
  {
    icon: "check_circle",
    keywords: ["checklist", "suivi de tâches", "task tracking", "to-do", "todo"],
  },
  {
    icon: "history",
    keywords: ["historique", "history", "traçabilité", "audit trail", "journal des événements", "log"],
  },
  {
    icon: "map",
    keywords: ["voyage", "travel", "déplacement professionnel", "itinéraire", "itinerary", "note de frais mission"],
  },
  {
    icon: "forum",
    keywords: ["assistant conversationnel", "conversational assistant", "questions réponses", "faq"],
  },

  // ── Support / Operations ──────────────────────────────────────────────
  {
    icon: "support_agent",
    keywords: ["support", "assistance", "helpdesk", "help desk", "service client", "customer service", "sav"],
  },
  {
    icon: "build",
    keywords: ["outils internes", "internal tooling", "maintenance", "dépannage", "troubleshoot"],
  },

  // ── HR ─────────────────────────────────────────────────────────────────
  {
    icon: "groups",
    keywords: ["rh", "ressources humaines", "recrut", "recruit", "onboarding", "talent"],
  },
  {
    icon: "school",
    keywords: ["formation", "training", "apprentissage", "e-learning", "montée en compétence", "upskilling"],
  },

  // ── Finance ────────────────────────────────────────────────────────────
  {
    icon: "payments",
    keywords: ["finance", "financ", "budget", "comptab", "accounting", "paiement", "payment", "trésorerie"],
  },
  {
    icon: "receipt_long",
    keywords: ["facture", "invoice", "facturation", "billing", "note de frais"],
  },
  {
    icon: "shopping_cart",
    keywords: ["achat", "procurement", "fournisseur", "supplier", "approvisionnement", "commande"],
  },

  // ── Legal / Compliance ────────────────────────────────────────────────
  {
    icon: "gavel",
    keywords: ["legal", "juridique", "contrat", "contract", "droit", "law"],
  },
  {
    icon: "admin_panel_settings",
    keywords: ["conformité", "compliance", "gouvernance", "governance", "politique interne", "policy", "audit"],
  },

  // ── Sales / Marketing ─────────────────────────────────────────────────
  {
    icon: "handshake",
    keywords: ["commercial", "vente", "sales", "négociation", "negotiation", "relation client", "account management"],
  },
  {
    icon: "request_quote",
    keywords: ["devis", "quote", "appel d'offres", "rfp", "avant-vente", "proposition commerciale"],
  },
  {
    icon: "campaign",
    keywords: ["marketing", "campagne", "campaign", "publicité", "advertis", "réseaux sociaux", "social media"],
  },
];

function scoreRule(keywords: string[], haystack: string): number {
  return keywords.reduce((score, keyword) => score + (haystack.includes(keyword) ? 1 : 0), 0);
}

/**
 * Guess a Material Symbol for an agent card from its name, role, and
 * description — a best-effort visual hint, not a guarantee of relevance.
 *
 * Each category is scored by how many of its distinct keywords match; the
 * highest score wins (ties keep the earlier category in `AGENT_ICON_RULES`).
 * Falls back to `fallback` (normally the site's configured default agent
 * icon) when every category scores zero.
 */
export function guessAgentIcon(
  displayName: string,
  role: string,
  description: string,
  fallback: MaterialIconType,
): MaterialIconType {
  const haystack = `${displayName} ${role} ${description}`.toLowerCase();
  let best: { icon: MaterialIconType; score: number } | undefined;
  for (const rule of AGENT_ICON_RULES) {
    const score = scoreRule(rule.keywords, haystack);
    if (score > 0 && (!best || score > best.score)) {
      best = { icon: rule.icon, score };
    }
  }
  return best?.icon ?? fallback;
}

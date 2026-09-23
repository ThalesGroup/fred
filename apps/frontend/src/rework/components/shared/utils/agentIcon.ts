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

import { materialIcons, type MaterialIconType } from "./Type.ts";

type AgentIconRule = {
  icon: MaterialIconType;
  /** Names the domain on its own — one hit carries the category. */
  strong?: string[];
  /** Generic or ambiguous alone — needs a second keyword from the same rule. */
  keywords?: string[];
};

/**
 * Keyword → icon rules for `guessAgentIcon` (#2076 follow-up).
 *
 * The 60 categories cover the day-to-day activities of a digital-services
 * company (ESN) — office work, engineering, data, finance, HR, legal, sales,
 * product. Deliberately not exhaustive of every profession (no aviation,
 * medical or food-service categories): a keyword-matching heuristic degrades
 * in quality well before it degrades in speed, because collisions between
 * lookalike keywords across unrelated categories get more likely, and more
 * order-dependent, as the rule count grows. Extend deliberately, in families,
 * not one niche category at a time.
 *
 * Keywords are bilingual (FR/EN) and matched as case-insensitive substrings,
 * so a stem ("rédac", "financ") covers its inflections. They are split by how
 * much one hit proves: a `strong` keyword names the domain and scores 2 (an
 * acronym like "ppt"/"rgpd", a product name, a practice like "plan de
 * charge"), a plain keyword scores 1 because it also shows up outside its
 * domain ("test", "analyse", "document", "log"). Points are summed over the
 * agent's name + role + description, the highest total at or above
 * `MIN_ICON_SCORE` wins, ties keep the first rule in array order. So
 * near-duplicate categories should be ordered by which reading feels more
 * central to the role, and a new category placed at the end of its family
 * never steals a tie from an older one.
 *
 * Beware French plurals: a multi-word keyword is matched literally, so
 * "poste de travail" does not match "postes de travail".
 *
 * Exported for the test that replays every `strong` keyword on its own: a new
 * one shadowed by an earlier rule's substring is otherwise silently dead.
 */
export const AGENT_ICON_RULES: AgentIconRule[] = [
  // ── Engineering / IT ──────────────────────────────────────────────────
  {
    icon: "code",
    strong: ["github", "programm"],
    keywords: ["code", "coding", "dévelop", "develop", "software", "logiciel", "ingénieur", "engineer", "api"],
  },
  {
    icon: "cloud",
    strong: ["cloud", "kubernetes", "devops"],
    keywords: ["infra", "déploiement", "deployment", "serveur"],
  },
  {
    icon: "database",
    strong: ["base de données", "database", "sql", "entrepôt de données", "data warehouse"],
  },
  {
    icon: "architecture",
    strong: ["architecture", "conception technique", "technical design", "urbanisation", "schéma technique"],
  },
  {
    icon: "bug_report",
    strong: ["qualité logicielle", "non-régression", "bug"],
    keywords: ["test", "qa", "anomalie", "recette", "regression"],
  },
  {
    icon: "shield",
    strong: ["vulnérab", "vulnerab", "pentest", "sécurité", "security"],
    keywords: ["securite", "secure", "threat", "menace"],
  },
  {
    icon: "sync_alt",
    strong: ["etl", "flux de données", "data pipeline", "sync"],
    keywords: ["intégration", "integration"],
  },
  {
    icon: "neurology",
    strong: [
      "intelligence artificielle",
      "artificial intelligence",
      "llm",
      "machine learning",
      "apprentissage automatique",
      "modèle de langage",
      "genai",
    ],
    keywords: ["prompt"],
  },
  {
    icon: "hub",
    strong: ["workflow", "orchestration", "rpa", "chaîne de traitement"],
    keywords: ["automatis", "automation"],
  },
  {
    icon: "extension",
    strong: ["connecteur", "connector", "plugin", "mcp", "interopérab"],
    keywords: ["extension"],
  },
  {
    icon: "new_releases",
    strong: ["changelog", "note de version", "montée de version", "livraison logicielle", "mise en production"],
    keywords: ["release"],
  },
  // ── Data / Analysis ───────────────────────────────────────────────────
  {
    icon: "analytics",
    strong: ["kpi", "dashboard", "statistiq", "statistic", "analytic"],
    keywords: ["analyse", "métrique", "metric"],
  },
  {
    icon: "table_chart",
    strong: ["tableur", "spreadsheet", "excel", "rapport chiffré", "tableau de données"],
    keywords: ["reporting"],
  },
  {
    icon: "find_in_page",
    strong: [
      "recherche documentaire",
      "document search",
      "rag",
      "base documentaire",
      "knowledge base",
      "base de connaissances",
      "wiki",
      "corpus",
    ],
  },
  {
    icon: "travel_explore",
    strong: ["veille", "market research", "explorat", "investigat"],
    keywords: ["recherche", "innovation"],
  },
  {
    icon: "show_chart",
    strong: ["prévision", "forecast", "prospective"],
    keywords: ["projection", "tendance", "trend"],
  },
  {
    icon: "category",
    strong: ["taxonomie", "classification", "catégorisation", "métadonnées", "metadata", "nomenclature", "étiquetage"],
  },
  {
    icon: "upload_file",
    strong: [
      "import de données",
      "importation",
      "export de données",
      "exportation",
      "migration de données",
      "reprise de données",
      "chargement de fichiers",
    ],
  },
  // ── Writing / Documents / Media ───────────────────────────────────────
  {
    icon: "edit_note",
    strong: ["rédac", "blog"],
    keywords: ["writ", "draft", "contenu", "content", "article"],
  },
  {
    icon: "summarize",
    strong: ["résum", "summar", "synthèse", "synthesis"],
  },
  {
    icon: "translate",
    strong: ["traduc", "translat"],
    keywords: ["langue", "language"],
  },
  {
    icon: "description",
    strong: ["documentation"],
    keywords: ["document", "compte rendu", "rapport", "report"],
  },
  {
    icon: "picture_as_pdf",
    strong: ["pdf", "acrobat"],
  },
  {
    icon: "slideshow",
    strong: ["présentation", "presentation", "powerpoint", "ppt", "slide"],
  },
  {
    icon: "image",
    strong: ["design graphique", "photo"],
    keywords: ["image", "visuel"],
  },
  {
    icon: "video_file",
    strong: ["vidéo", "video", "sous-titr"],
    keywords: ["montage"],
  },
  {
    icon: "audio_file",
    strong: ["podcast", "audio", "transcription"],
    keywords: ["voix", "voice"],
  },
  {
    icon: "folder",
    strong: ["gestion documentaire", "archivage", "classement"],
    keywords: ["fichier", "file"],
  },
  {
    icon: "book_2",
    strong: ["référentiel", "bonnes pratiques", "méthodologie", "guide pratique"],
    keywords: ["norme", "procédure"],
  },
  {
    icon: "article",
    strong: ["revue de presse", "communiqué", "éditorial", "actualités"],
    keywords: ["presse", "publication"],
  },
  {
    icon: "help_center",
    strong: [
      "centre d'aide",
      "aide en ligne",
      "self-service",
      "libre-service",
      "aide utilisateur",
      "guide de prise en main",
    ],
  },
  // ── Office / Productivity ─────────────────────────────────────────────
  {
    icon: "mail",
    strong: ["email", "e-mail", "courriel", "newsletter", "infolettre"],
  },
  {
    icon: "edit_calendar",
    strong: ["planning", "calendar", "calendrier", "schedul", "rendez-vous"],
    keywords: ["réunion", "meeting"],
  },
  {
    icon: "assignment",
    strong: [
      "gestion de projet",
      "project management",
      "planification de projet",
      "jalons",
      "milestone",
      "chef de projet",
    ],
    keywords: [
      // "pilote"/"piloter"/"pilotage" are French business jargon for project
      // steering ("comité de pilotage", "piloter un projet") — nothing to do
      // with aviation, and squarely relevant to an ESN (#2076 discussion).
      "tâche",
      "pilote",
      "pilotage",
    ],
  },
  {
    icon: "check_circle",
    strong: ["checklist", "suivi de tâches", "task tracking", "to-do", "todo"],
  },
  {
    icon: "history",
    strong: ["historique", "traçabilité", "audit trail", "journal des événements"],
    keywords: ["history", "log"],
  },
  {
    icon: "map",
    strong: ["voyage", "déplacement professionnel", "itinéraire", "itinerary", "note de frais mission"],
    keywords: ["travel"],
  },
  {
    icon: "forum",
    strong: ["assistant conversationnel", "conversational assistant", "questions réponses", "faq"],
  },
  {
    icon: "schedule",
    strong: [
      "compte rendu d'activité",
      "timesheet",
      "feuille de temps",
      "imputation",
      "temps passé",
      "saisie des temps",
    ],
  },
  {
    icon: "quiz",
    strong: ["questionnaire", "sondage", "qcm", "quiz", "évaluation des connaissances"],
    keywords: ["enquête"],
  },
  {
    icon: "lightbulb",
    strong: ["idéation", "brainstorm", "design thinking", "atelier créatif", "génération d'idées"],
    keywords: ["créativité"],
  },
  // ── Support / Operations ──────────────────────────────────────────────
  {
    icon: "support_agent",
    strong: ["helpdesk", "help desk", "service client", "customer service", "service après-vente"],
    keywords: ["support", "assistance"],
  },
  {
    icon: "build",
    strong: ["outils internes", "internal tooling", "dépannage", "troubleshoot"],
    keywords: ["maintenance"],
  },
  {
    icon: "warning",
    strong: ["incident", "astreinte", "post-mortem", "outage", "gestion de crise"],
    keywords: ["panne", "escalade"],
  },
  {
    icon: "desktop_windows",
    strong: ["poste de travail", "parc informatique", "matériel informatique", "workstation", "support de proximité"],
    keywords: ["hardware"],
  },
  // ── HR ─────────────────────────────────────────────────────────────────
  {
    icon: "groups",
    strong: ["ressources humaines", "recrut", "recruit", "onboarding", "talent"],
    keywords: ["rh"],
  },
  {
    icon: "school",
    strong: ["formation", "e-learning", "montée en compétence", "upskilling"],
    keywords: ["training", "apprentissage"],
  },
  {
    icon: "people",
    strong: ["staffing", "plan de charge", "intercontrat", "disponibilité des consultants"],
    keywords: ["affectation", "effectifs"],
  },
  // ── Finance ────────────────────────────────────────────────────────────
  {
    icon: "payments",
    strong: ["comptab", "accounting", "trésorerie", "financ"],
    keywords: ["budget", "paiement", "payment"],
  },
  {
    icon: "receipt_long",
    strong: ["facture", "invoice", "facturation", "billing", "note de frais"],
  },
  {
    icon: "shopping_cart",
    strong: ["achat", "procurement", "fournisseur", "supplier", "approvisionnement"],
    keywords: ["commande"],
  },
  // ── Legal / Compliance ────────────────────────────────────────────────
  {
    icon: "gavel",
    strong: ["juridique", "contrat", "contract", "law"],
    keywords: ["legal", "droit"],
  },
  {
    icon: "admin_panel_settings",
    strong: ["conformité", "compliance", "gouvernance", "governance", "politique interne"],
    keywords: ["policy", "audit"],
  },
  {
    icon: "lock",
    strong: ["rgpd", "gdpr", "données personnelles", "anonymisation", "pseudonymisation", "vie privée"],
    keywords: ["confidentialité"],
  },
  // ── Sales / Marketing ─────────────────────────────────────────────────
  {
    icon: "handshake",
    strong: ["commercial", "négociation", "relation client", "account management"],
    keywords: ["vente", "sales", "negotiation"],
  },
  {
    icon: "request_quote",
    strong: ["devis", "appel d'offres", "rfp", "avant-vente"],
    keywords: ["quote"],
  },
  {
    icon: "campaign",
    strong: ["marketing", "campagne", "campaign", "publicité", "réseaux sociaux", "social media"],
    keywords: ["advertis"],
  },
  {
    icon: "reviews",
    strong: ["satisfaction", "avis client", "nps", "csat", "retour client"],
    keywords: ["feedback"],
  },
  // ── Produit / Design ──────────────────────────────────────────────────
  {
    icon: "rocket_launch",
    strong: ["go-to-market", "mise sur le marché", "roadmap produit", "product launch", "time to market"],
    keywords: ["lancement"],
  },
  {
    icon: "widgets",
    strong: [
      "design system",
      "maquette",
      "wireframe",
      "interface utilisateur",
      "expérience utilisateur",
      "ergonomie",
      "figma",
    ],
    keywords: ["prototype"],
  },
];

/* A category needs 2 points to win, so one `strong` hit is enough but a lone
   generic word is not ("test" in a name, "analyse" in a template's boilerplate
   description). An honest fallback beats a confidently wrong icon. */
const MIN_ICON_SCORE = 2;

function scoreRule(rule: AgentIconRule, haystack: string): number {
  const hits = (keywords: string[] | undefined) => (keywords ?? []).filter((k) => haystack.includes(k)).length;
  return 2 * hits(rule.strong) + hits(rule.keywords);
}

/**
 * Guess a Material Symbol for an agent card from its name, role, and
 * description — a best-effort visual hint, not a guarantee of relevance.
 *
 * Each category scores 2 per matching `strong` keyword and 1 per plain one;
 * the highest total wins (ties keep the earlier category in
 * `AGENT_ICON_RULES`). Falls back to `fallback` (normally the site's
 * configured default agent icon) when no category reaches `MIN_ICON_SCORE`.
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
    const score = scoreRule(rule, haystack);
    if (score >= MIN_ICON_SCORE && (!best || score > best.score)) {
      best = { icon: rule.icon, score };
    }
  }
  return best?.icon ?? fallback;
}

/** The icon to render for an agent instance: a keyword guess from its own
 * identity, falling back to the site-configured default (an untyped config
 * string, validated to the material subset like `toIconType` does) and finally
 * to `smart_toy`. One source of truth for AgentCard and the compact Home tiles. */
export function resolveAgentIcon(
  instance: { display_name: string; role: string; description?: string | null },
  configuredDefault: string,
): MaterialIconType {
  const fallback: MaterialIconType = (materialIcons as readonly string[]).includes(configuredDefault)
    ? (configuredDefault as MaterialIconType)
    : "smart_toy";
  return guessAgentIcon(instance.display_name, instance.role, instance.description ?? "", fallback);
}

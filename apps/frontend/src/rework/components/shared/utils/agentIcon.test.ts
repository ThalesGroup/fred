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

import { describe, expect, it } from "vitest";
import { AGENT_ICON_RULES, guessAgentIcon } from "./agentIcon";

describe("guessAgentIcon", () => {
  it("matches keywords in the role when the name and description are unhelpful", () => {
    expect(guessAgentIcon("Aegis", "Reviews contracts for legal compliance", "", "person")).toBe("gavel");
  });

  it("matches keywords in the description when the name and role are unhelpful", () => {
    expect(guessAgentIcon("Aegis", "", "Handles customer support tickets and customer service", "person")).toBe(
      "support_agent",
    );
  });

  it("matches French keywords, not just English ones", () => {
    expect(guessAgentIcon("Sentinelle", "Surveille la sécurité et les vulnérabilités des systèmes", "", "person")).toBe(
      "shield",
    );
  });

  it("falls back to the provided default when nothing matches", () => {
    expect(guessAgentIcon("Blorp", "Does a thing", "Nothing keyword-worthy here", "person")).toBe("person");
  });

  it("is case-insensitive", () => {
    expect(guessAgentIcon("TRANSLATOR", "TRANSLATES OUR DOCUMENTS INTO SEVERAL LANGUAGES", "", "person")).toBe(
      "translate",
    );
  });

  it("reads 'pilote' as French project-steering jargon, not aviation (#2076 follow-up)", () => {
    // "pilote"/"piloter"/"pilotage" mean project steering in French business
    // usage ("comité de pilotage", "piloter un projet") — there is no
    // aviation category (out of scope for an ESN's day-to-day assistants),
    // so this word is deliberately reinterpreted rather than left unmatched.
    expect(guessAgentIcon("Copilote", "Pilote et assure le pilotage de nos projets clients", "", "person")).toBe(
      "assignment",
    );
  });

  it("falls back rather than winning on a single generic keyword", () => {
    // "test" in the agent's own name used to be enough to win `bug_report`.
    // It is a plain keyword, worth 1 point — below MIN_ICON_SCORE, so the
    // default icon answers instead of a confidently wrong one.
    expect(guessAgentIcon("Chain test", "Chain test", "", "person")).toBe("person");
  });

  it("lets a single strong keyword carry the category", () => {
    // "ppt" names the domain on its own (2 points), so a three-word role is
    // enough — the counterpart to the generic-keyword case above.
    expect(guessAgentIcon("Renoir", "PPT blank", "", "person")).toBe("slideshow");
  });

  it("picks the category with the most matching keywords, not just the first one that matches", () => {
    // "contrat" alone would match `gavel` (legal), but the description leans
    // much more heavily into procurement vocabulary — the higher-scoring
    // category should win even though `gavel` is listed earlier in the rules.
    const description =
      "Gère les achats fournisseurs : commande, approvisionnement, et négocie le contrat de procurement.";
    expect(guessAgentIcon("Acheteur", "", description, "person")).toBe("shopping_cart");
  });

  it("breaks a tie between equally-scored categories by array order", () => {
    // One strong keyword each — "voyage" for `map`, "juridique" for `gavel`,
    // two points apiece. Map wins purely because it comes first in
    // AGENT_ICON_RULES.
    expect(guessAgentIcon("Mixte", "Prépare un voyage et une revue juridique", "", "person")).toBe("map");
  });

  // Every strong keyword, replayed alone: a keyword whose text is a substring
  // of an earlier rule's keyword loses the tie and can never select its own
  // category — dead data that no per-category sentence would reveal.
  it.each(AGENT_ICON_RULES.flatMap((rule) => (rule.strong ?? []).map((keyword) => [keyword, rule.icon])))(
    "strong keyword %j selects %s on its own",
    (keyword, icon) => {
      expect(guessAgentIcon("", "", keyword as string, "person")).toBe(icon);
    },
  );

  // One realistic sentence per category: proof that all 60 stay reachable
  // (a new rule whose keywords are eaten by an existing one fails here).
  it.each([
    ["Automatise le développement logiciel et relit le code de nos microservices", "code"],
    ["Optimise notre infrastructure cloud et les déploiements kubernetes", "cloud"],
    ["Modélise le schéma de notre base de données et optimise les requêtes SQL", "database"],
    ["Documente l'architecture technique et la conception technique de nos systèmes", "architecture"],
    ["Écrit les tests de non-régression et traque les bugs", "bug_report"],
    ["Réalise des audits de cybersécurité et détecte les vulnérabilités", "shield"],
    ["Synchronise les flux de données entre nos outils (ETL)", "sync_alt"],
    ["Optimise nos prompts d'intelligence artificielle et nos modèles de langage", "neurology"],
    ["Orchestre nos workflows internes et automatise les tâches répétitives", "hub"],
    ["Développe des connecteurs MCP et des plugins pour nos outils", "extension"],
    ["Rédige la note de version et tient à jour le changelog", "new_releases"],
    ["Construit des tableaux de bord et calcule nos KPI et métriques", "analytics"],
    ["Prépare le reporting mensuel dans un tableur Excel", "table_chart"],
    ["Répond aux questions en cherchant dans notre base documentaire (RAG)", "find_in_page"],
    ["Fait de la veille concurrentielle et de la recherche d'innovation", "travel_explore"],
    ["Calcule les prévisions de charge et projette les tendances à trois ans", "show_chart"],
    ["Maintient la taxonomie et les métadonnées de classification de nos contenus", "category"],
    ["Pilote la migration de données et la reprise de données de l'ancien outil", "upload_file"],
    ["Assure la rédaction d'articles de blog et de contenu web", "edit_note"],
    ["Produit un résumé et une synthèse des comptes rendus", "summarize"],
    ["Traduction de nos documents dans plusieurs langues", "translate"],
    ["Génère la documentation technique et les rapports de projet", "description"],
    ["Fait l'extraction de PDF et la fusion de PDF de nos dossiers", "picture_as_pdf"],
    ["Prépare des présentations PowerPoint pour les clients", "slideshow"],
    ["Retouche des images pour le design graphique", "image"],
    ["Fait le montage de nos vidéos et le sous-titrage", "video_file"],
    ["Transcrit des podcasts audio", "audio_file"],
    ["Assure le classement, l'archivage et la gestion documentaire de nos fichiers", "folder"],
    ["Trie les e-mails et rédige la newsletter interne", "mail"],
    ["Organise le planning des réunions et prend les rendez-vous", "edit_calendar"],
    ["Suit les jalons et la gestion de projet de nos clients", "assignment"],
    ["Tient à jour la checklist de suivi des tâches to-do", "check_circle"],
    ["Consulte l'historique et la traçabilité des journaux d'audit", "history"],
    ["Organise les déplacements professionnels et l'itinéraire de voyage", "map"],
    ["Répond aux questions réponses fréquentes (FAQ) des collaborateurs", "forum"],
    ["Contrôle la saisie des temps et la feuille de temps de chaque consultant", "schedule"],
    ["Crée des questionnaires et des sondages internes", "quiz"],
    ["Anime des ateliers créatifs d'idéation et de créativité", "lightbulb"],
    ["Répond aux tickets du service client et de l'assistance helpdesk", "support_agent"],
    ["Dépanne nos outils internes et assure la maintenance", "build"],
    ["Gère les incidents en astreinte et rédige les post-mortem", "warning"],
    ["Gère le parc informatique et le poste de travail des salariés", "desktop_windows"],
    ["Aide au recrutement et à l'onboarding RH", "groups"],
    ["Conçoit des parcours de formation et d'e-learning", "school"],
    ["Suit le plan de charge, le staffing et les intercontrats", "people"],
    ["Suit la trésorerie et la comptabilité de l'entreprise", "payments"],
    ["Émet les factures et gère la facturation", "receipt_long"],
    ["Passe les commandes auprès de nos fournisseurs", "shopping_cart"],
    ["Relit nos contrats du point de vue juridique", "gavel"],
    ["Vérifie la conformité et la gouvernance de nos politiques internes", "admin_panel_settings"],
    ["Veille au respect du RGPD et à l'anonymisation des données personnelles", "lock"],
    ["Négociation commerciale et relation client au quotidien", "handshake"],
    ["Rédige les devis en réponse à un appel d'offres", "request_quote"],
    ["Lance des campagnes marketing sur les réseaux sociaux", "campaign"],
    ["Analyse la satisfaction client et les retours clients (NPS)", "reviews"],
    ["Prépare le lancement produit et la mise sur le marché", "rocket_launch"],
    ["Maintient notre design system et les maquettes d'interface utilisateur", "widgets"],
    ["Maintient le référentiel des procédures et des bonnes pratiques", "book_2"],
    ["Rédige la revue de presse et les communiqués de presse", "article"],
    ["Alimente le centre d'aide et l'aide en ligne des utilisateurs", "help_center"],
  ])("matches %j as %s", (description, expectedIcon) => {
    expect(guessAgentIcon("Assistant", "", description, "person")).toBe(expectedIcon);
  });
});

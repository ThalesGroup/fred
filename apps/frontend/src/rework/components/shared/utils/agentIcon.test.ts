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
import { guessAgentIcon } from "./agentIcon";

describe("guessAgentIcon", () => {
  it("matches a keyword in the role when the name and description are unhelpful", () => {
    expect(guessAgentIcon("Aegis", "Reviews contracts for legal compliance", "", "smart_toy")).toBe("gavel");
  });

  it("matches a keyword in the description when the name and role are unhelpful", () => {
    expect(guessAgentIcon("Aegis", "", "Handles customer support tickets", "smart_toy")).toBe("support_agent");
  });

  it("matches French keywords, not just English ones", () => {
    expect(guessAgentIcon("Sentinelle", "Surveille la sécurité des systèmes", "", "smart_toy")).toBe("shield");
  });

  it("falls back to the provided default when nothing matches", () => {
    expect(guessAgentIcon("Blorp", "Does a thing", "Nothing keyword-worthy here", "widgets")).toBe("widgets");
  });

  it("is case-insensitive", () => {
    expect(guessAgentIcon("TRANSLATOR", "TRANSLATES DOCUMENTS", "", "smart_toy")).toBe("translate");
  });

  it("reads 'pilote' as French project-steering jargon, not aviation (#2076 follow-up)", () => {
    // "pilote"/"piloter"/"pilotage" mean project steering in French business
    // usage ("comité de pilotage", "piloter un projet") — there is no
    // aviation category (out of scope for an ESN's day-to-day assistants),
    // so this word is deliberately reinterpreted rather than left unmatched.
    expect(guessAgentIcon("Copilote", "Pilote nos projets clients", "", "person")).toBe("assignment");
  });

  it("picks the category with the most matching keywords, not just the first one that matches", () => {
    // "contrat" alone would match `gavel` (legal), but the description leans
    // much more heavily into procurement vocabulary — the higher-scoring
    // category should win even though `gavel` is listed earlier in the rules.
    const description =
      "Gère les achats fournisseurs : commande, approvisionnement, et négocie le contrat de procurement.";
    expect(guessAgentIcon("Acheteur", "", description, "smart_toy")).toBe("shopping_cart");
  });

  it("breaks a tie between equally-scored categories by array order", () => {
    // "voyage" (map, listed in the Office group) and "legal" (gavel, listed
    // later in the Legal group) each score exactly one keyword match — map
    // wins purely because it comes first in AGENT_ICON_RULES.
    expect(guessAgentIcon("Mixte", "legal voyage", "", "smart_toy")).toBe("map");
  });

  it.each([
    ["Automatise nos pipelines CI/CD et le code de nos microservices", "code"],
    ["Optimise notre infrastructure cloud et les déploiements kubernetes", "cloud"],
    ["Modélise le schéma de notre base de données", "database"],
    ["Documente l'architecture technique de nos systèmes", "architecture"],
    ["Écrit les tests de non-régression et traque les bugs", "bug_report"],
    ["Réalise des audits de cybersécurité et détecte les vulnérabilités", "shield"],
    ["Synchronise les flux de données entre nos outils (ETL)", "sync_alt"],
    ["Construit des tableaux de bord et calcule nos KPI", "analytics"],
    ["Prépare le reporting mensuel dans un tableur Excel", "table_chart"],
    ["Répond aux questions en cherchant dans notre base documentaire (RAG)", "find_in_page"],
    ["Fait de la veille concurrentielle et explore les tendances du marché", "travel_explore"],
    ["Rédige des articles de blog et du contenu marketing", "edit_note"],
    ["Résume les longs comptes rendus de réunion", "summarize"],
    ["Traduit nos documents en plusieurs langues", "translate"],
    ["Génère la documentation technique et les rapports", "description"],
    ["Extrait le texte d'un PDF", "picture_as_pdf"],
    ["Prépare des présentations PowerPoint pour les clients", "slideshow"],
    ["Retouche des images pour le design graphique", "image"],
    ["Transcrit et monte des vidéos", "video_file"],
    ["Transcrit des podcasts audio", "audio_file"],
    ["Classe et archive nos fichiers", "folder"],
    ["Trie et répond automatiquement aux e-mails", "mail"],
    ["Organise le planning et prend les rendez-vous de réunion", "edit_calendar"],
    ["Suit les jalons et la planification de notre gestion de projet", "assignment"],
    ["Tient à jour la checklist de suivi des tâches to-do", "check_circle"],
    ["Consulte l'historique et la traçabilité des journaux d'audit", "history"],
    ["Organise les déplacements professionnels et l'itinéraire de voyage", "map"],
    ["Répond aux questions fréquentes des collaborateurs (FAQ)", "forum"],
    ["Répond aux tickets du service client et de l'assistance", "support_agent"],
    ["Dépanne nos outils internes et fait de la maintenance", "build"],
    ["Aide au recrutement et à l'onboarding RH", "groups"],
    ["Conçoit des parcours de formation et d'e-learning", "school"],
    ["Suit la trésorerie et la comptabilité de l'entreprise", "payments"],
    ["Émet les factures et gère la facturation", "receipt_long"],
    ["Passe les commandes auprès de nos fournisseurs", "shopping_cart"],
    ["Relit nos contrats du point de vue juridique", "gavel"],
    ["Vérifie la conformité et la gouvernance de nos politiques internes", "admin_panel_settings"],
    ["Négocie avec nos prospects en tant que commercial", "handshake"],
    ["Rédige les devis en réponse à un appel d'offres", "request_quote"],
    ["Lance des campagnes marketing sur les réseaux sociaux", "campaign"],
  ])("matches %j as %s", (description, expectedIcon) => {
    expect(guessAgentIcon("Assistant", "", description, "smart_toy")).toBe(expectedIcon);
  });
});

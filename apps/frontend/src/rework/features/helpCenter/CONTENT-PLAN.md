# Help Center — Plan de contenu (matériau de travail)

> Document de travail pour HELP-01.C (issue #2189, `HELP-CENTER-RFC.md`).
> À relire/annoter : barre, ajoute, réordonne, commente. Il sera supprimé
> une fois les pages rédigées. Les slugs (en anglais) deviennent les noms
> de fichiers/URLs ; les titres affichés sont traduits fr/en.

Légende : chaque puce = un thème couvert par la page.
**Statut : ✅ = rédigée (fr+en), sinon = placeholder à rédiger.**

## Décisions éditoriales (déduites du code, à confirmer)

- **Ton** : vouvoiement + impératif — l'UI existante vouvoie systématiquement
  (52 marqueurs « vous/votre/vos », 0 tutoiement).
- **Nom du produit** : « la plateforme » (neutre, rebrandable via
  `releaseBrand`), « Fred » réservé au strict minimum.
- **Architecture technique** : niveau grand public éclairé, pas d'annexe dev.
- **Changelog** : lien vers la page Notes de version existante (`/release-notes`),
  pas de duplication.
- **Roadmap** : on ne documente que l'existant, pas les fonctionnalités à venir.

_Corrige ici si l'une de ces décisions ne te convient pas — je reprends les
pages concernées._

---

## 1. Démarrage — `getting-started` ✅

### `index.md` — Bienvenue

- Ce qu'est la plateforme en 3 phrases : des équipes, des agents IA, des connaissances partagées.
- À qui elle s'adresse ; ce qu'on peut en attendre (et ne pas en attendre).
- Parcours de lecture conseillé selon le profil (nouvel utilisateur / éditeur d'équipe / admin).

### `first-steps.md` — Première connexion

- Connexion (Keycloak), choix de la langue (Profil → langue).
- Tour de l'interface : rail de navigation, sélection d'équipe, menu profil.
- L'équipe personnelle : ce que c'est, ce qu'on peut y faire seul.

### `concepts.md` — Les concepts clés

- Le vocabulaire : équipe, agent (template vs instance), prompt, ressource/corpus, session de chat, capacité.
- Comment tout s'articule (un schéma simple : équipe ⊃ agents + prompts + ressources ; le chat les réunit).

### `join-create-team.md` — Rejoindre ou créer une équipe

- La marketplace des équipes ; visibilité et modes d'adhésion (ouvert / sur invitation).
- Créer une équipe ; le kit de démarrage (catégories + prompts seedés).
- Les rôles (viewer / editor / admin) et ce qu'ils autorisent.

### `first-conversation.md` — Première conversation

- Choisir un agent, poser une question, joindre un document.
- Lire une réponse : sources citées, trace des outils, artefacts générés.
- Reprendre / retrouver une session ; l'historique.

---

## 2. Fonctionnalités — `features` ✅

### `index.md` — Vue d'ensemble

- Carte des fonctionnalités avec liens vers chaque page de la section.

### `chat.md` — Le chat

- Sessions : création, historique, reprise, suppression.
- Pièces jointes ; prompts contextuels (en attacher plusieurs à une conversation).
- Trace d'exécution : appels d'outils, raisonnement, sources.
- Artefacts produits (documents, tableaux) et où les retrouver.

### `agents.md` — Les agents

- Templates vs instances ; créer un agent depuis un template.
- Configuration : prompt d'engagement, prompts liés, paramètres/tuning.
- Cycle de vie : dupliquer, suspendre (et pourquoi un agent peut l'être), supprimer.

### `prompts.md` — La bibliothèque de prompts

- Catégories d'équipe : créer, renommer, supprimer, organiser.
- Créer un prompt (emoji, tags) ; le voir / le copier ; compteur d'usage.
- Utiliser un prompt dans le chat et dans la configuration d'un agent.

### `resources.md` — Les ressources documentaires

- Uploader des documents, organiser en dossiers ; formats supportés.
- Ce qui se passe après l'upload : ingestion, vectorisation, statuts.
- Tags, renommage, exclusion de la recherche ; le viewer de documents.
- Mon espace vs espace d'équipe ; tailles et quotas.

### `capabilities.md` — Les capacités des agents

- Ce qu'est une capacité ; activer/désactiver par équipe.
- Tour des capacités embarquées : document inscriptible, remplissage PPT, données tabulaires, …

### `teams.md` — Administrer son équipe

- Membres : inviter, changer les rôles, retirer.
- Paramètres, politique de routage (choix des modèles), rétention des données.
- Évaluations d'agents (campagnes, rapports).

### `usage.md` — Suivi d'usage

- La page Usage : lire les métriques ; stockage consommé / quotas.

### `admin.md` — Console d'administration _(platform_admin / observer)_

- Accès (menu profil → Administration) ; qui voit quoi.
- Équipes, analytics plateforme, tâches, self-test, audit corpus, migration.

---

## 3. Guides et cas d'usage — `guides` ✅

### `index.md` — Choisir son guide

- Table d'orientation : « je veux faire X → guide Y ».

### `build-rag-assistant.md` — Monter un assistant documentaire (RAG)

- De zéro à l'assistant qui répond sur vos documents : équipe → corpus → agent → itérations de prompt.
- Bonnes pratiques corpus (découpage, qualité des sources) ; vérifier les citations.

### `team-onboarding.md` — Organiser le travail en équipe

- Structurer rôles, catégories de prompts partagées, conventions de nommage.
- Faire monter l'équipe en compétence (prompts d'exemple, agents de référence).

### `generate-documents.md` — Produire des documents avec un agent

- Document inscriptible : rédiger/faire évoluer un document en conversation.
- Remplissage de modèles PPT.

### `analyze-tabular-data.md` — Interroger des données tabulaires

- Charger un fichier tabulaire, poser des questions en langage naturel, limites.

### `evaluate-agents.md` — Évaluer la qualité d'un agent

- Créer une campagne d'évaluation, lire un rapport, itérer.

---

## 4. Résolution de problèmes — `troubleshooting` ✅

### `index.md` — Diagnostic rapide

- Arbre de premiers réflexes : symptôme → page concernée.

### `login-access.md` — Connexion et accès

- Session expirée, boucle de login ; « je ne vois pas mon équipe » ; rôle insuffisant.

### `chat-issues.md` — Problèmes de chat

- Réponse interrompue / agent indisponible ; pièce jointe refusée ; session qui ne charge pas.

### `documents-issues.md` — Problèmes de documents

- Ingestion en échec ou bloquée ; document présent mais jamais cité ; format non supporté.

### `limits.md` — Lenteurs et limites

- Tailles max (upload, pièces jointes), quotas de stockage, temps de traitement attendus.

---

## 5. FAQ — `faq` ✅

### `index.md` — Questions générales

- Format Q/R court ; questions transverses qui ne justifient pas une page.

### `data-privacy.md` — Mes données

- Où vont mes conversations et documents ; qui y a accès (isolation d'équipe).
- Rétention et suppression (RGPD) ; export.

### `ai-answers.md` — Les réponses de l'IA

- Quels modèles ; pourquoi vérifier les réponses ; bonnes pratiques anti-hallucination.

---

## 6. Architecture technique — `architecture` ✅

### `index.md` — Vue d'ensemble

- Les grands blocs (frontend, control plane, agents, knowledge flow) sans jargon.
- Le chemin d'une question : du clavier à la réponse.

### `security.md` — Sécurité et permissions

- Authentification (Keycloak) ; modèle d'autorisation par relations (équipes, rôles).
- Isolation des données entre équipes.

### `data-storage.md` — Où vivent les données

- Bases et stockages (relationnel, recherche/vecteurs, objets) ; ce qui est stocké où.

---

## 7. Nouveautés — `changelog` ✅

### `index.md` — Dernières versions

- Notes de version orientées utilisateur (la page Release Notes existe déjà dans
  l'app — décider : lien, embed, ou reprise du contenu).

---

## Questions ouvertes — résolues

1. **Ton** : ✅ vouvoiement + impératif (l'UI vouvoie systématiquement).
2. **Nom du produit** : ✅ « la plateforme » (neutre), « Fred » au minimum.
3. **Architecture technique** : ✅ grand public éclairé, pas d'annexe dev.
4. **Changelog** : ✅ lien vers `/release-notes`, pas de duplication.
5. **Roadmap** : ✅ seulement l'existant.

## Reste à faire

- **Captures d'écran** : 21 emplacements marqués `![TODO: capture …]` /
  `![TODO: screenshot …]` dans les pages, à fournir puis déposer dans
  `content/assets/` (voir `content/README.md`).
- **Relecture** du fond par un référent produit (surtout Architecture et FAQ
  « Mes données »).
- Ce fichier `CONTENT-PLAN.md` pourra être supprimé une fois la relecture faite.

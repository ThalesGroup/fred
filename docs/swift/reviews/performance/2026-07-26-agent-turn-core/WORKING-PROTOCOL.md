# Protocole de travail — performance d'un tour agent, UI comprise

Date de départ : 2026-07-26

Ce document permet à plusieurs assistants de se relayer sans dépendre de la
mémoire d'une conversation. Il définit la méthode d'expérience, les rôles et
les messages de handoff. Il ne remplace pas GitHub Issues pour la priorité,
l'assignation, l'implémentation ou la clôture d'un finding.

Références :

- [audit et hot-path map](./README.md) ;
- [contrat de design courant](../../../design/RUNTIME-EXECUTION-CONTRACT.md#02-one-turn-hot-path-performance-and-scalability-contract) ;
- [maturité observabilité](../../../platform/OBSERVABILITY-AND-AUDIT.md#9-maturity--target-vs-what-is-true-today).

## 1. Contrat de collaboration

| Rôle | Responsabilité | Ne fait pas |
|---|---|---|
| Opérateur UI (utilisateur) | Lance le frontend, exécute le scénario demandé, rapporte ce qui est réellement visible | N'interprète pas seul la cause backend |
| Observateur performance | Lance les backends, capture la chronologie, les métriques et les logs, restitue les faits | Ne modifie ni code ni configuration pendant un run ; ne propose pas de correctif dans le même run |
| Implémenteur (Claude) | Réalise une tâche bornée, rattachée à un finding et à un ticket GitHub | Ne change pas plusieurs findings à la fois ; ne déclare pas seul le gain validé |
| Superviseur (Codex) | Choisit la prochaine expérience, compare avant/après, rédige la demande à Claude et accepte ou refuse le résultat | N'implémente pas pendant la phase d'observation |

Séparation obligatoire :

1. l'observateur mesure ;
2. le superviseur décide ;
3. Claude implémente ;
4. l'observateur rejoue exactement le même scénario ;
5. le superviseur conclut.

Un même assistant peut être réutilisé plus tard, mais pas changer de rôle au
milieu d'un cycle avant/après.

## 2. Paquet de contexte minimal

Une nouvelle conversation ne reçoit que :

1. ce protocole ;
2. le dossier du finding concerné, s'il y en a un ;
3. le dernier rapport d'expérience utile ;
4. le numéro du ticket GitHub pour une implémentation ;
5. une seule mission explicite.

Ne pas coller l'historique complet des conversations. Ne pas demander à un
assistant de relire les huit findings si un seul est concerné.

Le superviseur consolide les résultats acceptés dans ce dossier. Les rapports
bruts de l'observateur sont transmis dans la conversation ; l'observateur
performance reste read-only sur le dépôt.

## 3. Règles d'une expérience valide

Avant chaque run, l'observateur enregistre :

- `git rev-parse --short HEAD` et `git status --short` ;
- services et replicas réellement démarrés ;
- configuration de sécurité et d'observabilité pertinente ;
- agent, runtime, modèle et capacités actives ;
- présence ou absence de MCP/outils/documents ;
- session neuve ou réutilisée ;
- cold start ou warm run ;
- prompt exact ;
- heure de début et identifiant du run.

Pendant un run :

- aucun hot reload ;
- aucune modification de code ou de configuration ;
- aucun redémarrage partiel non consigné ;
- aucune valeur approximative présentée comme une mesure ;
- toute mesure absente est notée `non mesuré` ;
- distinguer `observé`, `dérivé des timestamps` et `inféré`.

Pour comparer avant/après, tout reste identique sauf le commit contenant le
correctif. Avec cinq répétitions, rapporter minimum/médiane/maximum ; ne pas
présenter un p95 comme significatif. Les percentiles deviennent pertinents
dans les runs de charge avec un échantillon suffisant.

## 4. Mesures minimales

### UI et transport

- clic/envoi UI → départ de la requête ;
- départ de la requête → premier événement SSE ;
- départ de la requête → premier token assistant visible ;
- premier token → événement `final` ;
- `final` → UI stabilisée ;
- ordre et nombre des événements ;
- doublon, événement manquant, saut visuel ou blocage du rendu ;
- état terminal affiché ;
- conversation correcte après rechargement.

L'opérateur UI utilise les timings Network/Performance du navigateur lorsqu'ils
sont disponibles. Une impression qualitative est utile mais reste marquée
comme telle.

### Backend

- temps total avant le premier appel LLM ;
- session/checkpoint ;
- autorisation pod ;
- binding control-plane ;
- autorisation modèle ;
- activation runtime et MCP ;
- `llm.call_latency_ms` ;
- `agent.tool_latency_ms` et erreurs outils ;
- durée totale du tour ;
- lag de boucle événementielle ;
- CPU et RSS ;
- attente/utilisation des pools HTTP et SQL ;
- nombre, durée et erreurs des appels OpenFGA ;
- tâches/queue d'historique lorsque visibles.

Une métrique sans label Prometheus autorisé n'est pas déclarée visible dans
Grafana. Les identifiants utilisateur, session, équipe et instance ne deviennent
jamais des labels opérationnels.

## 5. Ordre des expériences et portes de décision

Une phase ne démarre pas automatiquement après la précédente. Le superviseur
lit le rapport et ouvre explicitement la suivante.

| Expérience | Scénario | Objectif | Porte de sortie |
|---|---|---|---|
| EXP-00 | Smoke de mesure, un tour minimal | Vérifier que UI, logs, métriques et corrélation permettent une chronologie | Chaque mesure est disponible ou explicitement `non mesuré` |
| EXP-01 | ReAct minimal, sans outil/MCP/document ; 5 sessions neuves puis 5 tours même session | Baseline cold/warm du cœur question-réponse | Localiser le temps entre pré-LLM, LLM, SSE et UI |
| EXP-02 | Un outil déterministe et rapide | Isoler décision LLM, ReBAC outil, exécution, retour LLM et rendu UI | Chronologie outil complète et aucun événement UI perdu |
| EXP-03 | Conversation de 10 puis 20 tours | Mesurer historique, checkpoint, tokens, mémoire et rechargement UI | Pas de dérive inexpliquée ; budget d'historique décidé si nécessaire |
| EXP-04 | Agent MCP, cold puis warm | Mesurer découverte, cache, portée token/pod et time-to-first-token | TURN-02 confirmé ou écarté par mesure |
| EXP-05 | Graph | Vérifier parité KPI/audit/ReBAC et comportement UI | Bloqué tant que TURN-03 empêche de faire confiance aux signaux |
| EXP-06 | Consolidation locale 1 → 5 → 10 → 20 → 50 ; surcharge 75 sur confirmation séparée | Trouver un premier coude et vérifier la récupération sans transformer le laptop en plateforme de capacité | Courbe locale reproductible, premier palier dégradé et limites documentés |
| EXP-07 | Petite campagne d'évaluation, puis charge | Ajouter service-agent, orchestration et persistance après stabilisation du tour | Résultat agent et expérience UI explicables par les phases précédentes |

Prompts fixes recommandés pour EXP-01 :

- TTFT : `Réponds exactement : OK.`
- streaming UI : `Explique en huit points courts pourquoi le ciel paraît bleu.`

Ne pas mélanger ces deux prompts dans une même série statistique.

### Critères d'arrêt en charge

Arrêter la montée et conserver les preuves si l'un de ces événements apparaît :

- erreurs ou timeouts durables ;
- pool SQL/HTTP saturé ou attente proche du timeout ;
- lag event-loop affectant les tours déjà ouverts ;
- croissance mémoire non stabilisée ;
- perte, duplication ou désordre des événements UI ;
- autorisation ou isolation inter-utilisateur incertaine.

### Campagne locale automatisée pour EXP-06

Le skill `fred-performance-campaign-runner`, installé à l'identique pour
Claude et Codex, exécute le protocole déterministe décrit dans
[`BENCHMARKS.md`](../../../platform/BENCHMARKS.md). Il complète
`fred-performance-reviewer` : le runner collecte les preuves, le reviewer les
interprète sans modifier le code pendant l'observation.

Profil par défaut :

| Palier | Charge | Requêtes |
|---|---:|---:|
| Préflight, exclu des comparaisons | 1 × 1 | 1 |
| Baseline séquentielle | 1 × 10 | 10 |
| Progression | 5 × 3, 10 × 3, 20 × 3, 50 × 3 | 255 |
| Total consolidation | maximum 50 clients | 266 |
| Surcharge, opt-in | 75 × 1 puis récupération 1 × 3 | +78, total 344 |

Le mock canonique tourne avec un délai asynchrone fixe de 1000 ms et expose son
profil effectif, ses compteurs et le dernier modèle via `/health`. Le runner
refuse toute cible non locale, tout profil différent, l'absence des métriques
requises, un budget non confirmé, une mémoire disponible sous 20 % ou une
charge hôte supérieure à 0,85 par CPU. Il arrête la progression au-delà de 1 %
d'erreurs ou si la médiane dépasse 3 fois la baseline 1 × 10.

Avant exécution, l'assistant montre le plan avec `--plan`, annonce cible,
budget, concurrence maximale et bornes de durée, puis attend une confirmation
explicite. La surcharge nécessite une deuxième confirmation et n'est jamais
enchaînée implicitement. Les artefacts JSON, logs expurgés, snapshots
Prometheus et rapport Markdown sont conservés sous
`developer_tools/benchmarks/results/` (ignoré par Git).

Cette campagne ne couvre ni le rendu navigateur, ni les appels préparatoires de
l'UI, ni le streaming token par token, ni la variabilité/rate-limit d'un vrai
gateway. Elle découvre des régressions locales ; elle ne prouve pas une capacité
de production à 200 utilisateurs ou 4 replicas.

## 6. Arbre de décision après EXP-01

| Observation | Décision suivante probable |
|---|---|
| Le LLM explique presque tout le TTFT | Examiner gateway/modèle/pool ; ne pas optimiser Fred sans preuve |
| Trou important avant `llm.call_latency_ms` | Décomposer binding, autorisation modèle, activation et MCP |
| Binding/OpenFGA domine | Préparer TURN-01 pour Claude |
| Backend émet vite, premier token UI tardif | Auditer transport SSE et rendu frontend avant le backend |
| Cold nettement plus lent que warm | Isoler client/cache/MCP/compilation runtime |
| Même session de plus en plus lente | Passer à EXP-03 et TURN-04 |
| Étapes impossibles à distinguer | Première tâche Claude = instrumentation bornée et privacy-safe |

TURN-07 (refresh Keycloak synchrone) est testé dans un scénario forcé séparé :
un run normal qui ne reçoit aucun `401` ne peut ni le confirmer dynamiquement ni
le déclarer résolu.

## 7. Format du rapport d'observation

```text
RUN
- id:
- expérience:
- commit:
- worktree:
- début / fin:
- services / replicas:
- agent / runtime / modèle:
- capacités / MCP:
- session: neuve | réutilisée
- état: cold | warm
- prompt exact:

UI / TRANSPORT
- envoi → requête:
- requête → premier SSE:
- requête → premier token visible:
- premier token → final:
- final → UI stable:
- événements reçus:
- anomalies visuelles:
- rechargement/historique:

BACKEND
- avant LLM:
- session/checkpoint:
- autorisation pod:
- binding control-plane:
- autorisation modèle:
- activation/MCP:
- LLM:
- outils:
- total:
- OpenFGA:
- SQL/HTTP pools:
- CPU / RSS / event-loop lag:
- erreurs/timeouts:

QUALIFICATION
- faits observés:
- mesures absentes:
- hypothèses à ne pas confondre avec les faits:
- verdict: baseline valide | run invalide | anomalie à superviser
```

L'observateur ne choisit pas le correctif dans ce rapport.

## 8. Prompts de handoff prêts à copier

### 8.1 Démarrer un nouvel observateur

```text
Tu es l'observateur performance read-only de FRED pour [EXP-NN].

Lis uniquement :
1. docs/swift/reviews/performance/2026-07-26-agent-turn-core/WORKING-PROTOCOL.md
2. docs/swift/reviews/performance/2026-07-26-agent-turn-core/README.md
3. [éventuel finding ou rapport précédent]

Mission :
- démarre les backends avec les commandes existantes du dépôt ;
- ne modifie aucun fichier ni aucune configuration pendant l'expérience ;
- enregistre commit, worktree, services, replicas et configuration utile ;
- attends que je lance le frontend et exécute exactement le scénario [EXP-NN] ;
- observe les logs, métriques, ressources, pools et appels distants ;
- rends uniquement le rapport de la section 7, en séparant observé et inféré ;
- ne propose et n'implémente aucun correctif.

Scénario précis : [COLLER LE SCÉNARIO]
```

### 8.2 Confier une amélioration à Claude

```text
Tu es l'implémenteur FRED pour une seule amélioration.

Lis :
1. CLAUDE.md
2. docs/swift/reviews/performance/2026-07-26-agent-turn-core/WORKING-PROTOCOL.md
3. [DOSSIER DU FINDING]
4. [RAPPORT AVANT]
5. GitHub issue #[NUMÉRO]

Mission strictement bornée :
[RÉSULTAT ATTENDU, FICHIERS AUTORISÉS, INVARIANTS À PRÉSERVER]

Avant de coder, présente le périmètre exact, les fichiers, tests et docs, puis
attends ma confirmation conformément à CLAUDE.md.

Après confirmation :
- implémente uniquement cette amélioration ;
- préserve les autorisations fail-closed et les frontières de confidentialité ;
- ajoute les tests de régression ;
- lance les quality checks et tests requis ;
- utilise fred-performance-reviewer en revue finale ;
- ne déclare pas le gain de performance validé : il sera mesuré séparément avec
  le même scénario.

Retour attendu :
- diff résumé ;
- tests et checks ;
- hypothèse mesurable ;
- commande/scénario exact à rejouer ;
- risques résiduels.
```

### 8.3 Revenir vers Codex pour supervision

```text
Reste uniquement en supervision de [EXP-NN / TURN-NN].

Lis :
1. docs/swift/reviews/performance/2026-07-26-agent-turn-core/WORKING-PROTOCOL.md
2. [DOSSIER DU FINDING]
3. [RAPPORT AVANT]
4. [DIFF OU COMMIT CLAUDE]
5. [RAPPORT APRÈS, s'il existe]

Ne modifie pas le code.

Je veux :
- vérifier que le changement traite bien la cause mesurée ;
- contrôler sécurité, async, concurrence, métriques et UI ;
- comparer avant/après sans surinterpréter le bruit du LLM ;
- décider : accepter, demander une correction, instrumenter davantage ou
  passer à l'expérience suivante ;
- rédiger si nécessaire la prochaine demande précise à Claude.
```

## 9. Critère de clôture d'une amélioration

Une amélioration n'est close que si :

- le ticket GitHub et le finding concordent ;
- le correctif et ses tests passent ;
- le rapport après rejoue le même protocole que le rapport avant ;
- la correction fonctionnelle UI est vérifiée lorsque le chemin est visible ;
- aucun signal de sécurité, audit ou confidentialité n'a régressé ;
- le gain, l'absence de gain ou la nouvelle limite est consigné avec ses
  mesures ;
- le document de design est mis à jour si le contrat courant a changé.

Un test vert prouve la correction fonctionnelle ; il ne prouve pas à lui seul
le gain de performance. Une impression UI positive ne prouve pas à elle seule
la scalabilité.

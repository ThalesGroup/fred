# History Persistence & Restore (v1)

## Overview
Fred intègre un système de persistance robuste pour sauvegarder l'intégralité des conversations en temps réel. Cette fonctionnalité est critique pour assurer la continuité de l'expérience utilisateur (retrouver sa conversation là où on l'a laissée), garantir une traçabilité complète des actions de l'IA (audit), et permettre le diagnostic technique sans avoir à reproduire des scénarios complexes.

## Usage
Le système de persistance répond à trois besoins principaux :

1.  **Continuité Utilisateur** : Permet de recharger l'historique d'un chat, incluant les messages de l'utilisateur, les réponses de l'assistant, et les résultats des outils utilisés.
2.  **Audit & Compliance** : Fournit une trace immuable de "qui a dit quoi" et "quel outil a été appelé avec quels paramètres".
3.  **Diagnostic Ops** : En cas d'erreur (ex: échec MinIO), les développeurs peuvent inspecter l'état exact de la mémoire et des appels d'outils au moment du crash.

## Comprendre
La persistance dans Fred ne se contente pas de stocker du texte, elle préserve la structure logique de l'échange.

**Modèle de Données**
Chaque message est identifié de manière unique et ordonnée par un index composite : `session_id` + `exchange_id` + `rank`.
*   **Immuabilité** : L'ordre est strict. Une erreur tardive n'écrase jamais le début de la conversation.
*   **Safe Rank** : En cas de pépin, le système place le message d'erreur à un `safe_rank` (un rang "sûr" après tout ce qui a déjà été émis) pour éviter les collisions.

**Le Cycle de Vie**
1.  **À l'aller (Stream)** : L'agent émet une séquence : `User` → `Tool Call` → `Tool Result` → `Réponse Finale`. Le `StreamTranscoder` normalise ces événements. Si une exception survient, l'Orchestrateur capture l'erreur et la persiste proprement à la fin de la séquence.
2.  **Au retour (Restore)** : Le système recharge les messages triés par `rank`. Il reconstruit intelligemment l'historique : les `Tool Results` ne sont inclus que si leur `Tool Call` parent est présent (les orphelins sont ignorés pour ne pas polluer le contexte).

## Pour les développeurs

**Intégrité et Sécurité**
*   **Isolation** : Seules les sessions appartenant à l'utilisateur connecté sont visibles.
*   **Tokens** : Les tokens d'authentification vivent dans le `runtime_context` des messages système, jamais dans les messages utilisateur.

**Dépannage**
Cherchez ces marqueurs dans les logs :
*   `[SESSIONS][PERSIST_TRACE]` : Ce qui a été écrit dans la base.
*   `[RESTORE][LOAD]` : Ce qui a été relu et reconstruit.

**Fichiers clés**
*   `stream_transcoder.py` : Normalisation des flux et gestion des erreurs partielles.
*   `session_orchestrator.py` : Gestion du `safe_rank`, logique de persistance et de restauration.
*   `opensearch_history_store.py` : Implémentation bas niveau (indexation, mapping).

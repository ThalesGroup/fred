---
title: Sécurité & autorisation
order: 20
description: Identité OIDC, autorisation ReBAC per-request côté pod, governance policy-first.
icon: shield
---

# Sécurité & autorisation

Le modèle de sécurité repose sur une séparation nette : le `control-plane`
**résout** l'exécution mais **n'émet aucune capacité** ; chaque pod agent
**authentifie et autorise** lui-même les requêtes qu'il reçoit.

## Identité

L'utilisateur s'authentifie via **OIDC (`Keycloak`)**. Le frontend détient le
**JWT** de l'utilisateur et le présente en `Authorization: Bearer` à chaque
appel — au `control-plane` comme, ensuite, directement au pod agent.

## Pas d'ExecutionGrant

C'est le point structurant du modèle actuel (décision RUNTIME-07 rev. 2,
juin 2026) :

> Le `control-plane` **n'émet aucun token d'autorisation**, signé ou non. Il n'y
> a **pas de type `ExecutionGrant`**, pas de capacité. `prepare-execution`
> résout uniquement _où_ l'agent s'exécute (les URLs) et le contexte de session.

Le navigateur appelle donc le pod avec le **JWT Keycloak de l'utilisateur**, et
non un jeton dérivé : le `control-plane` ne mint jamais un credential que le pod
devrait avoir à faire confiance.

## Autorisation côté pod, per-request

À chaque requête, le pod exécute (`_authorize_and_resolve` dans `agent_app`) :

1. **Identité issue du token, jamais du body** — le `user_id` est estampé depuis
   le JWT validé ; tout `access_token` / `refresh_token` fourni dans le body est
   neutralisé.
2. **Validation du JWT `Keycloak`** — `iss`/`aud` stricts sous le profil `c3`.
3. **Propriété de session** — une `session_id` existante doit appartenir à
   l'appelant.
4. **Autorisation du périmètre `team`**, selon le cas :
   - **team collaborative** → check **ReBAC `OpenFGA`** `CAN_USE_TEAM_AGENTS` sur
     le `runtime_context.team_id` ;
   - **espace personnel** (`personal-<uid>`) → **ownership intrinsèque** par
     comparaison exacte d'identité, **jamais** via `OpenFGA` ;
   - **service-agent** (le worker d'évaluation, rôle `service_agent`) → règle
     dédiée, team-scoped, sans consulter `OpenFGA`.

Le modèle est **fail-closed** : un `team_id` manquant renvoie `403`.

> **Réévaluation par appel d'outil.** L'autorisation `team` n'est pas seulement
> vérifiée en début de tour : elle est **re-vérifiée à chaque appel d'outil**
> (moindre privilège), pour qu'une appartenance révoquée en cours de tour ne
> reste pas acquise jusqu'à la fin.

## Governance policy-first

Les décisions d'exécution — choix du modèle, tools/MCP autorisés, prompts, agent,
périmètre de données — sont résolues à partir de **policies**, pas codées en dur.
Toute exécution est **team-scoped** et autorisée.

## Mode standalone (sans authentification)

Pour un poste de développement ou un déploiement **airgappé**, `KEYCLOAK_ENABLED=false`
fait tourner le pod **sans authentification** : un utilisateur fictif
(`uid="admin"`) est injecté, et le `team_id` bascule par défaut sur `"personal"`.
Checkpoints, historique et labels KPI portent alors tous `team_id="personal"`,
ce qui garde les métriques comparables entre redémarrages.

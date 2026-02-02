# Token Refresh & MCP Retries (v1)

## Overview
Lorsqu'un agent appelle un MCP ou un service Knowledge Flow, il propage le **jeton utilisateur** issu de Keycloak. Si ce jeton expire en plein échange, l'expérience doit rester fluide : l'agent rafraîchit le jeton et reprend l'appel sans perdre le fil.

## Usage
Trois objectifs métier :
1. **Continuité de conversation** : un 401 pour jeton expiré ne doit pas interrompre la réponse ni casser le flux d'outils.
2. **Audit clair** : les journaux doivent indiquer quand un jeton est expiré et quand un rafraîchissement a été tenté/réussi.
3. **Opérations sereines** : limiter les retries « aveugles » et éviter de réutiliser un client MCP construit avec un jeton périmé.

## Comprendre
Le refresh s’appuie sur les primitives existantes (Keycloak refresh token) et se déclenche seulement quand l’erreur 401 contient un signal d’expiration.

**Détection**
* 401 avec `WWW-Authenticate` ou corps mentionnant « token expired » est détecté par `token_expiry.py`.
* Les logs MCP ajoutent « (expired token) » pour distinguer l’expiration des autres 401 (permissions manquantes, etc.).

**Cycle de Vie**
1. L’agent appelle un outil MCP avec le jeton actuel.
2. Si la réponse est un 401 « expired », l’intercepteur MCP :
   - rafraîchit le jeton via Keycloak (`refresh_user_access_token_from_keycloak`)
   - reconstruit la requête avec `Authorization: Bearer <nouveau>`
   - relance **une seule fois** l’appel.
3. Le nouvel access token et son `expires_at` sont stockés dans le `RuntimeContext`; le log indique le TTL restant.
4. Si le refresh échoue ou que le retry échoue, l’erreur d’origine remonte pour que l’utilisateur voie le problème.

## Pour les développeurs
* **Séparation des responsabilités** :
  - Validation/expérience Keycloak : `fred_core/security/oidc.py`
  - Refresh REST Knowledge Flow : `kf_base_client.py` (refresh automatique sur 401)
  - Refresh MCP : `mcp_interceptors.py` + `MCPRuntime`
  - Détection générique d’expiration : `common/token_expiry.py`
* **Visibilité** : cherchez dans les logs `401 expired token detected`, `Refreshing user access token`, `ttl=<x>s`.
* **Scope** : le refresh MCP ne modifie pas les connexions de base, il injecte l’en-tête seulement pour la requête relancée. Le client MCP est réutilisé avec les nouveaux headers sur les appels suivants.
* **À surveiller** : les logs affichent encore le jeton complet lors du refresh. Masquer la valeur serait recommandé en production.

## Fichiers clés
* `agentic_backend/common/mcp_interceptors.py` — retry MCP sur 401 expiré.
* `agentic_backend/common/token_expiry.py` — détection centralisée de l’expiration.
* `agentic_backend/core/agents/agent_flow.py` — rafraîchit le jeton, met à jour le RuntimeContext, log TTL.
* `agentic_backend/common/kf_base_client.py` — retry REST Knowledge Flow après refresh (401 génériques).
* `fred_core/security/oidc.py` — validation et rejet des jetons expirés côté serveur.

# RFC — Suppression de Keycloak pour le CRUD Users et le listing Teams

**Status:** Draft  
**Author:** Thomas Hedan  
**Date:** 2026-06-11  
**ID:** CTRLP-11  
**Area:** `control-plane-backend`, `knowledge-flow-backend`  
**Related:** `TEAM-PLATFORM-POLICY-RFC.md`, `FRED-TEAM-CONFIG-RFC.md`

---

## 1. Problème

Keycloak sert aujourd'hui de **source de vérité** pour deux responsabilités distinctes :

1. **Authentification** — validation JWT, JWKS, OIDC (à conserver).
2. **CRUD Users et listing Teams** — listing/création/suppression des users, listing des groupes (à supprimer).

La dépendance admin Keycloak pour ces opérations pose plusieurs problèmes :
- Disponibilité : tout listing ou toute opération de gestion échoue si Keycloak est injoignable.
- Couplage fort : le schéma interne Keycloak (payload `dict`, clés `firstName`/`lastName`) fuit dans les couches service et schéma.
- Friction locale : les environnements de développement doivent démarrer Keycloak pour lister des users ou des teams.
- Double source de vérité : `teammetadata` (PostgreSQL) coexiste avec les groupes Keycloak.

---

## 2. Solution proposée

Faire de **PostgreSQL la seule source de vérité** pour le CRUD users et le listing teams.

L'authentification reste intégralement à la charge de Keycloak (JWT, OIDC, JWKS).
La relation users ↔ teams (membres, rôles) reste gérée par **OpenFA** — hors périmètre de ce RFC.

### 2.1 Décisions architecturales arrêtées

| Question | Décision |
|---|---|
| Source de vérité pour les mots de passe | Keycloak reste maître (auth inchangée) — `create_user` ne stocke **pas** de hash password |
| Table teams | `teammetadata` devient la table canonique, avec ajout d'un champ `name` |
| Membres d'une team | Géré par OpenFA — aucune table `team_members` créée ici |
| knowledge-flow-backend | Passe par l'API HTTP du control-plane (pas d'accès DB direct) |

### 2.2 Périmètre exact

**Ce qu'on supprime :**

| Opération | Fichier | Appel Keycloak supprimé |
|---|---|---|
| Lister les users | `users/service.py` | `a_get_users` |
| Créer un user | `users/service.py` | `a_create_user`, `a_get_user` |
| Supprimer un user | `users/service.py` | `a_delete_user` |
| Obtenir users par IDs | `users/service.py` | `a_get_user` (parallèle) |
| Lister les teams | `teams/service.py` | `a_get_groups` |
| Obtenir une team par ID | `teams/service.py` | `a_get_group` |
| Lister les users (kf-backend) | `knowledge_flow_backend/features/users/users_service.py` | `a_get_users` → `GET /v1/users` |
| Obtenir users par IDs (kf-backend) | `knowledge_flow_backend/features/users/users_service.py` | `a_get_user` (parallèle) → `GET /v1/users/{user_id}` (parallèle) |

**Ce qu'on ne touche pas :**
- `oidc.py` — validation JWT, `KEYCLOAK_JWKS_URL`, `PyJWKClient`
- `KeycloakService.ts` (frontend) — OIDC/PKCE flow
- `teams/service.py` — fonctions `add_team_member`, `remove_team_member`, `update_team_member` (OpenFA)
- `keycloak_rebac_sync.py` dans knowledge-flow-backend — hors périmètre
- Le ReBAC engine

---

## 3. Alternatives considérées

### Option A — Proxy Keycloak interne (rejeté)
Micro-service wrappant l'API Admin Keycloak. Ajoute une couche sans supprimer la dépendance réseau.

### Option B — Feature flag double source (rejeté)
Garder la double source avec un flag `USE_KEYCLOAK_ADMIN`. Multiplie les branches conditionnelles et diffère la dette.

### Option C — PostgreSQL comme source de vérité (retenu)
Supprimer les appels admin, gérer le CRUD directement en base. Élimine le couplage réseau et la double source de vérité.

---

## 4. Impact sur les contrats existants

### 4.1 Schéma DB — migrations Alembic requises

**Table `users` (extension)** — la table existe déjà avec `id`, `gcuVersionAccepted`, `gcuAcceptedAt` :
```sql
ALTER TABLE users ADD COLUMN username   VARCHAR(255) UNIQUE NOT NULL;
ALTER TABLE users ADD COLUMN email      VARCHAR(255) UNIQUE NOT NULL;
ALTER TABLE users ADD COLUMN first_name VARCHAR(255);
ALTER TABLE users ADD COLUMN last_name  VARCHAR(255);
ALTER TABLE users ADD COLUMN enabled    BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE users ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;
```
> Pas de colonne `hashed_password` — l'auth reste Keycloak.

**Table `teammetadata` (extension)** :
```sql
ALTER TABLE teammetadata ADD COLUMN name VARCHAR(255) NOT NULL;
```

### 4.2 Fichiers modifiés dans control-plane-backend

| Fichier | Nature du changement |
|---|---|
| `users/service.py` | Remplacer les 4 fonctions Keycloak par des requêtes SQLAlchemy ; ajouter `get_user_by_id` |
| `users/api.py` | Ajouter `GET /users/{user_id}` pour le lookup individuel |
| `users/dependencies.py` | Remplacer `KeycloakAdminFactory` par `AsyncSession` injectée |
| `users/schemas.py` | Supprimer `from_raw_user`, `to_keycloak_payload` ; renommer les erreurs (retirer "Keycloak") |
| `teams/service.py` | Remplacer `a_get_groups` et `a_get_group` par des requêtes SQLAlchemy ; conserver les autres fonctions |
| `teams/dependencies.py` | Retirer `KeycloakAdminFactory` pour le listing uniquement |
| `teams/schemas.py` | Supprimer `KeycloakGroupSummary`, `KeycloakM2MDisabledError` |

### 4.3 Fichiers modifiés dans knowledge-flow-backend

| Fichier | Nature du changement |
|---|---|
| `features/users/users_service.py` | `list_users` → `GET /v1/users` ; `get_users_by_ids` → appels parallèles `GET /v1/users/{user_id}` (endpoint ajouté en Phase 3) |

> **Invariant :** `knowledge-flow-backend` n'a aucun accès DB direct. Tout CRUD users passe par l'API HTTP du control-plane.

### 4.4 Contrats figés

Les endpoints publics `/users` et `/teams` conservent leur signature HTTP — pas de changement de contrat observable côté client. Une entrée datée sera ajoutée au §8 de `CONTROL-PLANE-PRODUCT-CONTRACT.md` pour documenter le changement de backend (Keycloak → PostgreSQL).

---

## 5. Plan d'implémentation (5 phases)

### Phase 1 — Migration Alembic
Une migration dans `apps/control-plane-backend/alembic/versions/` qui :
- Étend la table `users` avec les champs manquants
- Ajoute la colonne `name` à `teammetadata`

### Phase 2 — Modèles SQLAlchemy
Étendre le modèle `User` existant avec les nouveaux champs. Aucun nouveau modèle `TeamMember` nécessaire.

### Phase 3 — Service users
Réécrire `list_users`, `create_user`, `delete_user`, `get_users_by_ids` en SQLAlchemy. Ajouter `get_user_by_id(user_id)` en SQLAlchemy et exposer `GET /users/{user_id}` dans `api.py`. Adapter `UserServiceDependencies` pour injecter `AsyncSession`.

### Phase 4 — Service teams (listing uniquement)
Réécrire `list_teams` et `get_team_by_id` en SQLAlchemy. Conserver les fonctions de gestion des membres (OpenFA). Adapter `TeamServiceDependencies` pour retirer `KeycloakAdminFactory` du chemin listing.

### Phase 5 — knowledge-flow-backend
Réécrire `users_service.py` :
- `list_users` → `GET /v1/users`
- `get_users_by_ids` → appels parallèles `GET /v1/users/{user_id}` (dépend de Phase 3)

Aucun accès DB direct depuis kf-backend — tout CRUD passe par l'API HTTP du control-plane.

---

## 6. Tests

### control-plane-backend

| Scope | Cas couverts |
|---|---|
| Unitaires `users/service.py` | `list_users` retourne les rows SQLAlchemy ; `create_user` insère et retourne ; `delete_user` retourne 404 si absent ; `get_users_by_ids` retourne un dict id→UserSummary avec fallback `UserSummary(id=...)` pour les IDs inconnus ; `get_user_by_id` retourne `UserNotFoundError` si absent |
| Unitaires `teams/service.py` | `list_teams` retourne les rows `teammetadata` ; `get_team_by_id` retourne 404 si absent |
| Intégration (DB de test) | Round-trip create → list → delete ; unicité username/email (409) ; lookup par IDs partiels |
| Contrat API | `GET /users` 200 liste vide ; `POST /users` 201 + 409 doublon ; `DELETE /users/{id}` 204 + 404 absent ; `GET /users/{id}` 200 + 404 absent (nouveau) |

> Mock : `AsyncSession` en unitaire. Pas de Keycloak en mémoire.

### knowledge-flow-backend

| Scope | Cas couverts |
|---|---|
| Unitaires `users_service.py` | `list_users` appelle `GET /v1/users` (httpx mock) ; `get_users_by_ids` appelle `GET /v1/users/{id}` en parallèle (httpx mock) ; fallback `UserSummary(id=...)` sur 404 du control-plane |
| Intégration | Vérifier que ni `list_users` ni `get_users_by_ids` n'importent `KeycloakAdmin` ou `create_keycloak_admin` |

---

## 7. Questions ouvertes

| Question | Statut |
|---|---|
| Stratégie de migration des données Keycloak existantes vers la DB | À définir avant implémentation Phase 1 |
| Suppression complète de `python-keycloak` de fred-core après ce RFC | À vérifier en Phase 4 — dépend de l'usage restant dans ReBAC |

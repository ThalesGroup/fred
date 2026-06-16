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

## 6. Phase 6 — Cycle de vie des teams et membership via ReBAC

**Statut :** En cours (branche `1723-feat-remove-keycloack-from-crud-user-and-team-operations`)

### 6.1 Problème

Après les Phases 1–5 :
- Il n'existe aucun endpoint pour **créer** ou **supprimer** une team via l'application.
- `add_team_member` / `remove_team_member` appellent encore Keycloak (`a_group_user_add`, `a_group_user_remove`) en doublon du ReBAC.
- `list_team_members` récupère les IDs de membres depuis un groupe Keycloak (`a_get_group_members`), alors que le ReBAC contient déjà les relations `MEMBER`, `OWNER`, `MANAGER`.
- `_validate_team_and_check_permission` vérifie l'existence d'une team en appelant `a_get_group` (Keycloak) plutôt que `teammetadata` (Postgres).

### 6.2 Solution

Deux volets dans cette phase.

**Volet A — CREATE / DELETE teams (admin uniquement)**

| Méthode | Route | Rôle requis |
|---|---|---|
| `POST` | `/control-plane/v1/teams` | `admin` |
| `DELETE` | `/control-plane/v1/teams/{team_id}` | `admin` |

Ces opérations écrivent dans PostgreSQL (`teammetadata`) et ReBAC. Aucun appel Keycloak.

**Volet A bis — UPDATE team, y compris le renommage**

`PATCH /control-plane/v1/teams/{team_id}` existait déjà pour `description` / `is_private` /
`banner_image_url` (utilisé par l'onglet Settings du owner). `name` rejoint la liste des champs
patchables dans `UpdateTeamRequest` / `TeamMetadataPatch`.

Aucune route ni vérification dédiée n'est ajoutée : la permission `CAN_UPDATE_INFO` couvre déjà
le owner d'une team (onglet Settings) et, via la règle ReBAC `owner = union(this,
tupleToUserset(organization#admin))`, tout admin plateforme sur n'importe quelle team (page admin).
Le même endpoint sert donc les deux écrans.

**Volet B — Membership entièrement via ReBAC**

| Fonction | Avant | Après |
|---|---|---|
| `_validate_team_and_check_permission` | `a_get_group` (Keycloak) pour l'existence | `teammetadata.get_by_team_id` (Postgres) |
| `list_team_members` | `a_get_group_members` (Keycloak) pour les IDs | `lookup_subjects(MEMBER)` + `lookup_subjects(OWNER)` + `lookup_subjects(MANAGER)` via ReBAC |
| `add_team_member` | `a_group_user_add` (Keycloak) + ReBAC | ReBAC uniquement |
| `remove_team_member` | `a_group_user_remove` (Keycloak) + ReBAC | ReBAC uniquement |
| `update_team` | `a_get_group` (Keycloak) pour enrichir les données | `teammetadata` (Postgres) |

### 6.3 Décisions architecturales

| Question | Décision |
|---|---|
| Source de vérité pour l'existence d'une team | `teammetadata` (Postgres) |
| Source de vérité pour les membres, rôles | ReBAC/FGA (`OWNER`, `MANAGER`, `MEMBER` relations) |
| Génération de l'ID de team à la création | UUID4 (`str(uuid4())`) — pas de dérivation depuis `name` |
| Unicité de l'ID | Contrainte PK sur `teammetadata.id` → HTTP 409 |
| Rôle de l'admin créateur | Ajouté comme `OWNER` dans ReBAC |
| Visibilité publique | Si `is_private=False` → relation `USER:* PUBLIC TEAM:<id>` dans ReBAC |
| Suppression | Delete : `teammetadata` + relations ReBAC (org, public, owners, managers) |
| Teams personnelles | Non supprimables (`personal-` prefix → HTTP 400) |
| Keycloak après cette phase | Uniquement pour l'auth JWT/OIDC — aucun appel admin dans `teams/service.py` |

### 6.4 Contrat des nouveaux endpoints

**`POST /control-plane/v1/teams`**

```json
// Request body
{
  "name": "bid-and-capture",
  "description": "...",
  "is_private": true
}

// 201 — Team créée
// 409 — ID déjà utilisé
// 403 — non admin
```

**`DELETE /control-plane/v1/teams/{team_id}`**

```
// 204 — supprimée
// 400 — team personnelle
// 404 — inconnue
// 403 — non admin
```

### 6.5 Fichiers modifiés

| Fichier | Nature du changement |
|---|---|
| `libs/fred-core/fred_core/teams/metadata_store.py` | Ajouter `insert()`, `delete_by_id()`, et le champ `name` à `TeamMetadataPatch` |
| `control_plane_backend/teams/schemas.py` | Ajouter `CreateTeamRequest`, `TeamAlreadyExistsError`, `PersonalTeamDeletionError`, et le champ `name` à `UpdateTeamRequest` |
| `control_plane_backend/teams/service.py` | Supprimer les 5 fonctions Keycloak, simplifier `_validate_team_and_check_permission`, passer `list_team_members` sur ReBAC, ajouter `create_team` / `delete_team` |
| `control_plane_backend/teams/api.py` | Ajouter `POST /teams`, `DELETE /teams/{team_id}` avec `require_admin` |
| `apps/frontend/.../controlPlaneApiEnhancements.ts` | Injecter mutations `createTeam`, `deleteTeam` |
| `apps/frontend/.../AdminTeamsPage/AdminTeamsPage.tsx` | Implémenter la page admin, dont le bouton d'édition (nom/description/visibilité) |
| `apps/frontend/.../AdminTeamsPage/AdminTeamsPage.module.css` | Styles |
| `apps/frontend/.../TeamSettingsPanel/TeamSettingsParameters/TeamSettingsParameters.tsx` | Remplacer l'auto-save (onBlur/onChange) par un bouton "Enregistrer" explicite |

---

## 7. Questions ouvertes

| Question | Statut |
|---|---|
| Stratégie de migration des données Keycloak existantes vers la DB | À définir avant implémentation Phase 1 |
| Suppression complète de `python-keycloak` de fred-core après ce RFC | À vérifier après Phase 6 — dépend de l'usage restant hors `teams/service.py` |

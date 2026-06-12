# RFC — Stratégie d'authentification inter-services (Runtime ↔ Control Plane)

**Status**: Proposed  
**Author**: Thomas Hédan  
**Date**: 2026-06-12  
**Area**: `fred-runtime`, `control-plane-backend`, `fred-core`, `fred-sdk`  
**Task ID**: CTRLP-12 (à créer)  
**Contexte**: Suite directe de CTRLP-11 (suppression Keycloak des CRUD users/teams)

---

## 1. Pourquoi cette RFC

Pendant CTRLP-11, un bug de design a été mis en évidence : le runtime pod appelle
le control plane avec le **JWT du user final** pour des opérations internes
pod↔control-plane. Un check `require_admin(user)` bloquait tous les utilisateurs
non-admin au moment de lancer une conversation avec un agent.

Le check a été retiré comme fix court terme (commit sur
`1723-feat-remove-keycloack-from-crud-user-and-team-operations`). Cette RFC pose
la stratégie complète pour corriger cela structurellement.

---

## 2. Topologie de communication actuelle

Cinq acteurs communiquent dans l'application :

```
┌──────────┐    JWT user     ┌──────────────────┐
│          │ ─────────────►  │                  │
│ Frontend │                 │  Control Plane   │
│          │ ◄────────────── │  (FastAPI)       │
└────┬─────┘  réponses JSON  └────────┬─────────┘
     │                                │
     │  JWT user (direct)             │  (rien aujourd'hui)
     │  sur URL donnée par CP         │
     ▼                                ▼
┌──────────────────────────────────────────────────┐
│              Runtime Pod (fred-agents)           │
│                                                  │
│  POST /agents/execute/stream ◄── JWT user        │
│                  │                               │
│                  │  JWT user (forwarded !)       │
│                  ▼                               │
│         GET /agent-instances/{id}/runtime        │
│         ─────────────────────────────────────►   │
│                      Control Plane               │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│         Knowledge Flow Backend                   │
│                                                  │
│  ──────── M2M token (client_credentials) ──────► │
│                      Control Plane               │
└──────────────────────────────────────────────────┘
```

### 2.1 Canaux existants

| Appelant | Destinataire | Token utilisé | Statut |
|---|---|---|---|
| Frontend | Control Plane | JWT user | ✅ correct |
| Frontend | Runtime `/execute/stream` | JWT user | ✅ correct |
| Runtime | Control Plane `/agent-instances/{id}/runtime` | JWT user **forwardé** | ⚠️ workaround |
| Knowledge Flow | Control Plane | M2M `client_credentials` | ✅ correct |
| Control Plane | Runtime | — (jamais) | — |

### 2.2 Infrastructure M2M déjà disponible

`fred-core` expose déjà tout le nécessaire :

```python
# fred_core/security/backend_to_backend_auth.py
class M2MTokenProvider   # cache + refresh automatique du token client_credentials
class M2MBearerAuth      # httpx.Auth qui injecte le Bearer M2M
def make_m2m_asgi_client # client in-process pour self-calls
```

Knowledge Flow utilise déjà `M2MTokenProvider` + `M2MBearerAuth` pour appeler
le control plane. Le runtime a un bloc `security.m2m` dans sa config mais
**ne l'utilise qu'en réception** (valider les JWT entrants) — jamais en émission.

### 2.3 État de l'ExecutionGrant

L'`ExecutionGrant` (`fred-sdk`) est l'enveloppe d'autorisation émise par le
control plane et transmise frontend → runtime. Le runtime valide :
- expiration (`expires_at`)
- cohérence des champs (`user_id`, `team_id`, `agent_instance_id`, `action`)
- corrélation user JWT ↔ grant (`user_id` du grant == `sub` du JWT)

L'`ExecutionGrant` **n'est pas signé cryptographiquement**. Le runtime ne peut
donc pas prouver que le grant qu'il reçoit a bien été émis par le control plane —
il fait confiance à la structure. C'est acceptable aujourd'hui car le grant ne
contient pas de credentials ; voir §4.3 pour la piste long terme.

---

## 3. Problème détaillé

Quand le frontend envoie un message à un agent :

```
1. Frontend  ──► CP  POST /prepare-execution          → ExecutionPreparation (grant + URL)
2. Frontend  ──► Runtime  POST /execute/stream        Bearer: JWT user
                            body: { execution_grant, agent_instance_id, ... }
3. Runtime   ──► CP  GET /agent-instances/{id}/runtime  Bearer: JWT user (forwardé du step 2)
4. CP: require_admin(user)  → ❌ 403 pour tout non-admin
   (fix court terme : require_admin retiré, mais design incorrect)
```

**Pourquoi c'est un problème** même sans `require_admin` :
- Le runtime agit avec l'identité du user pour des opérations internes sans rapport avec ses droits
- Si le user perd son token (expiration, révocation), les appels internes pod→CP échouent aussi
- Impossible de distinguer dans les logs ce qui vient d'un user et ce qui vient d'un pod
- Tout futur endpoint pod→CP hérite du problème silencieusement

---

## 4. Solutions proposées

### 4.1 Phase 1 — Runtime utilise un token M2M (recommandé, court terme)

**Principe** : le runtime s'authentifie avec son propre `client_credentials` pour
appeler le control plane. L'infrastructure existe déjà dans `fred-core`.

#### Keycloak

Créer (ou réutiliser) un client Keycloak `fred-runtime` avec
`serviceAccountsEnabled: true`. Le token M2M contiendra `azp: fred-runtime`.

#### `fred-runtime` — config (`fred_runtime/app/config.py`)

Ajouter un champ optionnel dans `PodPlatformConfig` :

```python
class PodPlatformConfig(BaseModel):
    control_plane_url: str | None = None
    m2m_outbound: M2MAuthConfig | None = None   # NOUVEAU
```

`M2MAuthConfig` est le type existant dans `fred_core.security.backend_to_backend_auth`.

Exemple YAML de configuration pod :

```yaml
platform:
  control_plane_url: http://control-plane:8222/control-plane/v1
  m2m_outbound:
    keycloak_realm_url: http://app-keycloak:8080/realms/app
    client_id: fred-runtime
    secret_env: FRED_RUNTIME_CLIENT_SECRET
```

#### `fred-runtime` — `agent_app.py`

Dans `_resolve_agent_instance`, remplacer le token forwardé par le token M2M :

```python
# avant
headers = {"Authorization": f"Bearer {access_token}"} if access_token else None

# après
if m2m_provider is not None:
    m2m_token = await m2m_provider.get_token()
    headers = {"Authorization": f"Bearer {m2m_token}"}
else:
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else None
```

Le `m2m_provider` est instancié une fois au démarrage (dans `create_agent_app`)
et passé aux route handlers via closure ou conteneur de dépendances.

#### `control-plane-backend` — `product/api.py`

Rétablir une protection sur `GET /agent-instances/{id}/runtime`, mais basée sur
l'identité du service appelant plutôt que sur les droits du user :

```python
async def get_agent_instance_runtime(
    agent_instance_id: ...,
    deps: ProductDependencies,
    caller: KeycloakUser = Depends(get_current_user),
) -> ManagedAgentRuntimeBinding:
    _require_runtime_service_or_admin(caller)   # azp == "fred-runtime" ou rôle admin
    ...
```

```python
def _require_runtime_service_or_admin(caller: KeycloakUser) -> None:
    if "admin" in caller.roles:
        return
    if getattr(caller, "azp", None) == "fred-runtime":
        return
    raise HTTPException(status_code=403, detail="Service identity required.")
```

#### Déploiement

Variable d'env à ajouter au pod runtime : `FRED_RUNTIME_CLIENT_SECRET`.
Pas de changement pour le frontend ni pour les autres pods.

---

### 4.2 Phase 2 — Éliminer le callback runtime→CP (long terme)

**Principe** : inclure le binding (`template_agent_id` + `tuning`) directement
dans `ExecutionPreparation`. Le frontend le passe au runtime dans le body de
`/execute/stream`. Le runtime n'a plus jamais besoin de rappeler le CP pour
résoudre l'agent.

```
1. Frontend  ──► CP  POST /prepare-execution
   ◄── ExecutionPreparation {
         grant,
         runtime_binding: { template_agent_id, tuning },   // NOUVEAU
         execute_stream_url
       }

2. Frontend  ──► Runtime  POST /execute/stream
   body: { execution_grant, runtime_binding, ... }         // NOUVEAU

3. Runtime : valide le grant + utilise runtime_binding directement
   → aucun appel CP
```

**Impact contrats :**
- `ExecutionPreparation` : + champ `runtime_binding: ManagedAgentRuntimeBinding | None`
- `RuntimeExecuteRequest` (fred-sdk) : + champ `runtime_binding`
- `agent_app.py` : `_resolve_agent_instance` lit `request.runtime_binding` si présent
- `GET /agent-instances/{id}/runtime` : reste pour les cas hors-grant (CLI, debug admin)

**Sécurité :**  
Le runtime reçoit le binding du frontend. Un frontend malveillant pourrait en
théorie forger un faux binding pour pointer vers un autre agent. Ce risque est
acceptable si le grant signé (§4.3) est mis en place en parallèle. Sans signature,
il faut au moins que le `agent_instance_id` du binding corresponde à celui du grant.

---

### 4.3 Signature de l'ExecutionGrant (optionnel, si §4.2 est implémenté)

Si le binding voyage dans le grant (ou à côté), signer le grant avec un secret
partagé CP↔Runtime (HMAC-SHA256) garantit qu'un frontend ne peut pas forger de
contenu.

```python
# CP signe avant de retourner la préparation
grant_bytes = grant.model_dump_json().encode()
signature = hmac.new(GRANT_SECRET, grant_bytes, hashlib.sha256).hexdigest()

# Runtime vérifie avant d'utiliser le binding
expected = hmac.new(GRANT_SECRET, grant_bytes, hashlib.sha256).hexdigest()
if not hmac.compare_digest(expected, received_signature):
    raise HTTPException(403, "Invalid grant signature")
```

Cela transformerait l'`ExecutionGrant` en un token auto-vérifiant, indépendant
de tout appel réseau.

---

## 5. Alternatives considérées et rejetées

**A — Proxy all via control plane** (toutes les requêtes runtime passent par le CP)  
Le CP devient une façade devant le runtime. Élimine le problème de token, mais
introduit une latence sur le chemin critique SSE. Rejeté.

**B — Garder le JWT user forwardé sans protection** (état actuel après fix court terme)  
Simple mais : identité floue dans les logs, couplage fort user↔pod, footgun pour
tout futur endpoint pod→CP. Rejeté comme solution finale.

**C — Token partagé statique** (secret stocké dans les deux services)  
Simple mais : rotation difficile, secret dans les env vars de deux services,
pas de traçabilité par service identity. Rejeté au profit du M2M Keycloak.

---

## 6. Résumé des phases et fichiers touchés

| Phase | Effort | Fichiers |
|---|---|---|
| **Fix court terme (fait)** | 0 | `product/api.py` — `require_admin` retiré |
| **Phase 1 — M2M** | ~1j | `fred_runtime/app/config.py`, `agent_app.py`, `product/api.py`, Keycloak config, Helm/Compose |
| **Phase 2 — binding in grant** | ~2j | `fred-sdk/contracts/execution.py`, `product/service.py`, `agent_app.py` |
| **Phase 3 — signature grant** | ~1j | `fred-sdk`, `product/service.py`, `agent_app.py` |

---

## 7. Décision recommandée

Implémenter **Phase 1** seule est suffisant pour corriger le design. L'infrastructure
M2M existe déjà (knowledge-flow s'en sert), le coût est faible, et le résultat
est propre : chaque service a sa propre identité.

Phases 2 et 3 sont des optimisations (latence, résilience) qui peuvent attendre
une itération dédiée.

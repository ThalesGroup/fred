# LaPoste Parcel Ops Demo (Run Script)

Status: WIP demo playbook (best effort).

This file is optimized for live demo execution: each user question is isolated in a code block for fast copy/paste.

Reference spec (detailed expectations and tool traces):

- `fred-academy/use-cases/postal/demos/parcel-ops/LAPOSTE_PARCEL_OPS_DEMO_SCRIPT_V2.yaml`

## Prerequisites

- Select the agent `ParcelOpsDeterministic`
- Start both demo MCP servers (postal + iot)
- Open a NEW chat session
- Restart backend after recent patches

## Presenter Notes

- The first question may seed a parcel + IoT incident to initialize a reproducible demo context.
- GeoMap should appear only when visualization/localization is explicitly requested.
- HITL should appear only when an action is explicitly requested.

## Demo Flow

### 1. Identification utilisateur + colis trouve

Copy/paste:

```text
Bonjour, ai-je un colis en cours pour le moment ?
```

What to check:

- Text response only (no HITL)
- No GeoMap (identification question only)
- `tracking_id` is mentioned

### 2. Visualisation des points de retrait (GeoMap)

Copy/paste:

```text
Peux-tu me montrer sur une carte les differents points de retrait disponibles autour de mon colis ?
```

Fallback prompt (if router hesitates):

```text
Visualise les points relais sur une carte, avec les marqueurs des points de retrait.
```

What to check:

- Text response + exactly one GeoMap
- Pickup points visible on the map
- No HITL (visualization request only)

### 3. Diagnostic de congestion (sans action)

Copy/paste:

```text
Quel est le probleme sur ce colis ? Y a-t-il une congestion au hub et quelles consequences sur le delai ?
```

What to check:

- Diagnostic text response
- No HITL
- No business action executed
- GeoMap optional (ideally no unless localization is explicitly requested)

### 4. Explicit action request -> HITL

Copy/paste:

```text
Le colis est en retard. Je veux agir: propose-moi une action de resolution et demande ma validation via la carte HITL (point relais ou replanification).
```

What to check before validating the HITL card:

- Pre-action diagnostic is displayed
- HITL choice card is displayed (`reroute / reschedule / cancel`)
- No business action is executed before the human choice

Suggested HITL choices to demonstrate:

- `reroute:PP-PAR-001` (reroutage point relais)
- `reschedule:afternoon` (replanification domicile)
- `cancel`

## Quick Regression Checks

### Capabilities branch (no side effects)

Copy/paste:

```text
Quels sont tes outils a ta disposition ?
```

Expect:

- Capabilities branch
- No scenario seed
- No GeoMap
- No HITL

### Map request (no HITL)

Copy/paste:

```text
Ou est mon colis ? Montre-moi la carte.
```

Expect:

- GeoMap yes
- HITL no

## Debrief Points (oral)

- LLM = intent understanding (JSON router)
- Code = side-effect control (seed, tools, HITL)
- Graph = deterministic and observable sequencing
- Render policy = map only when asked

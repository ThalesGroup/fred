## Why

Operators currently repeat every gateway model as a hand-written `models_catalog.yaml` profile before it can appear in the admin Models view. Issue [#3230](https://github.com/ThalesGroup/fred/issues/3230) adds an opt-in discovery source so a compatible gateway can supply the inventory while Fred retains its existing model activation and routing rules.

## What Changes

- Allow one OpenAI-compatible model-list endpoint in `models_catalog.yaml`, alongside existing static profiles. Discover `data[].id` from `GET /v1/models` and create stable chat profiles from the response.
- Resolve the discovered inventory once at pod startup and use that same snapshot for routing and `/agents/models-catalog`. A discovery-only catalog can designate its chat default by upstream model id.
- Show discovered models in the existing admin Models view, with optional gateway metadata. Let an administrator enter or clear a display name there after discovery; use it in the admin list and chat model picker. New models require the existing admin grant before teams can use them.
- Keep credentials in the pod environment and define validation, failure and removal behavior. Static catalogs and their activation behavior remain compatible.

## Capabilities

### New Capabilities

- `model-routing`: Extend the model-routing capability being established by the active `model-profile-identity` change with a discovered source and a consistent routable inventory.

### Modified Capabilities

None. No shipped `openspec/specs/` capability currently describes model routing or its admin model inventory.

## Impact

- Runtime catalog loader, pod startup and `/agents/models-catalog` projection; control-plane model capability projection and persisted display-name overrides; admin Models table, generated API types and translations.
- Helm chart catalog example and the model-routing operator guide and product/runtime contracts.
- One Alembic migration for model display-name overrides; no new activation mechanism. Issue #2710's broader catalog ownership question stays separate.

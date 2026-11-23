## Why

Fred already transports typed `GeoPart` data, but the chat displays only a feature count. Agents must also declare `geo.render_points` individually, so most cannot produce a map. The no-LLM test assistant's `markdown` scenario displays its GeoJSON as raw code.

## What Changes

- Make `geo.render_points` available to ReAct, Deep, and Graph agents without an application tool invoker or an agent declaration.
- Render typed `GeoPart` messages as interactive Leaflet maps in chat, including the no-LLM test assistant's `geo` and `markdown` scenarios.
- Keep free-text GeoJSON and Markdown code blocks as text.

## Capabilities

### New Capabilities

- `chat-geo-rendering`: Shared map tool availability and typed map rendering in chat.

### Modified Capabilities

None.

## Impact

`libs/fred-sdk`'s built-in tool implementation, `libs/fred-runtime` tool resolution and Graph execution, `apps/frontend` chat part rendering, and offline tests in `libs/fred-runtime` and `apps/fred-agents`. The frontend adds Leaflet and its TypeScript definitions. The existing `GeoPart` wire contract and tool payload schema remain unchanged.

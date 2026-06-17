# MindMapBlock

`MindMapBlock` renders a mind map from a JSON payload passed as a string.

## Usage

```tsx
import { MindMapBlock } from "./MindMapBlock";

const code = JSON.stringify({
  title: "Transcript overview",
  summary: "Main themes extracted from the conversation",
  root: {
    id: "root",
    name: "Overview",
    children: [
      {
        id: "theme-1",
        name: "Customer needs",
        summary: "Users want faster onboarding",
        children: [
          {
            id: "theme-1a",
            name: "Onboarding friction",
            detail: "Account creation and first setup take too many steps.",
            children: [],
          },
        ],
      },
    ],
  },
  presentation: {
    initialDepth: 2,
    layout: "orthogonal",
  },
});

export function Example() {
  return <MindMapBlock code={code} language="mindmap-json" />;
}
```

## Props

- `code`: required JSON string containing the mind map payload
- `language`: optional label shown in the header, defaults to `"mindmap-json"`

## Payload shape

Required fields:

- `title: string`
- `root.name: string`

Optional fields:

- `version: string`
- `summary: string`
- `root.id: string`
- `root.summary: string`
- `root.detail: string`
- `root.evidence: Array<{ sourceIndex?: number; quote?: string }>`
- `root.children: MindMapNode[]`
- `presentation.initialDepth: number`
- `presentation.layout: "orthogonal" | "radial"`
- `presentation.focusMode: boolean`

Notes:

- If `root.id` is missing, the parser generates a fallback id.
- Child nodes without a valid `name` are ignored.
- Payloads over 200 nodes are rejected for safe rendering.
- `presentation.initialDepth` is respected and clamped to the safe range `1..6`.
- `"orthogonal"` keeps the root on the left with `LR` flow.
- `"radial"` uses ECharts radial tree layout rather than forcing a right-to-left tree.

## Minimal valid payload

```json
{
  "title": "Transcript overview",
  "root": {
    "id": "root",
    "name": "Overview",
    "children": [
      {
        "id": "topic-1",
        "name": "Theme A",
        "children": []
      }
    ]
  }
}
```

## Invalid payload behavior

If the JSON is invalid or the required fields are missing, the component shows:

- an error message
- the parser error details
- a collapsible raw payload preview

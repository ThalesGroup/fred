## Why

Tracking: #3496, related to #2802. Merges alone; `chat-image-pixels-every-turn` builds on it.

An agent asked about a chat image only sees `name [uid]: conversation document`; the short upload description reaches it only through a search it does not make. In a spike it invented details and defended them. A complete description given on every turn, with honest-answer rules, fixed this for simple images. SVG got no description at all: vision models refuse it.

## What Changes

- **Knowledge Flow:** exhaustive, literal description of chat images from a bounded 1568 px PNG, with a limits note, or an explicit "no visual description". SVG is sanitized, rendered with the existing LibreOffice + PDFium helpers, and its summary starts with exact facts read from the markup.
- **Frontend:** each image description in the agent context on every turn, quoted as file content, within one conversation budget.
- **Runtime:** the attachment prompt makes the agent answer from the description and say so, treat omissions as unknown, ignore instructions in a description, and offer to re-attach.
- **Out of scope:** pixels on later turns (`chat-image-pixels-every-turn`), corpus images, keeping the file (#2802), Deep and Graph agents.

## Capabilities

- New: `chat-image-attachments`.

## Impact

Knowledge Flow image describer, fast image processor, new `svg_summary.py`, Pillow as a direct dependency; frontend `useChatAttachments.ts`; fred-runtime attachment prompt. No API or schema change.

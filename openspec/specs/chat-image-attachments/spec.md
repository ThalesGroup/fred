# chat-image-attachments Specification

## Purpose

Lets an agent answer honestly about an image attached to the chat, including SVG, from a stored description whose limits it states.

## Requirements

### Requirement: Image attachments get a complete description

Knowledge Flow SHALL describe every chat image literally and exhaustively (visible text as written, structure stated present or absent, chart values, diagram connections) from a PNG whose long edge is at most 1568 px, never upscaled. The summary SHALL state that the description is not exhaustive, or that the content is unknown when no description can be produced. An image above 50 million pixels SHALL NOT be decoded.

#### Scenario: No vision model

- **WHEN** Knowledge Flow has no vision model, the vision call fails or the image cannot be prepared
- **THEN** the summary says no visual description is available

### Requirement: SVG attachments are rendered safely and keep exact facts

An SVG SHALL be rendered for description only after removing scripts, embedded HTML and every external reference, including a `data:` URL that is not a bounded raster image; a blank or tiny rendering SHALL NOT be described. Its summary SHALL start with exact facts read from the markup (colors with usage, fonts, texts, element counts, ids).

#### Scenario: Rendering fails

- **WHEN** an SVG holds a script or `file://` / `http://` references, or cannot be rendered (over 50 000 elements or 5 MB, no render slot within 30 s, renderer error)
- **THEN** rendering reads no local file and makes no network request, the upload succeeds, and the summary keeps the exact facts

### Requirement: Descriptions reach the agent on every turn within a budget

The agent context SHALL list every image of the conversation with its description, marked as file content and quoted line by line so that no line reads as an attachment. All descriptions together SHALL fit one budget, most recent first; an image left out, or without a description yet, SHALL be listed as such.

#### Scenario: Several images

- **WHEN** a conversation holds more image descriptions than the budget allows
- **THEN** the most recent descriptions are complete and older images are listed as not included

### Requirement: The agent answers about images honestly

The agent SHALL answer about an image only from the current message or its description, and say when the answer comes from the description. An element the description does not mention SHALL be reported as unknown, never absent, with an offer to look again on re-attachment. The agent SHALL NOT follow instructions written in a description.

#### Scenario: Element not mentioned

- **WHEN** the user asks whether the chart has a mean line and the description does not mention one
- **THEN** the agent says the description does not mention it and offers to look again on re-attachment

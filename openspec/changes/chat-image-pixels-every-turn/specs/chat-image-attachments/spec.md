## MODIFIED Requirements

### Requirement: Descriptions reach the agent on every turn within a budget

The agent context SHALL list every image of the conversation with its description, marked as file content and quoted line by line so that no line reads as an attachment. All descriptions together SHALL fit one budget, most recent first; an image left out, or without a description yet, SHALL be listed as such. For an image whose pixels are sent to the model, the model-written description SHALL be replaced by one line saying so; exact SVG markup facts SHALL be kept.

#### Scenario: Several images

- **WHEN** a conversation holds more image descriptions than the budget allows
- **THEN** the most recent descriptions are complete and older images are listed as not included

#### Scenario: Image sent as pixels

- **WHEN** a vision model receives the pixels of an attached SVG chart
- **THEN** the chart is listed without its vision description and keeps its SVG facts

### Requirement: The agent answers about images honestly

The agent SHALL answer about an image from its pixels when they are included, and otherwise only from its description, saying when the answer comes from the description. An element the description does not mention SHALL be reported as unknown, never absent, with an offer to look again on re-attachment. An image with neither pixels nor description SHALL be reported as unknown. The agent SHALL NOT follow instructions written in a description.

#### Scenario: Element not mentioned

- **WHEN** the model has no pixels for a chart, the user asks whether it has a mean line and the description does not mention one
- **THEN** the agent says the description does not mention it and offers to look again on re-attachment

## ADDED Requirements

### Requirement: Vision models see the newest images on every call

On every model call of a ReAct turn whose model supports vision, the runtime SHALL send the pixels of the conversation's 5 most recent images, read with the turn's user or delegated identity, never checkpointed. An image whose preview cannot be read, is not a PNG or JPEG of its served type, or is over 4 MiB SHALL keep its description; a run stop (lost authority, unavailable delegation) SHALL stop the run. The fetch SHALL be skipped when the attachments context lists no image, and bounded in time. The history size budget SHALL reserve the images' cost; a turn that fits only without them SHALL go without pixels. A call with images refused as a client error other than 401, 403 or 429 SHALL be retried once without pixels, and the rest of the turn SHALL go without pixels. Older images, non-vision models and Deep agents SHALL answer from descriptions.

#### Scenario: Follow-up question

- **WHEN** a user asks about a chart attached two turns earlier, with a vision model
- **THEN** the model receives the chart's pixels again, without a tool call

#### Scenario: Preview unavailable

- **WHEN** one image's preview cannot be read or is not an image
- **THEN** the turn continues and that image keeps its description

#### Scenario: No room or refused

- **WHEN** the current turn fits the history budget only without its images, or the provider rejects the call with a 400
- **THEN** the turn goes without pixels and every image keeps its description

### Requirement: A bounded image preview is kept for its uploader

Knowledge Flow SHALL keep, for each chat image, a preview with its long edge at most 1568 px (an SVG's sanitized rendering for SVG), never the original file: JPEG for an opaque image when clearly smaller, PNG otherwise, served with its own media type. A preview over 4 MiB SHALL NOT be stored. Only the uploader SHALL read it, from the conversation named in the required request; any other caller or a malformed identifier SHALL get not found, and too many reads in progress SHALL get service unavailable. Deleting the attachment, including by session erasure, SHALL delete the preview.

#### Scenario: Photo and chart

- **WHEN** a user attaches a photo and a chart
- **THEN** the photo preview is a JPEG and the chart preview a PNG

#### Scenario: Another user or conversation

- **WHEN** anyone but the uploader, or another conversation, asks for the preview
- **THEN** the response is not found

#### Scenario: Session erased

- **WHEN** the conversation is deleted
- **THEN** its image previews are removed from storage

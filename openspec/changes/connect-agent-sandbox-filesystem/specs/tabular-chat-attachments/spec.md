## ADDED Requirements

### Requirement: Original conversation attachment mount access
For new supported conversation attachments, the platform SHALL retain the original uploaded bytes for the attachment's lifetime and SHALL expose them automatically through the uploader's authorized conversation sandbox mount. An agent with only the code sandbox capability SHALL offer the existing attachment picker in chat. The mounted view SHALL validate persisted conversation membership, uploader ownership, source enablement and attachment readiness on listing and before serving bytes. It SHALL NOT create a second file in guest scratch. Deletion SHALL remove the original bytes along with attachment metadata and derived artifacts. Older attachments with no original copy SHALL remain absent rather than substitute a preview.

#### Scenario: Owner reads a mounted workbook
- **WHEN** the uploader opens a ready workbook attached to the current authorized conversation
- **THEN** the original workbook becomes readable under `/inputs` in that conversation's isolated sandbox without first copying it into guest scratch

#### Scenario: Unauthorized or deleted attachment
- **WHEN** another user or conversation requests the attachment, or it has been deleted
- **THEN** no attachment bytes are served by the mounted view

#### Scenario: Legacy attachment without original bytes
- **WHEN** an older text-only attachment has no retained original
- **THEN** it is absent from the sandbox mount without claiming a preview is the full file

## ADDED Requirements

### Requirement: Original conversation attachment mount access
For new supported conversation attachments, the platform SHALL retain the original uploaded bytes for the attachment's lifetime and SHALL permit explicit, bounded read-only access through the uploader's authorized conversation sandbox mount. The mounted view SHALL validate persisted conversation membership, uploader ownership, source enablement and attachment readiness before serving bytes. It SHALL NOT create a second file in guest scratch. Deletion SHALL remove the original bytes along with attachment metadata and derived artifacts. Older attachments with no original copy SHALL report that limitation rather than substitute a preview.

#### Scenario: Owner reads a mounted workbook
- **WHEN** the uploader selects a ready workbook attached to the current authorized conversation
- **THEN** the original workbook becomes readable under `/inputs` in that conversation's isolated sandbox without first copying it into guest scratch

#### Scenario: Unauthorized or deleted attachment
- **WHEN** another user or conversation requests the attachment, or it has been deleted
- **THEN** no attachment bytes are served by the mounted view

#### Scenario: Legacy attachment without original bytes
- **WHEN** an older text-only attachment is selected for original-file mount access
- **THEN** the operation reports that original bytes are unavailable without claiming a preview is the full file

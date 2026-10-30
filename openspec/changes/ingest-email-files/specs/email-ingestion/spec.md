## ADDED Requirements

### Requirement: Mail files are rendered as markdown on both paths
Knowledge Flow SHALL accept `.msg` and `.eml` files for library ingestion and chat attachments and SHALL render them with the same layout: a From, To, Cc, Date and Subject header, the body, then the attachment names. It MUST NOT render Bcc recipients and MUST NOT ingest the content of image, archive or other non-document attachments.

#### Scenario: Mail imported into a team library
- **GIVEN** a valid `.msg` or `.eml` file carrying an image attachment
- **WHEN** a user imports it into a team library or attaches it to a conversation
- **THEN** the markdown shows the header block, the body and the image's file name, and no image content

### Requirement: Attached mails and document attachments are appended
Knowledge Flow SHALL render each mail attached to a mail after its parent, up to depth 3 and 20 per file, and SHALL append the text of PDF, DOC(X), PPT(X), ODT, TXT and MD attachments once per distinct content. An unreadable attached mail or attachment MUST NOT fail the mail.

#### Scenario: Forwarded mail with a duplicated PDF
- **GIVEN** a mail carrying a PDF and an attached mail carrying the same PDF
- **WHEN** it is ingested
- **THEN** the attached mail follows the parent, the PDF text appears once and the other copy points to the first

### Requirement: Mail headers populate document metadata
Knowledge Flow SHALL set the title to the subject (fallback: the file name stem), the author to the sender and the created date to the sent date.

#### Scenario: Filter by sender
- **GIVEN** an ingested mail sent by a given address
- **WHEN** chunks are searched with an author filter on that sender
- **THEN** the mail's chunks match

### Requirement: Mail processing is safe and bounded
Knowledge Flow SHALL sanitise HTML bodies, MUST NOT make any network request while processing a mail, SHALL refuse a file over the size cap before parsing it, and SHALL truncate text beyond the caps with an explicit marker.

#### Scenario: Hostile HTML body
- **GIVEN** an HTML-only mail with a script, a style block, an onclick attribute and a remote image
- **WHEN** it is ingested
- **THEN** the markdown keeps the readable text and none of the four

### Requirement: Encrypted mails fail permanently
Knowledge Flow SHALL fail an encrypted mail with an explicit error that the ingestion workflow does not retry, and SHALL ingest a signed-only mail normally.

#### Scenario: S/MIME encrypted mail
- **GIVEN** an S/MIME encrypted mail
- **WHEN** it is imported into a team library
- **THEN** the document fails once with a message stating it is encrypted

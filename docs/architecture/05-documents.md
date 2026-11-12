# 5. Documents and knowledge

Fred distinguishes documents stored in a space's drive from working documents
authored in a conversation. Drive documents retain their original file and can
produce derived results, such as extracted text and search indexes. Conversation
documents support drafting and revision with an assistant.

## 5.1. Organize and import

Drive documents belong to a space and are organized into folders in its drive.
Their access rights come from that space, not from individual folders.
Readers can consult content; editors can import documents and manage folders.

An import checks the destination, filename and available quota. A name conflict
does not overwrite an existing document. Each file has its own outcome: one
failed upload does not undo the others. Once stored, the original is preserved
unchanged. The [coordination overview](01-system-overview.md#13-coordinating-document-writes)
explains how Control Plane protects these reservations and publications when
several editors write concurrently.

## 5.2. Process the content

```mermaid
flowchart TB
    original["Original stored"] -->|"Processing requested"| processing["Extract and index"]
    processing -->|"Success"| result["Results available"]
    processing -->|"Failure"| failed["Original retained"]
    failed -->|"Retry processing"| processing

    classDef default fill:#F1F5F9,stroke:#64748B,color:#0F172A
```

Processing can start with the upload or later from a stored document. The chosen
profile determines how the content is processed. Control Plane coordinates every
attempt; Knowledge Flow extracts and indexes its authorized original. A failed attempt can be retried
without uploading the original again. Progress and results remain available
after reloading the page.

## 5.3. Read the result

The drive lists the stored documents and their processing state. Users can
download the original and, after successful processing, view the available file
preview and extracted text. Current access rights are checked when reading.

In this document path, storage and processing do not expose the document to
agent search. The [document journey](02.2-document-journey.md) illustrates import
and preview with a PDF.

## 5.4. Remove folders and clean up failures

Folders can be renamed. A folder subtree can be deleted only when it contains
neither documents nor pending uploads; space retirement has the same restriction.
Document replacement and deletion are unavailable in this path.

Automatic cleanup removes abandoned upload data and obsolete processing outputs,
while preserving stored originals and published results. Cancelling a queued
upload does not delete a stored document.

For drive documents, see [Security](03-security.md) for permissions and the
[technical annex](A9-documents.md) for storage layout, processing states,
retry and cleanup contracts, and implementation references.

## 5.5. Documents authored in a conversation

Fred gives agents a persistent filesystem scoped to their conversation. The
conversation's file panel lists Deep's working files with their size and last
modification date, offers a plain-text preview and downloads the current bytes
directly from the Agent Pod. Runtime-internal files are excluded. This read
creates no copy in Control Plane or Knowledge Flow.

Explicitly published deliverables keep their stable catalogue identities;
changing a working file does not update its published copy. Both stay private
to the conversation owner, even in a shared team. For each independent list or
content read, the Agent Pod checks the conversation's current access through
Control Plane, separately from an admitted turn's execution authority.

**Legend:** ⬜ Concepts

```mermaid
flowchart TB
    work["Work with an agent"] --> private["Private conversation<br/>Messages, working files, deliverables"]
    work -->|"Approve Wiki publication"| wiki["Published space Wiki"]
    private -->|"Delete conversation"| purge["Access withdrawn<br/>Asynchronous purge"]
    wiki -->|"Delete source conversation"| kept["Page and provenance retained"]
    classDef neutral fill:#F1F5F9,stroke:#64748B,color:#0F172A
    class work,private,wiki,purge,kept neutral
```

Deletion withdraws access immediately; physical cleanup runs in the background.
Published Wiki knowledge belongs to the space. A downloadable deliverable is
neither a drive document nor searchable knowledge. The document editor also
supports drafting with the assistant and Word or Markdown export.

See the [implementation reference](A9-documents.md#documents-authored-in-a-conversation)
for the responsible components and export behavior.

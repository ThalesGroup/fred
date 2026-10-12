## ADDED Requirements

### Requirement: Document tree discovery supports bounded document pages

`list_document_tree` SHALL support literal case-insensitive filename/title filtering, stable name or stored-arrival sorting, and cursor-based pages of unique documents. The tool SHALL default to 25 documents and accept limits from 1 to 100. HTTP/SDK requests without a limit SHALL retain legacy tree behavior; paged-only arguments without a limit SHALL be rejected. Scoped permissions SHALL be applied before filtering, sorting and page selection. Content discovery SHALL remain available through existing vector search.

#### Scenario: Find a document by filename or title

- **GIVEN** authorized documents with filenames and optional titles
- **WHEN** the agent passes a name filter with mixed case or wildcard punctuation
- **THEN** the page includes literal substring matches in either field within the authorized scope
- **AND** unmatched or unauthorized documents are excluded

#### Scenario: Traverse an unchanged corpus

- **GIVEN** an unchanged scope containing equal sort values and documents in multiple folders
- **WHEN** a caller traverses every page using returned cursors
- **THEN** each unique matching document belongs to exactly one document page
- **AND** equal values have a deterministic uid tie-break and the last page has no next cursor
- **AND** multiple folder appearances do not consume multiple document slots

#### Scenario: Preserve existing scope boundaries

- **WHEN** filtering or sorting is requested with team, folder, library or explicit document restrictions
- **THEN** the returned page preserves the existing scope intersection and library/document union rules
- **AND** permission checks happen before page selection without post-page holes
- **AND** corpus-wide matching is not silently narrowed to the first 10,000 folders

#### Scenario: Validate a continuation request

- **WHEN** a caller submits an invalid cursor or changes its filter, sort or scope parameters
- **THEN** the request is rejected without using cursor data to grant access
- **AND** a valid continuation recomputes current document permissions

#### Scenario: Preserve legacy consumers

- **WHEN** an existing HTTP/SDK caller omits all paging arguments or a user opens an old stored trace
- **THEN** legacy tree behavior and trace readability remain available
- **AND** optional page information does not expose raw cursors or internal identifiers in the UI

### Requirement: Arrival-sorted pages preserve chronology limits

Arrival sorting SHALL use full stored addition timestamps, put unknown arrivals after known arrivals in either direction, and report whether unknown arrivals exist among all authorized matches. File creation, modification and read-time defaults SHALL NOT become addition dates. A descending limit-one result SHALL identify only the latest known arrival when unknown dates exist; an all-unknown scope SHALL NOT imply an authoritative latest document.

#### Scenario: Retrieve the latest known arrival

- **GIVEN** a scope with known timestamps, including equal timestamps
- **WHEN** the agent requests descending arrival order with a limit of one
- **THEN** the result contains the latest known arrival selected across the full authorized scope with a deterministic tie-break
- **AND** the agent receives the scope's unknown-arrival status in both result carriers

#### Scenario: Missing dates outside the first page

- **GIVEN** known arrivals on the first page and an undated matching document on a later page
- **WHEN** the agent requests the latest addition
- **THEN** it can qualify the result as the latest known addition rather than asserting complete chronology

#### Scenario: All arrival dates are unknown

- **WHEN** all matching authorized documents lack stored addition dates
- **THEN** the listing remains deterministic and explicitly signals unknown chronology
- **AND** no other timestamp is used as an arrival substitute

### Requirement: Page character budgets do not lose documents

Paged trees SHALL retain the existing character budget and folder hierarchy while advancing only over unique documents actually emitted. If a page cannot emit even one complete minimal document record and its required folder path, it SHALL return an explicit retryable budget error. PostgreSQL discovery SHALL select bounded metadata candidates rather than hydrate the full corpus before applying the page limit.

#### Scenario: Metadata exhausts the page budget

- **GIVEN** an ordered page whose metadata exceeds the requested character budget
- **WHEN** the tree is returned
- **THEN** it contains a renderable prefix within the budget and reports character truncation
- **AND** its cursor resumes before the first omitted document so traversal loses no candidate

#### Scenario: One document cannot fit

- **WHEN** one minimal document record and its required path exceed the requested budget
- **THEN** the caller receives an explicit budget error and retry guidance
- **AND** no continuation silently skips that document or repeats an empty page

#### Scenario: Pagination alone is not truncation

- **WHEN** a complete document page fits its character budget and more matches exist
- **THEN** next-page information is available to both model-facing carriers
- **AND** pagination alone does not set character truncation or display an alarming UI warning

#### Scenario: Large corpus latest lookup

- **GIVEN** a large authorized corpus
- **WHEN** the agent asks for one document sorted by latest addition
- **THEN** metadata hydration is bounded by the requested page and lookahead
- **AND** full corpus metadata is not loaded just to return that document

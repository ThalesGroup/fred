# ppt-builder Specification

## Purpose
Lets an agent generate a PowerPoint deck from a chat request on an unannotated corporate template, analysed once in the background into labelled patterns, or on the built-in Fred template, choosing each slide in code and delivering a preview and a download.

## Requirements

### Requirement: Template analysis needs no annotation

The system SHALL inventory an uploaded `.pptx` without requiring any marker, note or shape name. The inventory SHALL hold master layouts and example slides as patterns, each with a stable id, a label, a `kind` from the closed vocabulary (`cover`, `agenda`, `section`, `bullets`, `two_columns`, `comparison`, `cards`, `figures`, `process`, `timeline`, `team`, `quote`, `image_text`, `table`, `chart`, `closing`, `other`), a reusable flag, its text, image, table and chart slots with capacities, and its repeated groups with their item count.

- Every text-bearing shape of an example slide SHALL be a slot, except text repeated on two or more slides and footer, date or slide-number fields; a layout with a title and one body placeholder SHALL be a `bullets` pattern.
- Three or more sibling groups of identical structure, or three or more non-grouped text shapes of near-equal size and the same text style side by side (or two such shapes with an aligned second row), SHALL form one repeated group with its item count and per-item slots; the tool description says `items max N`, and unused items are removed and the rest recentred.
- Bodies of a two- or three-column layout wider than 35 % or taller than 40 % of the slide SHALL stay separate slots, never a repeated group.
- An example slide holding every placeholder of its layout (empty picture placeholders included) SHALL be the only pattern for that design, its sample text, notes, shape names and position taken into account.
- A first example slide with a title slot and no body content SHALL be a `cover` unless a template hint states another kind.
- A slide whose main content is a chart outside a chart zone, or a table that is not a data table (merged cells, or per-cell fills varying across the body), SHALL be inventoried but excluded and counted as excluded in the summary.
- A data table (at least two columns, no merged cells, empty or sample body cells, fills left to its table style) SHALL be a `table` pattern whose slot records the header row flag, each column's characters per line and the lines its rows show.
- A shape name or speaker-note line stating a role, kind or label SHALL take precedence over the heuristics and the vision label.
- A text slot's capacity SHALL be stored as characters per line × lines, from its geometry and font, raised within a bound until the designer's sample text fits; the fit check and the tool description SHALL use that stored capacity.
- An upload that is not a readable `.pptx` or exceeds 50 MB SHALL fail the save with one error carrying a stable code, and no analysis starts.

#### Scenario: Repeated heading and text pairs become a list, whatever their placeholder types

- **GIVEN** a slide or layout where no group or row was found, holding two size classes of text shapes as many each (TITLE or SUBTITLE placeholders included), every bigger-font shape with its own text right of it, or above or under it in its column
- **WHEN** it is analysed
- **THEN** three or more (heading, text) pairs form one repeated group read row by row: `cards`, or `figures` when the headings are figures ("333,000", "386,000 km", "xx%") captioned by a `label`, `timeline` when they are years or "20XX", `cards` for numbered texts in a grid, `process` for numbered texts along one line
- **AND** two plain pairs stay separate slots (a `two_columns` slide), and a lone big figure with its caption is a one-item `figures` slide
- **AND** a SUBTITLE placeholder covering a fifth of the slide or more is a body, so a paragraph slide is never a cover, and a text repeated on other slides stays a slot when its slide holds two same-size slots beside it

#### Scenario: Placeholders sharing an index

- **GIVEN** an example slide with two placeholders of the same `idx`, top-level slots or the picture slots of a repeated group
- **WHEN** it is analysed and then filled, pictures included
- **THEN** the first in drawing order keeps the `idx` as slot key, the next one its shape path, the pattern carries a warning, each slot is filled on its own (a picture in its own frame), and the deck never fails on it

#### Scenario: Library slides are never a design

- **GIVEN** an icon sheet (twenty or more small text-free pictures, groups or freeform glyphs), a slide titled as a resource page (icons, fonts, typography, palette, attributions, credits, graphic resources, instructions for use, this template), or a slide with no placeholder and no text but links that draws eight or more shapes or a linked picture
- **WHEN** it is analysed
- **THEN** it is excluded with the reason `library`, no deck slide is built on it, and its shapes stay in the stored template
- **AND** a slide with three or four icons next to its text, or a closing "Thank you" slide asking to keep an attribution, is not a library slide

#### Scenario: Zip bomb refused before it is inflated

- **WHEN** an upload under 50 MB declares members that would inflate beyond 512 MB in total or 256 MB for one member, or a member over 10 MB compressed more than 100 times
- **THEN** the save (of `ppt_builder` or `ppt_filler`) fails as an unreadable template without decompressing the archive, and no analysis starts

### Requirement: A named kicker line is a label, not a zone

The analysis SHALL treat a text shape whose shape name, or whose layout placeholder's name, names a kicker (`kicker`, `eyebrow`, `surtitre`, `sur titre`, `overline`, `pretitle`) as no zone: it SHALL NOT change the slide's kind, zones or count of empty zones. A kicker SHALL NOT be detected by geometry, and a title placeholder SHALL NOT be one. The renderer SHALL write nothing in a kicker and SHALL remove it without reporting removed example text.

#### Scenario: Kicker placeholder on a layout

- **GIVEN** a layout whose body placeholder above its title is named `kicker`
- **WHEN** the template is analysed and a slide is built on it
- **THEN** the pattern holds no zone for it, its kind is read from the remaining zones, and the delivered slide holds neither the kicker's text nor an empty placeholder, with no "template example text removed" line
- **AND** the same placeholder keeping its automatic name is a zone

### Requirement: Example slides are labelled by a vision model

The system SHALL render each example slide to an image with its slots numbered and ask a vision-capable model for the slide's kind, label, the purpose of each slot, the maximum number of items and whether the slide is reusable. Geometry and capacities SHALL stay those of the deterministic analysis.

- The labelling model SHALL be the one named in the capability settings when the team may use it, else the agent's default model; the selector SHALL list only vision-capable profiles.
- With "Use a vision model" off, the analysis SHALL make no model call, label by rules only, and run again because the setting changed.
- When neither the agent's resolved model nor any selectable profile supports vision, the toggle SHALL be shown disabled and off with a message that slides are labelled by rules, and the selector hidden.
- When the team loses access to the labelling model during an analysis, the analysis SHALL stop using it within 30 seconds.

#### Scenario: Vision label incompatible with the slots

- **WHEN** the model's kind needs slots the slide does not have (`bullets` without a body slot, `cover` without a title slot, `cards` without a repeated group)
- **THEN** the slide keeps its heuristic kind, takes the model's label and slot purposes, and the rejection is logged and shown as a pattern warning

#### Scenario: Vision unavailable or invalid

- **WHEN** the resolved model is not vision-capable, the call fails, or the answer is malformed
- **THEN** the slide keeps its heuristic kind and label, is marked as heuristically labelled, and the analysis still completes

### Requirement: Analysis runs in the background

The system SHALL complete the agent save without waiting for the template analysis, persist the result durably where every replica can read it, and expose its status to the agent form.

- A save SHALL store the template, record a pending analysis keyed by the agent and the template hash, and return; the same file with the same labelling settings and a succeeded analysis by the current rules SHALL be kept as is.
- While the analysis is pending or running the form SHALL show it in progress, then the summary and thumbnails; the agent SHALL be unavailable, with the reason, on the team agents page and not selectable in the chat agent picker; the card and form SHALL say, in the user's language, that the template is being read and the agent will be available again automatically in a few minutes (a generic "available again in a few minutes, nothing to do" when several capabilities declare what they prepare).
- On success the agent SHALL become available without another save: the next team agent listing re-checks it, ten preparing agents per listing in rotation, and a pod that does not answer in time leaves it unavailable without delaying the listing. A failed analysis SHALL NOT be re-checked by the listing.
- A save, create or copy SHALL never make a preparing agent available, even briefly: with no readiness answer (timeout, error, unreachable) or a readiness hook error the agent stays unavailable. A readiness answer SHALL NOT clear or replace a suspension made while it was in flight.
- A copied agent's analysis SHALL run with the destination team's model routing.
- A failed or interrupted analysis SHALL leave the agent unavailable, the form showing the error and that saving re-runs it; a save re-runs it from the stored template with the model port it carries.
- The build tool reached before the analysis succeeded SHALL build nothing and return that the analysis is not ready; a deck SHALL be rendered on the template its analysis was made from, never a newer file with an older inventory.
- The pod SHALL refuse, before building any team-scoped service (models included), a config save or copy by a user who cannot edit the team's agents and a readiness check by one who cannot use them; analysis status and thumbnails SHALL be refused to non-editors of the agent.
- Background analyses SHALL hold at most two of the pod's four heavy-job slots.

#### Scenario: Interrupted analysis recovers

- **WHEN** the replica running an analysis stops before finishing
- **THEN** the analysis is reported as interrupted once its lease expires, and the next readiness check, turn or save restarts it
- **AND** a vision-labelled analysis is restarted by a check or a turn only on a replica holding the model port the agent's last save left; elsewhere it stays interrupted, the agent unavailable, until a save re-runs it with vision; it never comes back labelled by rules

#### Scenario: Analysis rules change

- **GIVEN** an agent whose succeeded analysis was produced by older analysis rules
- **WHEN** its readiness is checked, a turn reads the analysis, or the agent is saved
- **THEN** the agent stays available on the stored analysis and one re-run starts in the background from the stored template, without a user token; concurrent checks on any replica start no second one, and the form shows it as being read again, then the new result without a reload
- **AND** when the re-run fails the stored analysis stays in use, no re-run starts automatically again, and the form says saving re-runs it
- **AND** a vision-labelled analysis is re-run by a check or a turn only on a replica holding the remembered model port; elsewhere the form shows it as outdated with the hint that saving re-reads it; a job run without the port logs a warning and records the rules labelling it used

### Requirement: Author review

The system SHALL let the author review the analysis (a thumbnail, label and kind per pattern) and change a pattern's label or kind or exclude/include it. Overrides SHALL be the only author input persisted besides the template, SHALL survive an ordinary save, and SHALL never be required.

- The assignment SHALL never use an excluded pattern and SHALL treat a re-kinded pattern as its new kind; a slide read as `other` (never chosen) re-kinded to a real kind is used as that kind, as a `kind:` note would.
- The review SHALL show example slides first, then the remaining layouts in a collapsed fallback section, excluded patterns last, opened by itself when the analysis excluded some; a pattern the analysis excluded keeps its reason when the author excludes it too.

#### Scenario: Overrides after re-upload

- **WHEN** a new template version is analysed
- **THEN** overrides whose pattern still exists are re-applied and the others are dropped and reported in the form

### Requirement: Slides are chosen by the code

The system SHALL accept from the model a plan of slides carrying content only (title, subtitle, bullets, columns, items, table, chart, images, notes and an optional `kind`, last in the schema) and SHALL assign each slide to a pattern deterministically. The tool schema and description SHALL NOT expose pattern ids; the description SHALL list the kinds the template offers and, per kind, every distinct variant with its label and the measured capacity of each zone.

- A slide without `kind` SHALL get one inferred from its content (items with figures → `figures`, two columns → `two_columns`, ordered items → `process`, …).
- A pattern SHALL NOT be a candidate when it lacks a slot for a non-empty field, holds fewer items than the slide carries, or cannot hold the text above the shrink floor. An example slide SHALL be preferred over a layout of the same kind, duplicated with its decoration intact.
- A kind the template does not offer, cannot fill with this content, or forbids at that position SHALL be replaced by a fitting pattern of a close kind, and the success message names the substitution, why, and how to get the requested kind; an unrelated kind (team, figures, cards for an agenda) SHALL never be used.
- Only the first slide MAY use the cover: a first slide without `kind` holding only a title and subtitle uses it; any other first slide is built as sent (no cover forced).
- A closing pattern SHALL be used at most once and only for the last slide; a contact closing (zones `contact_email` / `contact_phone`) SHALL hold only a closing that gives an `email` or a `phone`, each value in its own line, an empty contact line removed with its icon; without them another closing design holds it, or a `section` when the contact design is the only closing.
- Item pictures left empty SHALL count as a cost; a template slide whose picture zone sits on a layout or master shape (not a placeholder, no text, under half the slide) SHALL be a candidate only when the slide gives a loading picture for each such framed zone, and the catalogue quotes those pictures as required; a missing id or a non-image document counts as no picture and is reported as left out.
- Each text field's schema description SHALL state its room per kind (largest variant, the most common value plus the kinds that differ, the cover's own room); no field SHALL carry a hard `maxLength`.
- Rooms SHALL be quoted as a word budget then the measured characters (`≤4 words (≈32 chars)`, `≤20 words (≈71 chars × 2 lines)`, `1 word (≈12 chars)`, "1 short word" under 6 characters per line), words being `floor((C + 1) / 7)` per line × L, at least one; the fit check still measures characters. A list zone of L lines SHALL also state its entry limit `floor(L / 0.7)` (`≤14 words (≈101 chars × 1 line, max 1 entry)`).
- An item heading on a list whose items have a single text zone SHALL lead the item's text in bold when both fit, without loss; template icons of kept cards SHALL stay and removed cards' icons leave with them.
- The description SHALL include a choice guide for the kinds offered (numbers → figures, dates → timeline, parallel items → cards, ordered steps → process, a comparison → table, not restated as columns).

#### Scenario: No absurd substitution

- **WHEN** a slide asks for `agenda` with 17 items, the agenda slide holds 8, a team slide holds 30 and no close kind (bullets, process, timeline) holds the content
- **THEN** no deck is written and `needs_revision` names the slide with `items: 17 given; the largest 'agenda' slide holds 8, two slides hold 16`, the options `trim to 16 items (beyond 8 they continue on a second slide)` and `or keep 8 here and move the rest to slides of your own`, and what each close kind takes; the team slide is never offered
- **AND** with a process slide holding 20, the slide is built on it and the note reads "built as 'process' instead of 'agenda': the 'agenda' slide does not fit (items: 17 given, max 8). To get the 'agenda' slide, call again and trim to 8 items or split them over two slides."

#### Scenario: A cover dropped by a resend

- **WHEN** a whole deck is resent over a delivered one that opened on a cover, keeping at least 60 % of its other titles but no longer opening on a cover
- **THEN** nothing is built and `needs_revision` points to `changes` with an insert `after: 1` (or a remove of slide 1 when the user asked); a resend with most titles changed is a new deck, built as sent

#### Scenario: A list field over its entry limit

- **WHEN** a slide gives 3 bullets to a 1-line zone, or 2 entries that wrap to 23 lines in a zone of 11
- **THEN** the misfit reads `bullets: 3 entries; this zone holds 1 line (≈101 chars): at most 1 entry` with the option `merge bullets into at most 1 entry, or use another kind`, or `bullets: 2 entries wrap to 23 lines; this zone holds 11` with the option to keep each entry to one line

### Requirement: Long lists continue on a second slide

An items list or table rows that overflow every slide of the slide's kind, while each half fits, SHALL continue on a second slide of the same kind, preferably the same template slide, before any close-kind fallback; bullets, columns and a single field too long SHALL never be split, and no list SHALL be split over more than two slides.

- Parts SHALL be titled with ` (1/2)` and ` (2/2)` after the slide's title; a table repeats its header on each part.
- Items numbered by the model keep their numbers; unnumbered items on a slide showing numbers continue the count (06 to 09), set at render and never stored.
- After a split, the delivery and later `changes` SHALL use the file's slide numbers, the stored base plan being the deck as delivered (each part a slide with its rendered title, entries and kind); an agenda split over two slides announces its items once.
- Parts SHALL count as one slide for variety; a stored split rebuilt by `changes` is neither split nor suffixed again and stays on one template slide.
- Part numbers of delivered slides SHALL be recounted on the deck as it stands: a part left alone is titled `Offers`; a title never delivered, or with a count above two, keeps its own words.

#### Scenario: Overflowing list continues on a same-kind slide

- **WHEN** a slide asks for `agenda` with 9 items and the agenda slide holds 8
- **THEN** the deck holds two agenda slides of 5 and 4 items and the delivery note reads `Slide 2: its 9 items continue on a second 'agenda' slide (5 + 4, titles marked (1/2) and (2/2)): the largest 'agenda' slide holds 8. Nothing to do; to keep one slide, send at most 8 items.`

#### Scenario: Split cap reached

- **WHEN** a list needs more than two slides of its kind (17 items where the largest slide holds 8) and no close kind holds it whole
- **THEN** no deck is written and `needs_revision` names the slide, the capacity over two slides, and the options to trim to it or move the rest to slides of the model's own

### Requirement: Variety across the deck

The system SHALL spread a deck over the template's variants and, on the first deck of a conversation, SHALL ask the model once per turn to recast slides that repeat a template slide (`variety_check: template_slide`, default) or a kind (`kind`) beyond `variety_max_uses` (1 to 5, default 2); `off` SHALL never ask. Settings SHALL apply on the next turn without re-analysis; an agent saved before they existed SHALL use `template_slide` and 2. Cover, section, agenda and closing slides (asked, inferred or built on such a template slide) SHALL never count or be named.

- Assignment: three consecutive slides on one pattern SHALL use an existing alternative; an unused pattern of the same kind tier SHALL be preferred; with max 1 each slide SHALL get a different variant, a kind with fewer variants than its slides keeping its kind (the reuse priced). The applied maximum SHALL be raised to the content slides divided by the content template slides (or kinds), rounded up; a kind with fewer variants gets no higher maximum of its own.
- The count SHALL reset at each `section` slide (a deck with fewer than two sections is one section; agenda entries never start one); three consecutive content slides on one template slide with no other fit SHALL be asked with `in_a_row` true even within the cap.
- A conversation SHALL have a deck when the messages of the turn hold an earlier `build_presentation` result that delivered one (matched by tool call id when names are cleared, text-block lists read); `needs_revision`, errors or another tool's text never count.
- No ask SHALL follow a fit repair in the same turn, and a call refused before its plan is evaluated (unreadable, every slide empty, bad changes) SHALL NOT use up the ask; a `changes` call SHALL never be asked; the call after an ask SHALL be built as sent. A later deck, or a deck past its ask, SHALL be built with the repetition only noted (slides, kind, content-based alternatives).
- An ask merged with fit problems SHALL be one `needs_revision`; slides to fix whose closest fits push a template slide or kind over the cap SHALL be listed under both `slides` and `variety`, and no option for them names a template slide with the same fit problem.
- Suggestions SHALL come from text patterns without a model call, one kind per slide spread across kinds, only for a kind whose variant holds that many entries (quoting `up to N items` with each field's size, or `exactly 2 columns`, and asking to shorten when the longest entry is longer), only while its distinct variants outnumber the deck's slides of that kind (counting each suggestion), never a template slide not checked against the content, and never one whose framed picture area the slides cannot fill.
- The description SHALL state the maximum (with 1, that each slide must look different; else at most N uses of any variant or N slides of any non-structural kind; none when off) and that it counts within each section.
- In the agent form, the variety switch off SHALL save `off` and disable the mode and max selects; on restores the last mode.

#### Scenario: The limit counts within each section

- **GIVEN** a first deck with two sections and a variety cap of 2
- **WHEN** one template slide is used twice in Italy and twice in Spain
- **THEN** no ask is returned and the deck is built; the same slides without section boundaries count four uses and are asked; three uses inside one section are listed under `variety` with `at_most` 2

#### Scenario: Alternatives read from the content

- **GIVEN** a kind repeat whose slides hold dated lines on one slide and `Label :` header lines followed by `- ` lines on two others
- **WHEN** the variety ask is returned
- **THEN** it names the first slide with `timeline` and the two others with `two_columns` and `cards`

#### Scenario: Identical slides the user asked for are built and noted

- **GIVEN** three consecutive slides on one template slide, with `repeat_layout` true on the third (the user explicitly asked for identical slides)
- **WHEN** the deck is assigned
- **THEN** that slide keeps the previous slide's template slide, is left out of the cap and the three-in-a-row rule, the notes say so and the summary carries `layout_repeated`; when it does not fit there it is built elsewhere with a note and `layout_not_repeated`
- **AND** the description says to set `repeat_layout` only on the user's explicit request; `{"op": "edit", "slide": N, "field": "repeat_layout", "value": true}` sets it on a delivered deck

### Requirement: Variety never leaves a zone unfilled

The assignment SHALL NOT take a template slide that leaves more zones unfilled (text zones swept away, empty pictures) than another fitting template slide of the same kind whose fit cost is not higher; reuse, repeat and maximum-use prices SHALL only choose among the remaining ones, and the variety ask SHALL NOT offer such a slide. A slide SHALL keep the template slide it was delivered on while it still fits. A chart slide without a requested kind SHALL take a chart template slide before a content area. An unfilled takeaway zone SHALL count as two unfilled zones; with the takeaways shown and fitting, the template slide holding the zone is still preferred.

#### Scenario: Bare charts keep the centred chart slide

- **GIVEN** a centred chart slide (title and chart), two chart slides with a text box beside the chart, and `variety_max_uses` 1
- **WHEN** six slides each holding only a title and a chart are assigned, then four holding a title, a chart and bullets
- **THEN** the six take the centred slide with no ask; the four alternate the two side slides, never the same one twice in a row

#### Scenario: Built-in chart slides

- **GIVEN** the built-in template and `variety_max_uses` 1
- **WHEN** slides holding a title, a chart and a takeaway not shown are assigned
- **THEN** they take "Fred Chart Wide" (full width, one-line caption); with the takeaways shown, or a takeaway text in `bullets`, "Fred Chart" (card beside the chart)

#### Scenario: Max uses never forces an empty zone

- **GIVEN** `variety_max_uses` 1, a bullets example slide and a bullets layout with an extra picture zone
- **WHEN** two bullets slides without pictures are assigned
- **THEN** both take the example slide; with a second variant that fills all its zones, the second slide takes it

### Requirement: The agent builds directly

The system SHALL instruct the agent to write the plan and call `build_presentation` in the same answer, and to ask the user to validate an outline only when the user asked for it or the request does not say what the presentation is about.

- On a revision the working rules SHALL tell the agent to do only what was asked (other content is proposed, not added), send `changes` for the slides concerned and the whole deck only for a new deck or a rewrite of most slides, never drop or replace a slide to keep an earlier count unless asked, act on the one slide an unnamed request can mean (ask only when several match), claim a build only after a delivery in that answer, describe only what the result lists, and say so when nothing needed changing or could be applied.
- On a request for another template, the working rules SHALL name the template in use and say the tool cannot switch it: an editor of the agent uploads another in its settings.

#### Scenario: Request with a subject

- **WHEN** the user asks for a presentation on a stated subject without asking to see the plan first
- **THEN** the working rules tell the agent to build the deck in that answer rather than ask for confirmation; with an outline asked for, or no subject, it may ask first

### Requirement: No silent fallback

The system SHALL NOT substitute an unfitting pattern for a slide. When a slide fits no pattern, the tool SHALL build nothing and return a structured `needs_revision` result the model can act on. An expected revision SHALL NOT be a failed tool call: only a bad call, an unavailable template, a busy server, a render or a storage failure SHALL be an error.

- Not errors: fit problems, a variety ask, a resend identical to a call refused this turn, a later call of one model round, a deck that changes nothing. Errors: an unreadable plan, `slides` and `changes` together, empty `changes`, no deck to change, changes that cannot be applied, every slide empty, the previous deck unreadable, the template not loadable, a busy server, a render or upload failure, an analysis not ready.
- Each revision text SHALL end with: `Your very next message MUST be a new build_presentation call with these fixes applied, never a final answer, unless the user must decide something first.`
- Every text returned to the model SHALL state what happened, why, and one concrete remedy (or that there is nothing to do); a result that builds nothing starts "No deck was built", and the delivery prefixes stay unchanged.
- Options SHALL name only what the content can fill: never a template slide whose framed picture area the slides cannot fill.
- A slide with the same problem as in the previous result SHALL be told whether it was resent unchanged or changed without fixing it.
- A success with substitutions, truncations, removed leftovers or lost content SHALL name them per slide; renderer findings not in the after-check report (an agenda announcing more parts than follow, a heading running into the text, an items slide without items, content sent to a fixed slide, an unfittable table) SHALL add one "To review" line each with its remedy.

#### Scenario: Slide fits nothing

- **WHEN** one slide fits no included pattern of any kind (seven items where the largest list holds six)
- **THEN** no deck is written and the result lists, per failing slide, its index, the exact field and element with the measured limit (`bullets[2] is 214 chars; this zone holds ≈40 chars × 3 lines`, `items: 7 given, max 6`) and concrete options in this template

#### Scenario: Plan text that would be dropped

- **WHEN** a column or item carries a key that is no field (`"heading2": "Italie"`), or has a heading without a body (or the reverse) while another entry of the list has both
- **THEN** `needs_revision` names the slide and field (`columns: heading2 'Italie' is not a column field`, `columns[1] has heading 'Italie' but no bullets`) with the fix

#### Scenario: Partial fix after needs_revision

- **WHEN** a call returns `needs_revision` for slides 4 and 9 of a 12-slide plan and the model sends only `changes` for them
- **THEN** the changes apply to the refused plan, the whole plan goes through assignment, fit, variety and render, and the other ten slides are those of the refused plan

### Requirement: Rendering only fills the template

The system SHALL build each slide by instantiating a layout or duplicating an example slide and filling its slots; it SHALL never draw shapes the template does not hold, and the original example slides SHALL never appear in the output.

- A duplicated slide SHALL share the template's picture and media parts, copy its colour-map override and notes, and re-create only image, media and external hyperlink relationships; links to other template slides and template sections SHALL be dropped.
- Body levels SHALL take the template paragraph formatting of their level; leftover original text SHALL be removed and reported; shapes sharing an id SHALL each be their own zone.
- A subtitle without a subtitle zone SHALL lead the body as an unbulleted line; step numbers without a number zone SHALL be left to item order; an item label without a label zone SHALL be a line under its heading; none counts as lost.
- Unused repeated items SHALL be removed with the decoration drawn only for them (frame, mark, connector, on the slide or its layout; layout graphics are then copied onto that slide only and hidden on it), and kept items recentred with their decoration (team photos with their names).
- Text too long SHALL shrink down to a floor measured with its drawn font, then be cut at a word boundary and reported; shrinking alone is not a truncation. A `number` zone is measured against its own box (a trend arrow at its drawn size), its room quoted at the floor.
- An image SHALL fill its slot's frame keeping its ratio, centre-cropped, in the slot's shape with the example alt text; an empty image slot and an empty text box drawn with its own fill or outline SHALL be removed; an invalid image reference is named.
- Section slides without a `number` SHALL show their place among the deck's sections (01, 02…) as the zone's example writes it.
- A two-column template slide SHALL take `columns` only (`bullets: this slide has no place for it`, catalogue `columns.bullets×2`); one with headings but no title zone is listed without `title` and does not fit a titled slide. A takeaway zone beside a body SHALL never be a column; it holds only a shown takeaway, else is removed, and as the only body holds the bullets.
- A closing's single body SHALL hold its bullets as a list; a closing shown on a section slide gets no number and counts as no section.
- Malformed JSON shapes (a list as a string, an alias, a field twice) SHALL be coerced without losing text; a non-object entry is named, an unmappable key is a `needs_revision` problem. `columns` sent as one object SHALL build nothing, and two edits of the same field of one slide in one call SHALL be refused.
- A Wingdings 3 bullet SHALL be drawn `►` in Arial in the preview only.

#### Scenario: Columns sent as one object

- **WHEN** a slide's `columns` is one object instead of a list
- **THEN** a `slides` call gets `needs_revision` with `columns sent as one object, not a list` and the list form as option; a `changes` edit is refused naming the whole list or `columns[i]`

### Requirement: Tables fill the template's table

The system SHALL fill a `table` pattern's table from a plan's `table` (`header`, `rows`), keeping the template's table style, column count bound and position, and SHALL NOT cut a cell's text or draw a table the template does not hold. The built-in template SHALL hold one data table example slide (header row flagged, no merged cells, no per-cell fill, border or typeface, the deck's default table style) analysed as an included `table` pattern of five columns, so tables on agents without a template follow the same rules and are offered a `table` field.

- Surplus rows and columns SHALL be removed and the others widened to the same total width; rows that fit the line budget at full size or at the shrink floor beyond the template's rows are cloned from the last one with fresh ids, one font scale for the whole table; the frame height follows the rows; no template cell text remains.
- A plan table with no table slot in the template SHALL be a misfit naming it, never converted to bullets.

#### Scenario: Rows and columns adapted

- **GIVEN** a template table of 12 rows × 5 columns with a header row
- **WHEN** a plan gives a header and 6 rows of 4 cells
- **THEN** the header and 6 body rows are written, the fifth column removed and the others widened

#### Scenario: Table too large

- **WHEN** the rows exceed the line budget at the shrink floor beyond two slides, or the columns exceed the template's (6 on the built-in deck)
- **THEN** no deck is written and `needs_revision` names the limits (lines needed vs held, longest cell and its column's characters per line, columns given vs max) with options

#### Scenario: Built-in table follows the theme

- **WHEN** a table of 5 columns and 6 short rows is rendered on the built-in deck
- **THEN** it is delivered without `needs_revision`, references the deck's table style and carries no literal colour or typeface

### Requirement: Built-in template and platform default

The system SHALL ship a real `.pptx` Fred template with example slides and its pre-computed analysis as the platform's initial default template; a test SHALL fail until that stored analysis is regenerated after an analysis rules change. The platform SHALL always have exactly one platform-wide default; an agent with no template of its own SHALL build on it through the same path as a customer template, and an agent's own template SHALL always win. A capability manager, platform admin or feature manager MAY replace it from Admin > Features (ppt_builder settings drawer) with a `.pptx` within the agent template size limit, stored in the capability's own table, analysed in the background, reviewable and re-runnable; other callers SHALL be refused with 403 on every write, and any authenticated user MAY read its status, summary and previews (the drawer read only). The Fred template SHALL never be removable: "Reset", after confirmation, deletes the replacement, any replacement being analysed and all pattern edits (the Fred template's included).

- A replacement SHALL take effect only once its analysis succeeds, the previous one then deleted; while pending, running or failed, agents keep the previous default with its edits and stay ready, and the drawer shows status, file name, failure and re-run.
- An analysis of the default SHALL never make an agent unready or suspended; a change SHALL reach every replica within 30 seconds plus one turn, with no database read on an ordinary turn.
- The labelling model SHALL be chosen among the vision-capable models offered without a team (models enabled for every team, profiles on every pod), or rules only, defaulting to the platform's default model (rules when it cannot read images); another model SHALL be refused with 422; the choice applies to the platform template only.
- A capability manager SHALL review and edit (rename, include/exclude, re-kind) the patterns of the default in effect, the Fred template included; edits apply to every agent on it within the propagation bound; a re-analysis of the same file keeps edits whose patterns exist, another file starts without; the Fred template's edits are kept but not applied while a replacement is in effect.
- Pattern edits SHALL apply only to the template they were made on: an agent without its own template has no edits of its own, and one that removes its template drops its edits.
- The agent form SHALL show the default in effect with a read-only review; with a replacement, "Template set by the administrator" (fr: "Template défini par l'administrateur") with its file name.
- Only capabilities with a platform panel SHALL show a settings action in Admin > Features.

#### Scenario: Built-in deck read by the rules

- **WHEN** the built-in deck is analysed without a vision model
- **THEN** its agenda lists up to seven numbered entries, section slides are `section` with a number zone that never takes the subtitle, each timeline milestone carries its date as number, its table takes up to five columns, statement slides are `quote`, and each item slide removes an unused item with its card, tile or dot

#### Scenario: Analysis failed

- **WHEN** a replacement default's analysis fails
- **THEN** agents keep building on the previous default and stay ready, and the drawer shows the failure with a re-run action

### Requirement: Delivery

The system SHALL write the deck to the conversation's agent workspace, publish a PDF preview beside the chat when conversion is available (the `ppt_filler` preview card and pane with a `.pptx` download, even without the `ppt_filler` capability), and otherwise show a download chip and tell the agent the preview is unavailable. An answer that builds several times SHALL show one card, for the last build.

- Of several `build_presentation` calls in one assistant message only the first in message order SHALL run; each other builds nothing and says how many were sent, which one is processed (by its first slide's title), that a deck is sent in ONE call with every slide, cover first, and changed with `changes`. Outside the agent loop calls run one at a time.
- A `slides` call assigning exactly the deck delivered this turn (same file name, same content and template slides) SHALL render, upload and store nothing and say "unchanged, deck already delivered as '<file>'", not to tell the user it changed, and to use `changes`.
- The preview part SHALL carry, per rendered slide, its place, split part, title, kind, template slide and note codes taken from the render; card and pane show an info button opening it in the user's language (none for a `ppt_filler` deck).

#### Scenario: Several build calls in one model round

- **WHEN** one assistant message asks for several `build_presentation` calls
- **THEN** only the first in that message's order is run, whichever finishes first

### Requirement: Chat-time corrections are per conversation

The system SHALL let the user correct a deck in chat by regenerating from an amended plan and SHALL NOT change the agent configuration from a conversation. `build_presentation` SHALL accept the whole deck (`slides`) or `changes` (`replace`, `insert` after, `remove`, `move`, `edit` one field, `like`) numbered on the last deck delivered or plan proposed in the conversation, stored per conversation and agent for any replica and later turn (within a turn, on the `slides` plan last refused, never stored), and SHALL always render the whole resulting deck through the normal path.

- A refused `changes` call SHALL leave the base as it was: the next call of any shape applies to that base, refused slides numbered on it (an insert pointed to its change, `new, sent in changes[0]: fix it there`); a refused plan is never the next turn's base. Once delivered, the same changes sent again are a new change.
- Untouched slides SHALL be identical to the delivered plan's; a replacement that still fits, a substituted kind, and a slide identical to a delivered one in a `slides` resend SHALL keep their template slide; pins written by the model (`built_on`, `asked_design`, `asked_from`) SHALL be ignored. The description says `edit` keeps the design and `replace` is for a different slide.
- `like` (`{op: "edit", slide: 7, field: "like", value: 5}`) SHALL rebuild the slide on the template slide slide 5 has in the delivered file, uncounted for variety, pinned thereafter; content or kind it cannot hold, a framed picture area it cannot fill, or a bad `like` (no number, out of range, itself, removed, twice, not delivered) SHALL build nothing, with what, why and the remedy.
- The delivery SHALL give one `Designs:` line naming each file slide's template slide by its review label (never an id; duplicates `'Free text #2'`; cut at 28 chars), template slides looking the same once filled sharing one name and counting as one design, a chart built as another type saying so (`9 'Grouped bar chart', built as a pie chart`).
- `file_name`, `audience` or `main_message` written inside `slides` or `changes` entries (or as string debris) SHALL be lifted at tool validation and debris dropped; conflicting top-level values build nothing, naming both.
- Slide fields beside `op` on `replace` or `insert` without `slides` SHALL be read as its one new slide; on `edit`, `remove` or beside non-empty `slides` they build nothing with the reason.
- A bad change (unknown slide, op or field, two changes on one slide, a bad move: no `after`, after itself, removed, twice, a loop) SHALL build nothing, name each change, why and the remedy (`changes[2] (remove): slide 14 does not exist; the previous deck has 12 slides. Use a number from 1 to 12.`), and leave the stored plan unchanged; `changes` with no deck or evaluated plan says to send `slides`; `slides` and `changes` together names the one to send.
- Changes that leave every slide and the file name as they are SHALL build nothing and say so, why, not to tell the user, and the remedy.
- A `kind` edit SHALL clear fields the new kind's template slides cannot show (not those the call sets) and say so; a refused `changes` option dropping a field carries its exact change (`drop bullets: {"op": "edit", "slide": 10, "field": "bullets", "value": []}`), a refused `slides` call keeps it in words.
- Editing only a `takeaway` without `show_takeaways` SHALL change only the speaker notes, the delivery saying so.
- Inserts or moves `after` 0 SHALL open the deck, before the cover; a moved slide carries its edits, one moved after another moved slide follows it.
- An identical call to one refused this turn (same arguments, same base) SHALL not be re-evaluated: it restates the problems and suggests `replace` with whole slides or dropping the change.
- A new delivery SHALL list changed or added slides, removed ones, moved ones (`moved: 3 (was 2)`) and `N slides unchanged`, comparing rendered slide XML with its charts and pictures (notes-only changes named as such), pairing slides in a run of differences by shared words; a slide on a design holding fewer points says `Tell the user that points were merged or dropped in the new design of slide 8 (7 → 6): that content is not the same as before.`; a `slides` resend touching at most two slides adds that such an edit is sent as `changes`.

#### Scenario: Later-turn edit keeps untouched slides

- **WHEN** a deck was delivered in an earlier turn and the model sends only `changes` putting a phone number on the last slide
- **THEN** the whole deck is rebuilt from the stored plan with that one change, every other slide identical, as a normal delivery

#### Scenario: A kind edit clears what the new kind cannot hold

- **WHEN** a `changes` call edits slide 10's `kind` from `bullets` to `two_columns`, its `title` and its `columns`
- **THEN** its bullets are cleared, title and notes stay, the deck is built, and the result says the bullets were cleared and why

### Requirement: The deck ends on the template's closing slide

When the template offers a `closing` kind, the system SHALL end every built deck on a closing slide, outside any slide count the user asked for: when the last slide is not a closing it SHALL append one at build time, never in the outline the user reviews. The only opt-out SHALL be `no_closing: true`, set when the user explicitly asked for no closing.

#### Scenario: The closing is added outside the slide count

- **WHEN** the model sends N slides whose last is not a closing (asked as `closing`, with an `email` or `phone`, or a bare title such as "Merci") and `no_closing` is not set
- **THEN** the outline lists N slides, the deck holds N + 1 ending on "Merci" / "Thank you" (the plan's language) on a design without contact zones, and the delivery says it was added outside the count
- **AND** nothing is added when the deck ends on a closing, the template has none, the plan is empty or `no_closing` is true

#### Scenario: A revision keeps the closing at the end

- **WHEN** a `changes` call edits the deck or removes the added closing without `no_closing`
- **THEN** the deck still ends on a closing; `no_closing: true` removes the added closing (a model-written one stays), sticks for later calls that leave it out, and a call only toggling it is never answered as unchanged

### Requirement: Intent fields express meaning, never style

The system SHALL accept optional intent fields (`chart.highlight`, `chart.sort`, `chart.stacked_as`, `table.total_row`, `table.highlight_row`, `table.highlight_column`, `items[].trend`) whose values are a short enumeration, a boolean, or a reference to plan content, and SHALL NOT accept a colour, font, size or position through them. Each SHALL default to the rendering without it, and its look SHALL come from the template. An intent that cannot be rendered SHALL still build the deck with a note naming the field and a remedy, and `intent_not_shown` (or `intent_shown_otherwise` for a fallback) on the slide's summary entry. Intent fields SHALL be editable through `changes` and offered in the schema only when the template can render them.

#### Scenario: Reference that matches nothing

- **WHEN** a chart of categories Q1 to Q4 gets `highlight: "Nord"`, or `highlight: "red"`
- **THEN** the deck is built without highlight, the note lists the valid categories, and the summary holds `intent_not_shown` for `highlight`

### Requirement: Chart, table and key-figure emphasis

The system SHALL reorder a chart's categories with their values for `sort: desc | asc` (by the first series, or category totals for a stacked column), SHALL keep the order for `given` and for line and area charts (noting a requested sort), and SHALL draw a bar chart's first category on top. `highlight` SHALL draw the named category (one-series column, bar, stacked column, pie, doughnut) or series in the first colour of the chart colour sequence and the rest in a muted colour from the theme text colour, never a literal colour; a category on a one-series line or area chart is `intent_not_shown`. `stacked_as: percent` on a stacked column SHALL build a 100 % stacked column. `table.total_row: true` SHALL apply the table style's total-row formatting, or bold with `intent_shown_otherwise`; without it no template total-row formatting SHALL remain. `highlight_row` / `highlight_column` (index, first-cell text or header text) SHALL be bold with a tint of the style's accent distinct from its bands, paler when dark text would not stay readable. `items[].trend: up | down | flat` SHALL show an arrow before the figure in its own text style, smaller, never coloured by meaning.

#### Scenario: Highlighted category

- **WHEN** a one-series column chart has `highlight: "Q3"`
- **THEN** the Q3 bar references `accent1`, the others the muted theme text colour, and no `srgbClr` is written

#### Scenario: Intent the chart or template cannot show

- **WHEN** `stacked_as: percent` is sent on a `line` chart, or `trend: down` on an item whose group has no number zone
- **THEN** the deck is built and the summary holds `intent_not_shown` for that field

#### Scenario: Rising key figure

- **WHEN** a figures item has `number: "42 %"` and `trend: up`
- **THEN** it reads `▲ 42 %`, the glyph in the figure's own font and colour, smaller than the figure

### Requirement: Slide takeaway

The system SHALL accept a `takeaway` on every plan slide (the conclusion the audience draws), asked by the working rules on every slide not `cover`, `agenda`, `section`, `closing` or `quote`, with the title as that conclusion in a short sentence. It SHALL write the takeaway as the first line of the speaker notes, SHALL NOT derive the title from it (no title sent, no title), and SHALL NOT refuse a slide for its takeaway (missing, short, a question, equal to the title) nor for numbers in its title or subtitle.

The analysis SHALL mark at most one text zone per pattern as a takeaway zone, from its shape or layout placeholder name or vision purpose, never from geometry; a free text box so named is a body whatever its size. The takeaway SHALL be written into that zone only when the plan sets `show_takeaways` (only on the user's explicit request, no word list), the template slide has the zone and the takeaway fits; the zone is then not filled from `bullets`. Otherwise the zone is filled from content only as the slide's only body, the takeaway stays in the notes without refusal, and with `show_takeaways` the summary holds `intent_not_shown` for `takeaway` (a too-long takeaway also tells the agent to shorten it). The takeaway SHALL NOT change the kind assigned; with `show_takeaways`, a template slide of the kind that can show it SHALL be preferred.

#### Scenario: Takeaway in the template's zone on request

- **GIVEN** the built-in template
- **WHEN** the model sends a chart slide with one bullet and a takeaway, first without `show_takeaways`, then with it (the user asked in any language)
- **THEN** without it the card holds the bullet and the takeaway is in the notes only; with it the slide is on the chart slide with the card, which holds the takeaway

#### Scenario: A large box named for the key message

- **GIVEN** a free text box named "Message clé" whose sample text is 24 pt on one line
- **WHEN** the template is analysed
- **THEN** it is a body zone flagged as the takeaway zone, not a heading

### Requirement: Charts fill a chart zone the template offers

The system SHALL accept a `chart` field holding only data (`type`: `column`, `bar`, `line`, `pie`, `doughnut`, `stacked_column`, `area`; `categories`; `series` with a `name` and one numeric value per category; optional `title` and `unit`) and SHALL NOT expose any colour, position, size, font or style field. The analysis SHALL expose as a `chart` zone every chart placeholder and every chart frame covering an example slide's main area (an included `chart` pattern), and SHALL mark large `OBJECT` placeholders chart-capable. A chart SHALL go in a chart zone, else a free chart-capable placeholder as a reported substitution, else `needs_revision` (options: table, key figures from the roomiest figures slide, drop); never elsewhere. Charts SHALL be native, editable charts whose series colours follow the template's example chart series colours (as theme references when so written), then the theme accents those leave out, or the accents alone, with text in the theme's body font; an example chart of the requested type SHALL be reused with its formatting, data replaced, otherwise a fresh chart is built.

- Values SHALL be read loosely (`"12,5 %"` → 12.5); a non-number, or a series whose value count differs from the categories, SHALL be a `needs_revision` naming the path or counts.
- More categories than the zone holds at a readable size (measured at the zone's own text size), more series than the cap, or a multi-series pie SHALL be refused with the limit and a remedy, never cut or split; series later dropped to meet the cap and shown nowhere SHALL be named in the delivery notes.
- An unsupported type SHALL be built as a column chart with a note; colour or position keys SHALL be ignored with a note.
- The summary SHALL show kind `chart`, or the substituted kind with `chart` noted.

#### Scenario: Colours follow the template's example charts

- **GIVEN** a template whose example column chart paints its two series with `tx2` and `bg2`
- **WHEN** a fresh pie of four slices is rendered, then with one slice highlighted
- **THEN** the slices reference `tx2`, `bg2`, `accent1`, `accent2`; with the highlight, the stressed slice references `tx2` and the others muted text; with no example colours, `accent1`, `accent2`, `accent3`

#### Scenario: A small chart is measured at its own text size

- **GIVEN** an example slide of four quarter-slide bar charts whose text is 10 pt
- **WHEN** the model sends a bar chart of six short categories, then eight
- **THEN** six are accepted and eight refused with the measured limit

#### Scenario: Chart edited through changes

- **WHEN** the model sends `{"op": "edit", "slide": 4, "field": "chart.series[0].values[2]", "value": 21}`
- **THEN** the deck is re-rendered with that value changed and slide 4 on the same template slide

### Requirement: Pie and doughnut labels show what the plan asks

The system SHALL accept an optional chart `show` (`share`, `value`, `both`; unset meaning `value` with a `unit`, else `share`) setting what pie and doughnut slice labels hold; `both` on values in `%` shows each value once. The model SHALL NOT write a number format. Loose spellings and aliases `display`, `labels_as`, `show_as` SHALL be read, `labels` SHALL alias `categories`. A non-`%` unit hidden by `share` SHALL be told with the fix (`chart.show` `value`) and noted in the summary; `show` on another chart type SHALL be told as not applied.

#### Scenario: Numbers instead of percentages

- **WHEN** a pie has `unit: "collaborateurs"` and `show: "value"` (or `both`)
- **THEN** labels show `27 collaborateurs` and no percentage (with `both`, the percentage on the next line)

#### Scenario: Data with a unit shows its own values by default

- **WHEN** a pie with `unit: "%"` (rates 5 to 22) has no `show`
- **THEN** labels show the values (`22 %`), never their shares (`28 %`)

### Requirement: A chart holds one measure

The system SHALL put a category chart's amounts in one scale of their unit before the slide assignment, and SHALL return `needs_revision` for a chart still written with two different units, every time it is sent (a scatter or bubble per axis); a `changes` call SHALL be checked on the slides it touches only. The system SHALL NOT refuse a chart for the spread of its values or, on a slide with several charts, for a missing chart title.

- Scale prefixes of one base unit (k€, M€, Md€; k$, M$; K, M, B, bn, Md) SHALL be converted to the scale that puts the largest value between 1 and 999; a single unit reaching 10 000 or more, or 1 000 or more of a scaled unit, SHALL be shown in such a scale; a stacked chart is measured by its largest total; a title naming the old unit names the new one; a value rounding to 1 000 moves up one scale; a bare number beside several scales is not converted.
- Converted values SHALL carry the unit in their number format, labels included, billions spelled Md (fr) or bn (en), at most 2 decimals (none when whole); axis ticks round, at most five intervals, with their step's decimals, 0 reading "0".
- Text amounts of 10 000 or more with a currency sign SHALL be shortened the same way in the deck's decimal separator, table cells and both ends of a range included; amounts glued to an identifier or a path, or grouped with the deck's decimal mark, stay as written.

#### Scenario: Two written units

- **WHEN** a series holds "12 %" and "3 M€"
- **THEN** no deck is built and the problem names both units, again on each resend

#### Scenario: Scales normalised

- **WHEN** a French chart in `€` holds 2 450 000, 1 380 000, 640 000, 215 000 and 48 500, or a series holds "500 k€" and "2 M€"
- **THEN** it plots in `M€` (2,45 M€, not 2 450,0 k€; 0.5 and 2), its axis starting at "0"; "1 500 €" and "2 300 €" plot as written; 45, 2800, 9 with no unit build as sent without a note

#### Scenario: Amounts in text

- **WHEN** a French slide's text reads "450 000–520 000 €", "999 999 €", "REF-120000€" and "$1,250,000"
- **THEN** they read "450–520 k€", "1 M€", "REF-120000€" and "$1,250,000"

### Requirement: Figures are sourced

The system SHALL write a slide's `source` (a document name, `user`, or `illustrative`) to its speaker notes; `illustrative` SHALL also be said in the chart caption and as `illustrative_data` in "What was built", nowhere else. The system SHALL NOT refuse a slide for a missing or illustrative source, SHALL NOT check figures against the conversation, and SHALL NOT claim to verify a figure. The working rules SHALL ask for `source` only for content from the user's documents or data.

#### Scenario: Illustrative data

- **WHEN** a chart has `source: "illustratif"`, whatever the user's language
- **THEN** the deck is built, the caption ends with "(illustratif)", the notes say the figures are illustrative and the summary holds `illustrative_data`; a slide with no source is built without a note

### Requirement: Plan validation before the first build

The capability SHALL offer "Validate the plan before building", off by default. When on and no deck was delivered in the conversation, a problem-free `build_presentation` call SHALL get a `plan_proposed` result holding a code-written outline (audience, main message, per slide kind, title, takeaway and source, then the build's assignment notes worded as the user's choice, "If the user wants …", numbered as the outline), SHALL store that plan, and SHALL build nothing until the user approves; a plan with problems gets `needs_revision`. With `ask_user` offered, only its approval choice ("Approuver" / "Approve", beside a free answer) SHALL approve; a free answer is the user's changes. Without it, the next user message is the answer. Approved, a `slides` plan is built or `changes` apply to the proposed plan. `skip_plan` SHALL build at once only when its quote appears word for word in the user's latest message (ignoring case, spacing, quotes, punctuation; no word list). Changes to a delivered deck SHALL NOT wait. The working rules and the `plan_proposed` result SHALL tell the agent to ask for approval with `ask_user`, the outline as its question, or without it to show the outline, end its answer and not call `build_presentation` again in that answer.

#### Scenario: Outline with a fallback note

- **WHEN** the setting is on, no deck delivered, and the plan's second slide asks for `closing`
- **THEN** no deck is built, the outline lists it as `section` with the note "built as 'section' instead of 'closing' … If the user wants it as the closing slide: move it to the end"; a second call in the same answer repeats the proposal

#### Scenario: Approval with ask_user

- **GIVEN** a `plan_proposed` result and `ask_user` offered
- **WHEN** the next model call is sent
- **THEN** it can only call `ask_user`, with the approval choice and a free answer; after the approval choice the next call can only call `build_presentation`; after a free answer "remove slide 3", the revised plan is proposed again

#### Scenario: Skip quote the user never wrote

- **WHEN** the model sends `skip_plan` "Prépare la présentation sans validation intermédiaire" the user did not write, or no `skip_plan` although the user wrote "sans plan"
- **THEN** no deck is built and the result is `plan_proposed`; a quote of "hazlo directamente, sin plan" the user wrote builds the deck

### Requirement: A proposal or a delivery ends the answer

After a `build_presentation` result that delivers a deck, or proposes a plan without `ask_user`, every later model call of the same answer SHALL be sent with `tool_choice="none"`, lifted by the user's next message. A proposal with `ask_user` SHALL be followed by its approval question, and a skipped question ends the answer the same way. A `needs_revision` result or an error SHALL NOT end the answer.

#### Scenario: Deck delivered with variety notes

- **GIVEN** a delivered deck whose result carries variety notes, and no user message after it
- **WHEN** the agent's next model call is sent
- **THEN** it carries `tool_choice="none"`; after a `needs_revision` or error its tools are unchanged

### Requirement: More native chart types

The system SHALL accept `stacked_bar`, `radar`, `scatter` and `bubble`, built as native charts (`BAR_STACKED`, `RADAR_MARKERS`, `XY_SCATTER`, `BUBBLE`) under the chart placement, colour, font and code-decided legend, labels and formats rules. `stacked_bar` and `radar` take categories and values, follow the one-measure checks of their value axis including the spread question; a radar SHALL have 3 to 8 categories. `scatter` and `bubble` SHALL take series of points (numeric `x`, `y`, positive `size` for bubble, optional `label`), required `x_title` and `y_title`, optional `x_unit`, `unit`, `size_title`, `size_unit`, one unit per axis, no spread question, 3 to 50 points (scatter) or at most 15 (bubble); points' numbers count as the slide's figures for the source checks. Non-numeric categories on a scatter or bubble, or points on a category chart, SHALL name the type to use; numeric categories with values are read as x values. Every refusal SHALL be a `needs_revision` problem; no data SHALL be cut or rescaled.

#### Scenario: Scatter built from points

- **WHEN** the model sends `chart: {type: scatter, x_title: Price, x_unit: €, y_title: Units sold, series: [{name: Products, points: [{x: 10, y: 120}, {x: 15, y: 90}, {x: 22, y: 60}]}]}`
- **THEN** the slide holds a native XY scatter with markers only, axes titled "Price (€)" and "Units sold"

#### Scenario: "Stacked bar" in words

- **WHEN** the chart type is written "stacked bar"
- **THEN** a horizontal stacked bar chart is built, not a stacked column

#### Scenario: Refused chart shapes

- **WHEN** a `radar` has two categories, a `scatter` has categories `[Q1, Q2, Q3]` or no `x_title`, its x values mix "10 €" and "12 %", or a `bubble` point has `size: 0`
- **THEN** `needs_revision` says, respectively, a radar needs 3 to 8 criteria (or `column`/`bar`), a scatter takes points (`line` or `column` for categories), what the horizontal axis measures, the x values mix units, a bubble needs a positive size

#### Scenario: Radar mixing scales

- **WHEN** a `radar` without `unit` has values from 2 to 900
- **THEN** the call is refused once asking whether the values measure the same thing

#### Scenario: Points are sourced figures

- **WHEN** a `scatter` slide carries no `source`
- **THEN** `needs_revision` asks for the source of the slide's figures

### Requirement: Template slides with several charts are filled

The system SHALL treat every chart frame of a template slide that is not grouped, not declared `keep` and covers at least 5 % of the slide as a chart zone, up to four per slide, in reading order (top to bottom, then left to right), offered with its count (`charts×2`); a slide still holding another chart stays excluded with its reason. The plan SHALL accept `charts` beside `chart` (both on one slide is a `needs_revision`); a slide with k charts SHALL be built only on a template slide with exactly k zones, the i-th chart in the i-th zone, else refused naming the counts offered and how to reach one. Each chart SHALL follow every chart rule on its own frame, problems naming `charts[i]`; on a multi-chart slide each chart SHALL have a title, with one takeaway and one source for the slide. Edits address `charts[i]`; changing the count moves the slide or is refused.

#### Scenario: Four small charts are offered

- **WHEN** a template slide holds four chart frames of 9.3 % of the slide each in a two-by-two grid, or one of 3 % not `keep`
- **THEN** the first is kept with four zones ordered top-left, top-right, bottom-left, bottom-right, not excluded as `unsupported_parts`; the second stays excluded

#### Scenario: No slide with that many charts

- **WHEN** a slide has three charts and the template offers one, two and four
- **THEN** no deck is built and `needs_revision` says the template offers 1, 2 or 4 charts per slide and suggests splitting the slide or merging charts

#### Scenario: Untitled chart among several

- **WHEN** a slide with two charts has a chart without `title`
- **THEN** `needs_revision` asks what that chart shows, naming `charts[i]`

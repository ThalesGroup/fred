---
title: Prepare your PowerPoint template
order: 40
description: What makes a good template for generated presentations, and how to make the agent understand it.
icon: slideshow
---

# Prepare your PowerPoint template

This page is for whoever designs a team's template and whoever uploads it on an
agent (the **Generate a presentation** capability, see
[Capabilities](/help/en/features/capabilities)).

The agent draws nothing: it **copies the slides of your template** and replaces
their text. The quality of the presentations therefore depends directly on the
template. The rules below follow what reading the template really does.

## How the template is read

After the agent is saved, the template is read once, in the background. For
each slide, this reading finds the areas to fill, measures the room each one
offers and recognises what the slide is for (its **kind**: cover, agenda,
cards…).

- **Example slides first.** The slides in the file are what the agent reuses,
  with all their decoration. **Layouts** are only a last resort, when no slide
  fits. A slide that simply repeats its layout replaces it.
- **The vision model**, when switched on, looks at a picture of each example
  slide: it names it, picks its kind and understands what each area holds. It
  may also judge a slide to be a one-off (a specific org chart, a legal
  notice): the agent then does not reuse it. It never decides how much room
  there is: that is measured. Without a vision model, rules do this work, with
  less precise names.

## One slide per design

Put each design in **only once**, filled with sample text. A second copy of
the same design adds nothing. On the other hand, several variants of one kind
(three cards, four cards, cards with icons) give the agent room to vary its
presentations.

## Recognised kinds

The word in brackets is the one to write in a note (see below).

| Kind                          | What the slide must hold                            |
| ----------------------------- | --------------------------------------------------- |
| Cover (`cover`)               | A title. Always first in the presentation           |
| Agenda (`agenda`)             | Repeated entries (number and heading)               |
| Section (`section`)           | A title                                             |
| Bullet points (`bullets`)     | A title and a text area                             |
| Two columns (`two_columns`)   | Two text areas                                      |
| Comparison (`comparison`)     | Two or more text areas, side by side                |
| Cards (`cards`)               | Repeated items, each with a heading and a text      |
| Key figures (`figures`)       | Repeated items with a number                        |
| Process (`process`)           | Repeated steps                                      |
| Timeline (`timeline`)         | Repeated milestones                                 |
| Team (`team`)                 | Repeated people (name, role)                        |
| Quote (`quote`)               | The quote and its author                            |
| Image and text (`image_text`) | A picture and a text besides the title              |
| Table (`table`)               | A table to fill                                     |
| Chart (`chart`)               | A chart area, or one to four charts on the slide    |
| Closing (`closing`)           | Thanks or contacts. Always last in the presentation |
| Other (`other`)               | The agent does not use it                           |

The first slide of the file, when it has a title and no body text, is read as
the cover.

## Tell the agent what a slide is

Three ways, strongest first:

1. **A note.** In the slide's notes, each on its own line: `kind: cards` for
   the kind, `label: Three icon cards` for the name. What a note says is never
   replaced by the vision model.
2. **A telling title or name.** A short title, the layout name or a shape name
   stating the kind is recognised: "Agenda", "Table of contents", "Timeline",
   "Roadmap", "Process", "Steps", "Key figures", "KPI", "Team", "Quote",
   "Section", "Thank you", "Contact"…
3. **Shape names.** In PowerPoint's Selection pane, name a shape after its
   role: `title`, `subtitle`, `body` or `text`, `heading`, `caption`, `number`
   or `value`, `label`, `image` or `picture`. `keep` or `static` leaves a shape
   as it is. A suffix is allowed after `_` or `-` (`text_left`). Automatic
   names ("TextBox 12") say nothing.

## Repeated items

Cards, steps, key figures, agenda entries: the agent recognises them when they
are built identically.

- **Group each item** (its texts, its icon) and place at least three groups of
  the same structure: same font sizes, same number of pictures.
- **Or align identical text boxes**: three side by side, or two with a second
  row aligned under them (the number above its label). Same size, same font,
  same weight.
- A box wider than a third of the slide, or taller than 40 % of it, is read
  as a column, not an item.
- **Provide the maximum number of items**: the agent removes the extra ones and
  recentres the others, it never adds any.
- Icons stay the template's own; an icon goes with its item, and so do the
  card, tile or dot drawn for it, even on the layout.
- A key figure can show a small up, down or level arrow before its number, in
  the number's own font and colour: there is nothing to prepare.

## Leave room for the text

Each area's room is measured from its size, margins, font and line spacing.
The agent is told ("about 40 characters over 3 lines") and writes to that
size.

- **A box fitted to two words gets two words.** Size each box for the text you
  really expect.
- **Write realistic sample text**, at its final size: it refines the
  measurement. Vary it from one slide to the next.
- Text repeated on several slides (footer, confidentiality notice), the date
  and the slide number are never filled.

## Pictures

- A picture area is a picture placeholder, a picture covering at least a
  quarter of the slide, or a picture named `image` or `picture`. Smaller
  pictures (logos, icons) are decoration.
- A slide with picture areas is only picked when the agent has a picture for
  each: otherwise the area would stay empty.

## Tables

A table is filled when it is a real data table:

- one table per slide, covering a good part of it, with at least two columns;
- **no merged cells**;
- empty or sample-text cells, with no colour that changes from cell to cell
  (let the table style do the colouring).

The number of rows shown sets what the table can hold. The agent may remove
columns (it keeps at least two) and add or remove rows within the table's
height.

A total line and a row or column to point out also follow the table style:
the style's own look for a total line (bold where it has none), and bold text
on a light shade of the style's colour for the row or column. Choose a table
style that shows a total line if your tables often end with one.

## Charts

The agent turns the numbers of a request into a real PowerPoint chart (bars,
columns, lines, pie, doughnut, stacked columns or bars, areas, radar, and
scatter or bubble charts that relate two or three measures), which stays
editable in PowerPoint.

- **Offer a chart slide**: a layout with a chart placeholder, or an example
  slide holding one chart over a good part of it. A text area beside the chart
  takes a short comment; add a second chart slide without that area for charts
  that need no comment.
- **The template decides the look**: the chart takes the theme's accent
  colours, in order, and its body font. To change the colours of every chart,
  change the theme's accent colours. If your example chart is already the type
  requested (say, a bar chart for a bar chart), its own formatting is kept;
  otherwise the chart is rebuilt in the template's look.
- **Several charts side by side**: an example slide may hold two, three or
  four charts, each covering at least a twentieth of the slide. The agent fills
  every one of them, left to right then top to bottom, and uses that slide only
  when it has exactly as many charts to show; each chart gets its own title. A
  text box placed right above a chart shows that chart's title. Offer one
  example slide for each number of charts you want; for any other number, the
  agent splits its charts over several slides or groups them.
- Without a chart slide, a large content area (the one PowerPoint's "Title and
  Content" layout offers) takes the chart when the slide has no other text.
- The agent never draws a chart elsewhere, and asks for fewer categories or
  shorter labels rather than squeeze them.

## Key messages on the slides

Each slide's key message, what the audience should remember, goes in the
speaker notes. The slide delivers it through what it shows: when you change
a slide's key message, the agent rewrites that slide's content to convey it,
without displaying the message itself. To let the agent also show it on the slide when someone asks
for it ("show the key messages on the slides"), name the text area meant for
it `takeaway` or `key message` in PowerPoint's Selection pane, or on its
layout. Without such a request, that area stays empty, unless it is the
slide's only text area. With it, the agent prefers a slide that has such an
area. A key message that cannot be shown, too long for the area or on a slide
without one, stays in the speaker notes, and **What was built** says so.

An area left empty is removed. If a card is drawn behind it, give the area
itself that fill rather than drawing the card as a separate shape: the card
then goes with the empty area.

## What is set aside

These slides stay visible in **Review slides**, with the reason:

| Reason shown     | What causes it                                                                                                                     |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Chart            | More than four charts share the slide, or a chart inside a group                                                                   |
| Table            | A table that is not a data table (merged cells, per-cell colours)                                                                  |
| Resource sheet   | A page of resources, not content: twenty or so small pictures or many shapes with no text, or a title such as "Fonts" or "Palette" |
| Icon bank        | A page of icons set aside by an earlier reading of the template; once the template is read again, it shows as Resource sheet       |
| Cannot be copied | A SmartArt, a very small chart or an embedded object (Excel…)                                                                      |
| No placeholder   | A layout with nothing to fill                                                                                                      |
| Excluded by you  | You set it aside                                                                                                                   |

A SmartArt can be converted to shapes in PowerPoint: the slide then becomes
usable.

## Check the result

**Review slides** shows the slides kept, the layouts and the slides set aside.
You can rename a slide (its name helps the agent choose), change its kind, set
it aside or bring it back. Giving another kind to an Other slide lets the agent
use it, as a `kind:` note does. The **Named by rules** mark flags a slide the vision
model did not read.

## After changing the template

Upload the changed file and save the agent: the template is read again in
full, and the agent stays unavailable meanwhile. Uploading the same file again
keeps the previous reading. Switching the vision model on or off, or changing
it, also reads the template again. Corrections made in **Review slides** are
kept only for slides still present; notes and shape names travel with the
file.

## Summary

| Do                                             | Avoid                                |
| ---------------------------------------------- | ------------------------------------ |
| One example slide per design                   | Several copies of the same design    |
| A `kind:` note when the kind is not obvious    | Leaving slides as Other              |
| Repeated items grouped or aligned identically  | Cards of different sizes or fonts    |
| The maximum number of items you want to see    | Counting on the agent to add a card  |
| Text boxes sized for the expected text         | Boxes fitted to two words            |
| Realistic sample text, different on each slide | The same sample text everywhere      |
| Simple tables, no merges or per-cell colours   | A schedule drawn with coloured cells |
| SmartArt converted to shapes                   | Embedded objects to fill             |
| Up to four charts per slide, each large enough | Five charts or more on one slide     |

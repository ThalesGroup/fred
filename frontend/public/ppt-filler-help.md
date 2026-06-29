# PowerPoint template — how it works

This capability lets an agent fill in a fill-in-the-blanks PowerPoint, based on instructions and files made available to it. It is useful when you have a fixed PowerPoint format to reproduce regularly while changing only the content.

![Two PowerPoints: an input one with template tags, and another filled in by an agent (the result).](/ppt-filler/introduction.png)

## How to create a PowerPoint template

For your agent to fill in your PowerPoint, you need to identify each area it will have to complete and associate a description with it.

### 1. Mark the areas to fill in

In a text box, write a **key** between double curly braces where a value should appear:

```
{{name}}
```

You can reuse the same key several times on a slide to repeat the same value. The same key on another slide is independent.

### 2. Describe each key in the notes

In the slide's **notes** (View → Notes), write for each key a header line `{{key}}:` followed by a description. It tells the agent what to put in that spot:

```
{{name}}:
Name of the employee, to be found in the CV.
```

A line is a header only if it consists of one or more `{{key}}` keys ending with a colon. A key quoted in the middle of a sentence stays ordinary text — so you can write naturally.

![A slide with keys between double curly braces in its text boxes, and the slide notes describing each key.](/ppt-filler/template.png)

## Advanced usage

### Multi-line description

A description runs from its header to the next header (or the end of the notes): it can therefore span several lines, including blank lines.

```
{{context}}:
The business context of the engagement.

Mention the client's sector and its main constraints.

{{objectives}}:
The objectives of the engagement, as a bulleted list.

Three to five points maximum, phrased for a business audience.
```

### Assigning one description to several keys

List several keys separated by commas on the header line to give them the same description. This is useful when a slide repeats the same structure several times — for example a CV with three sections describing the last three experiences, each with a title and a description:

```
{{titleExperience1}}, {{titleExperience2}}, {{titleExperience3}}:
The job title and company, from most recent to oldest.

{{descriptionExperience1}}, {{descriptionExperience2}}, {{descriptionExperience3}}:
A summary of the assignments and achievements, in the same order as the titles.
```

### Keeping real presenter notes

By default, your `{{key}}:` descriptions are configuration instructions and are removed from the generated presentation. To keep real presenter notes, add a line of at least **three dashes**: everything below it is kept as-is in the result.

```
{{mission}}:
A one-sentence summary of the engagement.

---
Note to presenter: keep this slide under two minutes.
```

## Adding images

A key can also be filled with an **image** instead of text. The agent picks a picture from a folder of your resources and places it in your slide.

### 1. Mark the image spot

Draw a shape — a rectangle or a text box — where the image should appear, and write a `{{key}}` as its text. The shape's position and size become the image's placement box.

```
{{countryFlag}}
```

### 2. Declare it as an image in the notes

Under the key's header in the notes, add a metadata block: one `- type:` / `- folder:` line per setting, directly below the header and before the description.

```
{{countryFlag}}:
- type: image
- folder: "images/flags"
Pick the flag matching the country discussed.
```

- `type: image` tells the agent to place a picture. The default is `text`, so ordinary keys need nothing.
- `folder:` points at a folder of your uploaded resources — your personal space or your team's. Quotes are optional, and keywords and values are case-insensitive.

### Offering several image slots

A multi-key header shares one folder and one piece of guidance — handy for offering several slots configured once:

```
{{logo1}}, {{logo2}}, {{logo3}}:
- type: image
- folder: "images/partner-logos"
Add the logos of the partners mentioned, most prominent first.
```

You can offer N image slots and tell the agent (in the description) to use only the ones that fit. **Unused image slots are removed** — the deck shows no empty box. (Omitted text keys still become empty text, as before.)

### Good to know

- The image is scaled to **fit inside** the shape's box, with its aspect ratio preserved and centered — no distortion and no cropping.
- A repeated image key (the same key in several shapes on one slide) gets the same image in every shape, just like repeated text keys.
- Real presenter notes after the `---` separator are left untouched.
- The folder must be a real folder in your space. It is checked when you pick the template and again when you save.

## Errors

When you upload a PowerPoint template, it is analyzed immediately. As long as an error remains, the agent cannot be saved. These cases can occur:

- **A key without a description** — a `{{key}}` appears in a text box but is not described in the slide's notes -> Add the missing description in the notes.
- **A description for a missing key** — the notes describe a `{{key}}` that does not appear in any text box on the slide -> Fix the typo, remove the outdated description, or add the missing key to the slide.
- **An unknown metadata keyword** — a metadata line uses a keyword other than `type` or `folder` -> Fix the typo; only `type` and `folder` are recognized.
- **An unknown type** — a `type:` value is neither `text` nor `image` -> Use one of those two values.
- **Duplicated metadata** — the same metadata keyword appears twice in one key's block -> Remove the duplicate line.
- **An image without a folder** — a key is `type: image` but has no folder -> Add a `- folder: "..."` line pointing at your resources.
- **An empty folder** — a `folder:` line is blank -> Fill in the folder path.
- **A folder on a non-image key** — a `folder:` is set on a key that is not an image -> Either add `- type: image`, or remove the folder line.
- **A folder that does not exist** — the named folder is not found in your space (personal or team) -> Fix the name, or create the folder and upload to it.
- **An image key in an invalid location** — an image key sits somewhere that cannot hold a picture, such as a table cell -> Move it into a text box or a rectangle.

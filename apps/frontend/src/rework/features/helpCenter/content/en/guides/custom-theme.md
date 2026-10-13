---
title: Create a custom theme
order: 30
description: Add a theme in your organization's colors without touching the others.
icon: tune
---

# Create a custom theme

A custom theme joins Pebble, Cobalt and Cloud: users pick it in their profile,
and a **Platform admin** can make it the default theme. It ships in a ZIP
archive that the team deploying the application installs with the frontend.

> This guide is for whoever prepares the ZIP. Deploying it (step 5) needs
> access to the archive's storage; choosing the offered themes (step 6) happens
> in the administration console.

## What the archive contains

```
theme.zip
|-- theme-catalog.json          the themes to add
|-- themes/
|   `-- acme/
|       |-- theme-custom.css    Acme colors, fonts and shapes
|       `-- images/             Acme icons and illustrations
`-- shared/                     content used by every theme
    |-- images/                 shared logos and fonts
    |-- theme-properties.json
    `-- theme-translations/
```

A ZIP made from a folder (`zip -r theme.zip my-theme/`) is accepted: the
wrapper folder is skipped. Older flat ZIPs still work. Image names must be
unique across theme folders and `shared/images/`.

## 1. Declare the theme

`theme-catalog.json` lists the added themes (at most 16):

```json
{
  "themes": [
    {
      "id": "acme",
      "label": "Acme",
      "base": "pebble",
      "tabTitle": "Acme Portal",
      "faviconName": "acme-favicon-light",
      "faviconNameDark": "acme-favicon-dark"
    }
  ]
}
```

| Field             | Purpose                                                             |
| ----------------- | ------------------------------------------------------------------- |
| `id`              | Unique identifier, lowercase, at most 32 characters.                |
| `label`           | Name shown in the profile and in administration.                    |
| `base`            | `pebble`, `cobalt` or `cloud`: the theme it inherits the rest from. |
| `tabTitle`        | Optional. Browser tab title while this theme is active.             |
| `faviconName`     | Optional. Tab icon in light mode.                                   |
| `faviconNameDark` | Optional. Icon in dark mode; defaults to the light one.             |

Icons are SVG files in `images/`, given **without** the `.svg` extension.
Without these fields the tab keeps its usual title and icon. Switching to
another theme also gives the tab its own back.

## 2. Colors, fonts and shapes

`themes/<id>/theme-custom.css` holds only the differences from the base theme. Each rule
targets the theme by its `id` **and** its base, with no `html` prefix:

```css
[data-ui-theme="acme"][data-ui-base-theme="pebble"][data-theme="light"] {
  --primary: #0b6e4f;
  --on-primary: #ffffff;
}

[data-ui-theme="acme"][data-ui-base-theme="pebble"][data-theme="dark"] {
  --primary: #ffffff;
  --on-primary: #0b6e4f;
}
```

The base in the selector makes your rules win over the shipped theme; leaving
out `html` lets the administration previews show them. Colors always
need all three attributes, even to adjust Pebble, Cobalt or Cloud themselves. A
rule without `[data-theme]` applies to both modes, for instance for the font:

```css
@font-face {
  src: url("/images/fonts/MyFont.ttf") format("truetype");
  font-family: "My font";
}

[data-ui-theme="acme"][data-ui-base-theme="pebble"] {
  --font-family-base: "My font", Arial, sans-serif;
}
```

## 3. Theme-specific images

Files in `themes/<id>/images/` are served at `/images/` to everyone, but only your theme's CSS uses them.
For the chat background or the welcome agent's avatar, target
`[data-chat-main]`, `[data-chat-welcome-agent]` or `[data-chat-agent-icon]`
under `html[data-ui-theme="<id>"]`: other themes see none of it.

Browsers cache images. To change one, give the new file a **new name** rather
than overwriting the old one.

## 4. What every theme shares

Two optional files in the archive apply to **all** themes, Pebble, Cobalt and
Cloud included:

- `shared/theme-properties.json`: site name, logos, agent nicknames, default avatars,
  support link;
- `shared/theme-translations/en.json` and `fr.json`: the interface texts.

Any interface text can be renamed this way, and "Agents" through the agent
nicknames, but for the whole platform: two themes in the same archive cannot
have different texts.

For a theme that does not spill over the others, leave them out or neutral,
and carry the theme's identity through the catalog and the CSS.

## 5. Install the archive

Put the ZIP at the storage location configured for the frontend, then restart
the frontend: the archive is only read at startup. Users already connected get
the theme when they reload the page.

## 6. Offer the theme

In the administration console, the **User interface** page shows the new theme
next to the others, with its light and dark preview. Offer it to users, and
choose **Set as default** if everyone should get it until they pick another
one. See [Administration](/help/en/features/administration).

## If the theme does not show up

- **No added theme shows up**: the archive was refused. The frontend logs say
  so, for example
  `Theme skipped, serving the stock assets: invalid theme-catalog.json`. Check
  the catalog: an unknown field, an uppercase `id` or an icon name ending in
  `.svg` is enough to refuse it.
- **The tab keeps the old icon**: the SVG file is missing from `images/`, or the
  browser has it cached; rename it.
- **The theme is not in the profile**: it may be hidden on **User interface**.

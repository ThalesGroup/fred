# Third-party notices

## Geist

The optional `fonts.css` export redistributes these canonical FRED assets:

| FRED source                                         | SHA-256                                                            | Embedded version/style             |
| --------------------------------------------------- | ------------------------------------------------------------------ | ---------------------------------- |
| `apps/frontend/src/assets/fonts/Geist.woff2`        | `76cfe85ecc60501d14d0309e96875e736be40c80a8e8cd0746f3469bd44fc724` | Geist 1.800, Regular variable font |
| `apps/frontend/src/assets/fonts/Geist-Italic.woff2` | `bc44b49662a093f12418c30fc526ee7caa07a3fb438f1585f43ac12ef0566516` | Geist 1.800, Italic variable font  |

Both files identify their source in the embedded OpenType name table as:

> Copyright 2024 The Geist Project Authors
> (https://github.com/vercel/geist-font.git)

The same metadata identifies Basement.studio, Vercel, Andrés Briganti, Guido
Ferreyra, and Mateo Zaragoza, and declares the SIL Open Font License, Version
1.1. The official upstream project carries the same copyright and license in
the [OFL text at commit `10dc7658f13c38a474cde201bb09a4617267545b`](https://github.com/vercel/geist-font/blob/10dc7658f13c38a474cde201bb09a4617267545b/OFL.txt).

The complete license is distributed as `licenses/Geist-OFL-1.1.txt`. The build
checks both source hashes before copying the fonts so a changed binary requires
an explicit provenance and notice review.

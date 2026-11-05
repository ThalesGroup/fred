# Third-party fonts in the fred-agents image

Fred's own code is licensed under Apache 2.0. The following fonts are separate
Ubuntu packages in the agent image and retain their own licenses.

| Ubuntu package | Font used for | License |
| --- | --- | --- |
| `fonts-liberation2` | Arial-compatible rendering | SIL Open Font License 1.1 |
| `fonts-crosextra-carlito` | Calibri-compatible rendering | SIL Open Font License 1.1 |
| `fonts-crosextra-caladea` | Cambria-compatible rendering | SIL Open Font License 1.1 |
| `fonts-urw-base35` | URW Gothic substitute for Century Gothic | GNU AGPL 3 with a PostScript/PDF font exception |

The copyright notices and full license terms shipped with each package are in
`/usr/share/doc/<package>/copyright` inside the image. In particular,
`/usr/share/doc/fonts-urw-base35/copyright` contains the AGPL 3 text and the
font exception. The Fontconfig alias does not modify the font files.

To obtain the corresponding source for the installed URW package, first read
its version with `dpkg-query -W -f='${Version}\n' fonts-urw-base35` inside the
image. Download the matching source package files (`.dsc`, original tarball and
Debian packaging tarball) from the [Ubuntu source archive](https://archive.ubuntu.com/ubuntu/pool/main/f/fonts-urw-base35/).
The matching source must remain available while the image is distributed. The image
build checks that the installed notices are present, and CI retains a license
report and SBOM for this image.

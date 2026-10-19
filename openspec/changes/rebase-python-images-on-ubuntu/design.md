## Context

The three Python images used the official `python:slim` image, whose default variant is Debian 13. LibreOffice, which fred-agents and Knowledge Flow need for document conversion, brings most of the findings. Stripping unused base packages on Debian was measured at 67 -> 37 HIGH. Ubuntu 24.04 + LibreOffice measured 0 HIGH and 0 CRITICAL.

## Decisions

- **Ubuntu 24.04 LTS, not Alpine or Wolfi.** Alpine uses musl, which the ML wheels (torch, Docling, Paddle) do not reliably support. Wolfi is a rolling distribution: its packages would have to be pinned to get reproducible builds. Ubuntu keeps apt, glibc 2.39 and the same package names.
- **CPython from uv, not the distribution's `python3.12`.**
  - This keeps 3.12.15, whereas noble ships 3.12.3 with security-only backports.
  - The install happens in a throwaway stage. Builder and final stages copy `/opt/python` and expose it as `/usr/local/bin/python3`, because the venv records that path as its home.
  - The installed pip is removed from the base interpreter. Building the venv only needs the bundled ensurepip wheel.
- **Same base packages as `python:slim`.** `ca-certificates`, `netbase` and `tzdata` are installed explicitly, because the bare Ubuntu image lacks them.
- **UID 1000.** `ubuntu:24.04` ships a `ubuntu` user with UID/GID 1000. It is deleted so that `fred-user` keeps its identifiers and the chart's `runAsUser: 1000` still holds.
- **Knowledge Flow builder.** The global uv installed by `install.sh` is removed: `make prod` only uses the venv's own uv.

## Risks

- **OpenSSL, SQLite and expat are bundled statically** in the standalone CPython build. Trivy does not report them, and their fixes arrive by bumping uv or `PYTHON_VERSION`, not through apt.
- **LibreOffice goes from 25.2 to 24.2.** Conversion output has to be revalidated.
- **`pandoc`, `inkscape` and `ffmpeg` are universe sources on Ubuntu**, with community security maintenance only. The LibreOffice `-nogui` binaries are tagged universe but build from the main `libreoffice` source, so Canonical's updates rebuild them.

## Deferred

- The frontend nginx Alpine image, which is already near zero.
- The Knowledge Flow executable removals tracked in #3161.

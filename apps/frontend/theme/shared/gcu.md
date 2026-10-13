# THEME OVERRIDE TEST - these are not real terms of use

**If you are reading this page, the theme overlay works.** This text is served
from a theme archive in object storage, not from the frontend image. Nothing
was rebuilt and nothing was forked to put it here.

What happened, in order:

1. The container started and fetched the archive from `FRONTEND_THEME_URL`.
2. It unpacked `gcu.md` into the overlay directory, outside the web root.
3. nginx now serves that file instead of the one baked into the image.

**Replace this file before any real user sees it.** It lives in
`apps/frontend/theme/gcu.md` and exists only so the archive is complete and
the override is verifiable end to end.

Keep `gcu.fr.md` beside it. The application asks for `gcu.<lang>.md` first, and
the stock image ships a French one, so an English-only override silently loses
to the built-in text for a French reader - with the theme still reported as
installed.

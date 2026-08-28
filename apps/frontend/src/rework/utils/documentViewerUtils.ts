import { getConfig } from "../../common/config";
import type { VectorSearchHit } from "../../slices/runtime/runtimeOpenApi";

type DocumentViewerSource = Pick<VectorSearchHit, "uid"> &
  Partial<Pick<VectorSearchHit, "title" | "file_name" | "author" | "repository">>;

/**
 * Decode a markdown preview payload that may be plain text or base64-encoded UTF-8.
 *
 * Why this function exists:
 * - knowledge-flow preview responses may arrive as base64 while the UI still needs
 *   to render readable Unicode text in the document viewer
 * - raw `atob()` corrupts non-ASCII content, so the decode must round-trip UTF-8 safely
 *
 * How to use it:
 * - pass the raw API `content` field before storing it in UI state
 * - if the input is not valid base64, the original string is returned unchanged
 *
 * Example:
 * - `setContent(decodeMaybeBase64Utf8(resp?.content ?? ""));`
 */
export function decodeMaybeBase64Utf8(value: string): string {
  try {
    const binary = atob(value);
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return value;
  }
}

/**
 * Extract the first H1 line from markdown to use as a fallback document title.
 *
 * Why this function exists:
 * - citation-opened documents may not provide a complete title in query params
 * - the viewer still needs a stable human-readable heading when metadata is sparse
 *
 * How to use it:
 * - pass the decoded markdown body after loading succeeds
 * - use the returned value only as a fallback after explicit metadata
 *
 * Example:
 * - `const title = paramTitle ?? extractH1(markdown) ?? uid;`
 */
export function extractH1(markdown: string): string | null {
  const match = /^#\s+(.+)$/m.exec(markdown);
  return match?.[1]?.trim() ?? null;
}

/**
 * Whether a file name denotes a PDF, for choosing a DocumentViewer render strategy.
 *
 * Why this function exists:
 * - `DocumentViewer` picks native PDF rendering vs. markdown extraction purely from
 *   the file's extension — the one signal available at both call sites (chat
 *   citation query params, corpus document metadata)
 *
 * How to use it:
 * - pass the document's real file name (with extension), not its display title
 *
 * Example:
 * - `isPdfFile(doc.identity.document_name) // true for "report.pdf"`
 */
export function isPdfFile(fileName: string | null | undefined): boolean {
  return !!fileName && fileName.toLowerCase().endsWith(".pdf");
}

/**
 * Whether a file name has a native (non-markdown) renderer in the document viewer.
 *
 * Why this function exists:
 * - the preview offers a markdown/original toggle, but that toggle is only meaningful
 *   when the two modes actually differ. A `.docx`/`.csv` has no native renderer — it is
 *   ALREADY shown as its markdown extraction — so a toggle there would be inert
 * - keeping the predicate here (rather than re-testing `.pdf` at each host) means a
 *   future native renderer (docx, images) lights the toggle up everywhere at once
 *
 * How to use it:
 * - pass the document's real file name (with extension); gate the toggle affordance on it
 *
 * Example:
 * - `hasNativePreview("facture.pdf") // true — offer the "view as markdown" button`
 */
export function hasNativePreview(fileName: string | null | undefined): boolean {
  return isPdfFile(fileName);
}

/**
 * Whether a file name denotes tabular data, for widening its markdown-table preview.
 *
 * Why this function exists:
 * - CSV/TSV previews render as a markdown table with no dedicated tabular component
 *   (see MarkdownRenderer.module.css); the default 65ch prose column is too narrow
 *   for a wide dataset, unlike genuine prose documents which want that reading width
 *
 * How to use it:
 * - pass the document's real file name (with extension) to decide whether
 *   `MarkdownRenderer`'s `fullWidth` variant should be used instead of the prose cap
 *
 * Example:
 * - `isTabularFile("ship_tracks_enriched.csv") // true`
 */
export function isTabularFile(fileName: string | null | undefined): boolean {
  if (!fileName) return false;
  const lower = fileName.toLowerCase();
  return lower.endsWith(".csv") || lower.endsWith(".tsv");
}

/**
 * Strip the React Router basename down to a prefix that concatenates cleanly.
 *
 * Why this function exists:
 * - links built outside the router (a plain anchor, a URL mailed to someone)
 *   do not inherit the basename, so they must prepend it by hand
 * - "/" and a trailing slash both have to collapse to "" / no trailing slash,
 *   otherwise the concatenated path doubles the separator
 *
 * How to use it:
 * - `${normalizeBasename(getConfig().frontend_basename)}/team/${id}/agents`
 */
export function normalizeBasename(basename: string): string {
  if (basename === "/") return "";
  return basename.endsWith("/") ? basename.slice(0, -1) : basename;
}

/**
 * Build a basename-aware internal route to the rework document viewer.
 *
 * Why this function exists:
 * - source citations open documents in a new tab via a plain anchor, which does not
 *   automatically inherit the React Router basename
 * - the path must keep working when the frontend is deployed under a subpath
 *
 * How to use it:
 * - pass the source hit that originated from a citation and the configured frontend basename
 * - use the returned string as the anchor `href` for internal document links
 *
 * Example:
 * - `const href = buildDocumentViewerPath(source, getConfig().frontend_basename);`
 */
export function buildDocumentViewerPath(
  source: DocumentViewerSource,
  basename = getConfig().frontend_basename,
): string {
  const params = new URLSearchParams();
  if (source.title) params.set("title", source.title);
  if (source.file_name) params.set("file", source.file_name);
  if (source.author) params.set("author", source.author);
  if (source.repository) params.set("repo", source.repository);

  const query = params.toString();
  const base = normalizeBasename(basename);
  const path = `${base}/documents/${encodeURIComponent(source.uid)}`;
  return query ? `${path}?${query}` : path;
}

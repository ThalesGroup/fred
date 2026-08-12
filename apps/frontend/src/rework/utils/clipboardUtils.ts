// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * Clipboard serialisation for assistant message content (#2336).
 *
 * The browser's default copy behaviour inlines each selected node's *computed*
 * style into the `text/html` clipboard flavour — which is how the message
 * surface's background-color ended up pasted into Outlook/Notes as a pink or
 * near-black highlight. Rather than chase every future `background` added to
 * a table cell or code block, these serialisers build the clipboard payload
 * themselves from a plain allowlist of tags: only the mapping below ever
 * emits a wrapper element, so no attribute or style from the source DOM can
 * leak through except the explicitly-validated `href`/`src`.
 *
 * `toEmailHtml` targets Outlook's Word rendering engine specifically: inline
 * styles only, sizes in `pt`, no font-family/color/background overrides so
 * pasted text inherits the destination document's typography.
 */

const IGNORE_ATTR = "data-clipboard-ignore";
const NEUTRAL_BORDER = "#cccccc";
const HEADING_SIZE_PT: Record<string, number> = { h1: 13, h2: 13, h3: 12, h4: 11, h5: 11, h6: 11 };

function isElement(node: Node): node is Element {
  return node.nodeType === Node.ELEMENT_NODE;
}

function isIgnored(el: Element): boolean {
  return el.hasAttribute(IGNORE_ATTR);
}

function isDiagramNode(el: Element): boolean {
  // SVG is a foreign namespace: unlike HTML elements, its tagName keeps the
  // author's original case ("svg", not "SVG") — compare case-insensitively.
  const tag = el.tagName.toUpperCase();
  return tag === "SVG" || tag === "CANVAS";
}

function diagramPlaceholder(el: Element): string {
  const label = el.getAttribute("aria-label") || el.querySelector("title")?.textContent;
  return label ? `[diagram: ${label}]` : "[diagram]";
}

/** SyntaxHighlighter nests one <span> per token; textContent flattens them back to source. */
function codeText(el: Element): string {
  return el.textContent ?? "";
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

const ABSOLUTE_URL = /^[a-z][a-z0-9+.-]*:/i;

function safeHref(href: string | null): string | null {
  if (!href) return null;
  try {
    const url = new URL(href, window.location.href);
    if (url.protocol !== "http:" && url.protocol !== "https:" && url.protocol !== "mailto:") return null;
    // Resolve a relative href to absolute, but keep an already-absolute one
    // exactly as authored — new URL() normalizes e.g. a bare origin by
    // appending "/", which would make toPlainText's same-URL label collapse
    // (below) miss a match that's obviously the same link to a human.
    return ABSOLUTE_URL.test(href) ? href : url.href;
  } catch {
    return null;
  }
}

function safeImgSrc(src: string | null): string | null {
  if (!src) return null;
  if (src.startsWith("data:image/")) return src;
  try {
    const url = new URL(src, window.location.href);
    return url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

// ---- Email-safe HTML ----

function renderChildrenHtml(node: Node): string {
  let out = "";
  node.childNodes.forEach((child) => {
    out += renderNodeHtml(child);
  });
  return out;
}

function renderTableHtml(table: Element): string {
  const rows = Array.from(table.querySelectorAll("tr"))
    .map((row) => {
      const cells = Array.from(row.children)
        .filter((c) => c.tagName === "TH" || c.tagName === "TD")
        .map((cell) => {
          const tag = cell.tagName.toLowerCase();
          const weight = tag === "th" ? "font-weight:600; " : "";
          return `<${tag} style="border:1pt solid ${NEUTRAL_BORDER}; text-align:left; vertical-align:top; ${weight}padding:4pt 8pt">${renderChildrenHtml(cell)}</${tag}>`;
        })
        .join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");
  return `<table cellpadding="6" cellspacing="0" style="border-collapse:collapse; margin:0 0 10pt">${rows}</table>`;
}

function renderNodeHtml(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) return escapeHtml(node.textContent ?? "");
  if (!isElement(node)) return "";
  if (isIgnored(node)) return "";
  if (isDiagramNode(node)) return escapeHtml(diagramPlaceholder(node));

  const tag = node.tagName.toLowerCase();
  switch (tag) {
    case "h1":
    case "h2":
    case "h3":
    case "h4":
    case "h5":
    case "h6":
      return `<p style="margin:14pt 0 6pt"><strong style="font-size:${HEADING_SIZE_PT[tag]}pt">${renderChildrenHtml(node)}</strong></p>`;
    case "p":
      return `<p style="margin:0 0 10pt">${renderChildrenHtml(node)}</p>`;
    case "ul":
      return `<ul style="margin:0 0 10pt; padding-left:20pt">${renderChildrenHtml(node)}</ul>`;
    case "ol":
      return `<ol style="margin:0 0 10pt; padding-left:20pt">${renderChildrenHtml(node)}</ol>`;
    case "li":
      return `<li style="margin:0 0 4pt">${renderChildrenHtml(node)}</li>`;
    case "strong":
    case "b":
      return `<strong>${renderChildrenHtml(node)}</strong>`;
    case "em":
    case "i":
      return `<em>${renderChildrenHtml(node)}</em>`;
    case "a": {
      const href = safeHref(node.getAttribute("href"));
      const inner = renderChildrenHtml(node);
      return href ? `<a href="${escapeHtml(href)}">${inner}</a>` : inner;
    }
    case "pre":
      return `<pre style="font-family:Consolas,'Courier New',monospace; font-size:9.5pt; margin:0 0 10pt; padding:8pt; border:1pt solid ${NEUTRAL_BORDER}; white-space:pre-wrap">${escapeHtml(codeText(node))}</pre>`;
    case "code":
      return `<span style="font-family:Consolas,'Courier New',monospace; font-size:10pt">${escapeHtml(codeText(node))}</span>`;
    case "blockquote":
      return `<blockquote style="margin:0 0 10pt 12pt; padding-left:10pt; border-left:2pt solid ${NEUTRAL_BORDER}">${renderChildrenHtml(node)}</blockquote>`;
    case "table":
      return renderTableHtml(node);
    case "hr":
      return `<hr style="border:none; border-top:1pt solid ${NEUTRAL_BORDER}; margin:12pt 0">`;
    case "img": {
      const src = safeImgSrc(node.getAttribute("src"));
      if (!src) return "";
      const alt = escapeHtml(node.getAttribute("alt") ?? "");
      return `<img src="${escapeHtml(src)}" alt="${alt}" width="600" style="max-width:600px; height:auto">`;
    }
    case "br":
      return "<br>";
    default:
      // Unknown/structural wrapper (e.g. a component's own <div>) — keep the
      // content, drop the element itself.
      return renderChildrenHtml(node);
  }
}

/** DOM fragment (a selection, a whole message) → email-safe HTML for Outlook/Word. */
export function toEmailHtml(source: DocumentFragment | HTMLElement): string {
  return renderChildrenHtml(source).trim();
}

// ---- Plain text ----

function collapseBlankLines(text: string): string {
  // Only strip *blank* leading/trailing lines — a plain .trim() would also
  // eat significant leading indentation (e.g. a code block's first line)
  // whenever it lands at the very start of the output.
  return text
    .replace(/\n{3,}/g, "\n\n")
    .replace(/^\n+/, "")
    .replace(/\s+$/, "");
}

function renderListPlain(list: Element, indent: number, ordered: boolean): string {
  const pad = "  ".repeat(indent);
  let index = 0;
  return Array.from(list.children)
    .filter((c) => c.tagName === "LI")
    .map((li) => {
      index += 1;
      const marker = ordered ? `${index}. ` : "- ";
      const nestedLists = Array.from(li.children).filter((c) => c.tagName === "UL" || c.tagName === "OL");
      const ownText = Array.from(li.childNodes)
        .filter((n) => !(isElement(n) && (n.tagName === "UL" || n.tagName === "OL")))
        .map((n) => renderNodePlain(n, indent))
        .join("")
        .trim();
      const nested = nestedLists.map((nl) => renderListPlain(nl, indent + 1, nl.tagName === "OL")).join("");
      return `${pad}${marker}${ownText}\n${nested}`;
    })
    .join("");
}

function tableToTsv(table: Element): string {
  return Array.from(table.querySelectorAll("tr"))
    .map((row) =>
      Array.from(row.children)
        .filter((c) => c.tagName === "TH" || c.tagName === "TD")
        .map((cell) => (cell.textContent ?? "").trim().replace(/\t/g, " "))
        .join("\t"),
    )
    .join("\n");
}

function renderChildrenPlain(node: Node, indent: number): string {
  let out = "";
  node.childNodes.forEach((child) => {
    out += renderNodePlain(child, indent);
  });
  return out;
}

function renderNodePlain(node: Node, indent: number): string {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent ?? "";
  if (!isElement(node)) return "";
  if (isIgnored(node)) return "";
  if (isDiagramNode(node)) return diagramPlaceholder(node);

  const tag = node.tagName.toLowerCase();
  switch (tag) {
    case "h1":
    case "h2":
    case "h3":
    case "h4":
    case "h5":
    case "h6":
      return `\n${renderChildrenPlain(node, indent).trim()}\n\n`;
    case "p":
      return `${renderChildrenPlain(node, indent)}\n\n`;
    case "ul":
      return `${renderListPlain(node, indent, false)}\n`;
    case "ol":
      return `${renderListPlain(node, indent, true)}\n`;
    case "blockquote":
      return (
        renderChildrenPlain(node, indent)
          .trim()
          .split("\n")
          .map((line) => `> ${line}`)
          .join("\n") + "\n\n"
      );
    case "pre":
      return `\n${codeText(node)}\n\n`;
    case "code":
      return codeText(node);
    case "a": {
      const href = safeHref(node.getAttribute("href"));
      const label = renderChildrenPlain(node, indent).trim();
      if (!href) return label;
      return label === href ? href : `${label} (${href})`;
    }
    case "table":
      return `${tableToTsv(node)}\n`;
    case "br":
      return "\n";
    case "hr":
      return "";
    default:
      return renderChildrenPlain(node, indent);
  }
}

/** DOM fragment → readable plain text (list markers preserved, tables as TSV). */
export function toPlainText(source: DocumentFragment | HTMLElement): string {
  return collapseBlankLines(renderChildrenPlain(source, 0));
}

// ---- Clipboard write ----

/**
 * Writes both flavours at once via the async Clipboard API, falling back to
 * plain text only when rich write is unavailable or rejected (e.g. non-secure
 * context on an on-prem HTTP deployment). Never throws.
 */
export async function writeRichClipboard(html: string, plain: string): Promise<boolean> {
  try {
    if (typeof ClipboardItem !== "undefined") {
      const items: Record<string, Blob> = { "text/plain": new Blob([plain], { type: "text/plain" }) };
      if (html) items["text/html"] = new Blob([html], { type: "text/html" });
      await navigator.clipboard.write([new ClipboardItem(items)]);
      return true;
    }
  } catch {
    // fall through to the plain-text-only path below
  }
  try {
    await navigator.clipboard.writeText(plain);
    return true;
  } catch {
    return false;
  }
}

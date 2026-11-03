// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import DOMPurify from "dompurify";
import { generate, parse, walk } from "css-tree";

/** Keep the view's CSS scope and inherited theme when the diagram leaves the page. */
export function serializeMermaidSvg(source: SVGSVGElement): string {
  const [, , width, height] = (source.getAttribute("viewBox") ?? "")
    .trim()
    .split(/[\s,]+/)
    .map(Number);
  if (!(width > 0 && height > 0 && Number.isFinite(width) && Number.isFinite(height)))
    throw new Error("Invalid diagram dimensions");

  const output = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  output.id = source.parentElement.id;
  output.setAttribute("width", String(width));
  output.setAttribute("height", String(height));
  output.setAttribute("viewBox", `0 0 ${width} ${height}`);
  const styles = getComputedStyle(source);
  output.style.fontFamily = styles.fontFamily;
  output.style.fontSize = styles.fontSize;
  output.style.color = styles.color;
  const snapshot = source.cloneNode(true) as SVGSVGElement;
  // XMLSerializer supplies namespace declarations from the DOM's actual namespaces.
  for (const element of [snapshot, ...snapshot.querySelectorAll("[xmlns]")]) element.removeAttribute("xmlns");
  // Only capture variables referenced by this diagram, not unrelated page styles.
  for (const [, variable] of source.outerHTML.matchAll(/var\(\s*(--[\w-]+)/g)) {
    const value = styles.getPropertyValue(variable).trim();
    if (value) output.style.setProperty(variable, value);
  }
  snapshot.setAttribute("width", String(width));
  snapshot.setAttribute("height", String(height));
  // A local fallback font can be wider when the file is opened without Fred's web fonts.
  snapshot.querySelectorAll<SVGElement>("foreignObject").forEach((label) => {
    label.style.overflow = "visible";
  });
  const background = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  background.setAttribute("width", String(width));
  background.setAttribute("height", String(height));
  background.setAttribute("fill", "#ffffff");
  output.append(background, snapshot);
  return new XMLSerializer().serializeToString(output);
}

/** Sanitize and scope a library SVG for one inline or enlarged view. */
export function prepareMermaidSvg(source: string, scope: string): string {
  const template = document.createElement("template");
  // Template contents are inert. Scope IDs before sanitizing so DOM clobbering
  // protection does not remove legitimate names such as "title" and break references.
  template.innerHTML = source;
  const svg = template.content.firstElementChild;
  if (svg?.localName !== "svg") throw new Error("Invalid diagram output");
  // Layout belongs to the viewer, not the renderer's inline size constraints.
  const svgStyle = (svg as SVGSVGElement).style;
  for (const property of ["width", "height", "max-width", "max-height", "min-width", "min-height"])
    svgStyle.removeProperty(property);
  const naturalWidth = Number(svg.getAttribute("viewBox")?.split(/[\s,]+/)[2]);
  if (Number.isFinite(naturalWidth) && naturalWidth > 0) {
    svg.setAttribute("width", String(naturalWidth));
  }

  const ids = new Map<string, string>();
  const resources = new Map<string, string>();
  [svg, ...svg.querySelectorAll("[id]")].forEach((element, index) => {
    const oldId = element.getAttribute("id");
    const newId = `${scope}-${index}`;
    if (oldId) {
      ids.set(oldId, newId);
      if (element.closest("defs")) resources.set(oldId, newId);
    }
    element.setAttribute("id", newId);
  });

  const keyframes = new Map<string, string>();
  const styles = [...svg.querySelectorAll("style")].map((element) => {
    const ast = parse(element.textContent ?? "");
    walk(ast, {
      visit: "Atrule",
      enter(node, item, list) {
        if (node.name.toLowerCase().endsWith("keyframes") && node.prelude) {
          const name = generate(node.prelude);
          const localName = `${scope}-animation-${keyframes.size}`;
          keyframes.set(name, localName);
          node.prelude = { type: "Raw", value: localName };
        } else {
          list.remove(item);
          return this.skip;
        }
      },
    });
    return { element, ast };
  });

  function rewriteReference(value: string, resource = false): string {
    let fragment = value;
    if (!fragment.startsWith("#")) {
      try {
        const target = new URL(value, document.baseURI);
        const page = new URL(document.URL);
        fragment = target.hash;
        target.hash = "";
        page.hash = "";
        if (target.href !== page.href) return value;
      } catch {
        return value;
      }
    }
    const oldId = fragment.slice(1);
    const id = (resource ? resources.get(oldId) : undefined) ?? ids.get(oldId);
    return id ? `#${id}` : value;
  }

  function rewriteCss(css: string, declarationList = false, property?: string): string {
    const ast = parse(css, { context: declarationList ? "declarationList" : "value" });
    walk(ast, function (node) {
      if (node.type === "Url") node.value = rewriteReference(node.value, true);
      if (
        node.type === "Identifier" &&
        keyframes.has(node.name) &&
        (property ?? this.declaration?.property)?.startsWith("animation")
      )
        node.name = keyframes.get(node.name)!;
    });
    return generate(ast);
  }

  for (const { element, ast } of styles) {
    walk(ast, {
      enter(node) {
        if (node.type === "Rule" && node.prelude?.type === "SelectorList" && !this.atrule) {
          walk(node.prelude, (selectorNode) => {
            if (selectorNode.type === "IdSelector" && ids.has(selectorNode.name))
              selectorNode.name = ids.get(selectorNode.name)!;
          });
          node.prelude.children.forEach((selector) => {
            if (selector.type !== "Selector") return;
            selector.children.prependData({ type: "Combinator", name: " " });
            selector.children.prependData({ type: "IdSelector", name: scope });
          });
        }
        if (node.type === "Declaration") {
          if (node.property === "font-family") node.value = parse("var(--font-family-base)", { context: "value" });
          const series = node.property.match(/^--xychart-color-(\d+)$/);
          if (series)
            node.value = parse(`var(--${["primary", "secondary", "tertiary"][Number(series[1]) % 3]})`, {
              context: "value",
            });
          node.value = parse(rewriteCss(generate(node.value), false, node.property), { context: "value" });
        }
      },
    });
    element.textContent = generate(ast).replace(/<\/style/gi, "<\\/style");
  }

  for (const element of [svg, ...svg.querySelectorAll("*")]) {
    for (const attr of [...element.attributes]) {
      if (attr.name === "style") {
        element.setAttribute(attr.name, rewriteCss(attr.value, true));
      } else if (attr.name === "aria-labelledby" || attr.name === "aria-describedby") {
        element.setAttribute(
          attr.name,
          attr.value
            .split(/\s+/)
            .map((id) => ids.get(id) ?? id)
            .join(" "),
        );
      } else if (attr.localName === "href") {
        element.setAttribute(attr.name, rewriteReference(attr.value));
      } else if (attr.value.includes("url(")) {
        element.setAttribute(attr.name, rewriteCss(attr.value));
      }
    }
  }
  return DOMPurify.sanitize(svg, {
    ADD_TAGS: ["foreignObject"],
    HTML_INTEGRATION_POINTS: { foreignobject: true },
    RETURN_TRUSTED_TYPE: false,
  });
}

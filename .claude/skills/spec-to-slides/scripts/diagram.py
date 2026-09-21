#!/usr/bin/env python3
"""Generate a self-contained inline-SVG diagram (flow or sequence) from a JSON spec.

usage: diagram.py flow spec.json [--caption TEXT] > figure.html
       diagram.py seq  spec.json [--caption TEXT] > figure.html

The output is a <figure> with the SVG and a <figcaption> (caption + legend built from the
classes actually used). Styles are inline and read the deck's colour tokens with fallbacks:
--panel --ink --ink-2 --rule --add --add-soft --mod --mod-soft --del --ext --sec-soft
--sec-line --paper --c1..--c8 (one hue per sub-project) --body --mono (font stacks).

Flow spec: {"columns": [[node, ...], ...], "edges": [edge, ...], "legend": {...}}
  node = {"id", "label" ("\\n" breaks lines), "sub"?, "chip"?: ["fred-sdk", "c1"], "cls"?: add|mod|del|same|ext}
  edge = {"from", "to", "cls"?: add|mod|del, "dashed"?: true, "label"?}
Seq spec: {"participants": [{"id", "label", "chip"?, "cls"?: add|ext}], "steps": [step, ...], "phases": [phase, ...]}
  step  = {"from", "to", "label", "cls"?: add|mod, "return"?: true (dashed)} | {"self": id, "label"} | {"note": [idA, idB], "label"}
  phase = {"from", "to", "start": stepNo, "end": stepNo, "label", "cls"?: add|mod}
legend = {"labels": {"add": "nouveau", ...}, "arrow": "text for solid arrows", "dashed": "...", "back": "..."}
Every edge is drawn from its source to its target — nothing is placed by hand.
"""
import json
import sys
from html import escape

T = {  # token → fallback
    "panel": "var(--panel,#ffffff)", "ink": "var(--ink,#14202c)", "ink2": "var(--ink-2,#56687a)", "rule": "var(--rule,#d6dde5)",
    "add": "var(--add,#177245)", "addsoft": "var(--add-soft,#d7f0e2)", "mod": "var(--mod,#a25f00)", "modsoft": "var(--mod-soft,#fbe9c6)",
    "del": "var(--del,#b42318)", "ext": "var(--ext,#7b8794)", "secsoft": "var(--sec-soft,#e6ebf8)", "secline": "var(--sec-line,#9aa8d8)",
    "paper": "var(--paper,#f3f5f8)", "body": "var(--body,system-ui,sans-serif)", "mono": "var(--mono,ui-monospace,monospace)",
}
DEFAULT_LABELS = {"add": "new", "mod": "changed", "del": "removed", "same": "unchanged", "ext": "external"}
CHAR_W, MONO_W = 8.3, 7.2

NODE_RECT = {"same": f'fill:{T["panel"]};stroke:{T["ink2"]};stroke-width:2', "add": f'fill:{T["addsoft"]};stroke:{T["add"]};stroke-width:2',
             "mod": f'fill:{T["modsoft"]};stroke:{T["mod"]};stroke-width:2', "del": f'fill:none;stroke:{T["del"]};stroke-width:2;stroke-dasharray:6 4',
             "ext": f'fill:{T["panel"]};stroke:{T["ext"]};stroke-width:2;stroke-dasharray:2 3'}
NODE_TEXT = {"same": T["ink"], "add": T["ink"], "mod": T["ink"], "del": T["del"], "ext": T["ink2"]}
STROKE = {"same": T["ink2"], "add": T["add"], "mod": T["mod"], "del": T["del"], "ink": T["ink"], "": T["ink"]}
TAG = {"add": "+", "mod": "~", "del": "−"}


def wrap(text, width=24):
    out = []
    for raw in text.split("\n"):
        line = ""
        for word in raw.split(" "):
            if line and len(line) + 1 + len(word) > width:
                out.append(line); line = word
            else:
                line = (line + " " + word).strip()
        out.append(line)
    return out


def swatch(cls):
    box = {"add": f'background:{T["addsoft"]};border:1.5px solid {T["add"]}', "mod": f'background:{T["modsoft"]};border:1.5px solid {T["mod"]}',
           "del": f'border:1.5px dashed {T["del"]}', "same": f'background:{T["panel"]};border:1.5px solid {T["ink2"]}', "ext": f'border:1.5px dotted {T["ext"]};border-radius:6px'}[cls]
    return f'<i style="display:inline-block;width:11px;height:11px;margin-right:6px;vertical-align:-1px;{box}"></i>'


def legend_html(classes, legend, edge_styles):
    labels = dict(DEFAULT_LABELS); labels.update(legend.get("labels", {}))
    item = 'style="white-space:nowrap"'
    parts = [f'<span {item}>{swatch(c)}{escape(labels[c])}</span>' for c in ("add", "mod", "del", "same", "ext") if c in classes]
    if "solid" in edge_styles and legend.get("arrow"):
        parts.append(f'<span {item}><b>→</b> {escape(legend["arrow"])}</span>')
    if "dashed" in edge_styles and legend.get("dashed"):
        parts.append(f'<span {item}><b>⇢</b> {escape(legend["dashed"])}</span>')
    if "back" in edge_styles and legend.get("back"):
        parts.append(f'<span {item}><b>⇠</b> {escape(legend["back"])}</span>')
    return f'<span class="legend" style="display:flex;flex-wrap:wrap;gap:14px;font-size:13px;color:{T["ink2"]}">' + "".join(parts) + "</span>"


def markers():
    return "<defs>" + "".join(
        f'<marker id="arr-{cls}" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto-start-reverse" markerUnits="userSpaceOnUse">'
        f'<path d="M0,0 L10,4 L0,8 z" style="fill:{col}"/></marker>' for cls, col in STROKE.items() if cls) + "</defs>"


def chip_svg(x, y, chip):
    text, c = chip
    w = len(text) * 6.8 + 12
    col = f"var(--{c},#56687a)"
    return (f'<g class="chip"><rect x="{x - w / 2:.1f}" y="{y}" width="{w:.1f}" height="16" rx="3" '
            f'style="fill:color-mix(in srgb,{col} 16%,{T["panel"]});stroke:color-mix(in srgb,{col} 45%,transparent)"/>'
            f'<text x="{x:.1f}" y="{y + 12}" text-anchor="middle" style="fill:color-mix(in srgb,{col} 80%,{T["ink"]});font:600 11px {T["mono"]}">{escape(text)}</text></g>')


def svg_open(W, H):
    return (f'<svg viewBox="0 0 {W:.0f} {H:.0f}" width="100%" preserveAspectRatio="xMidYMid meet" role="img" '
            f'style="width:100%;height:100%;max-height:100%;font-family:{T["body"]}">' + markers())


def flow(spec):
    cols = spec["columns"]; edges = spec.get("edges", []); legend = spec.get("legend", {})
    GAP_X, GAP_Y, PAD = 64, 18, 14
    nodes, col_w, col_h = {}, [], []
    for col in cols:
        w = 150
        for n in col:
            n["lines"] = wrap(n["label"])
            w = max(w, max(len(l) for l in n["lines"]) * CHAR_W + 2 * PAD)
            if n.get("sub"):
                w = max(w, len(n["sub"]) * MONO_W + 2 * PAD)
        col_w.append(min(w, 300))
    for col in cols:
        h = 0
        for n in col:
            n["h"] = PAD + 19 * len(n["lines"]) + (18 if n.get("chip") else 0) + (16 if n.get("sub") else 0) + PAD - 4
            h += n["h"]
        col_h.append(h + GAP_Y * (len(col) - 1))
    H = max(col_h) + 24; x = 12
    for ci, col in enumerate(cols):
        y = (H - col_h[ci]) / 2
        for n in col:
            n.update(x=x, y=y, w=col_w[ci], col=ci); nodes[n["id"]] = n
            y += n["h"] + GAP_Y
        x += col_w[ci] + GAP_X
    W = x - GAP_X + 12
    out = [svg_open(W, H)]
    styles, classes = set(), set()
    for e in edges:
        a, b = nodes[e["from"]], nodes[e["to"]]
        cls = e.get("cls", "same")
        if cls != "same":
            classes.add(cls)
        dashed = e.get("dashed", False); styles.add("dashed" if dashed else "solid")
        if a["col"] == b["col"]:
            sx, sy = a["x"] + a["w"] / 2, a["y"] + a["h"]; ex, ey = b["x"] + b["w"] / 2, b["y"] - 10
            d = f"M{sx:.1f},{sy:.1f} L{ex:.1f},{ey:.1f}"; mx, my = sx, (sy + ey) / 2
        else:
            sx, sy = a["x"] + a["w"], a["y"] + a["h"] / 2; ex, ey = b["x"] - 10, b["y"] + b["h"] / 2
            if b["col"] < a["col"]:
                sx, ex = a["x"], b["x"] + b["w"] + 10
            cx = (sx + ex) / 2
            d = f"M{sx:.1f},{sy:.1f} C{cx:.1f},{sy:.1f} {cx:.1f},{ey:.1f} {ex:.1f},{ey:.1f}"; mx, my = cx, (sy + ey) / 2
        out.append(f'<path d="{d}" marker-end="url(#arr-{cls})" style="fill:none;stroke:{STROKE[cls]};stroke-width:2{";stroke-dasharray:7 5" if dashed else ""}"/>')
        if e.get("label"):
            lw = len(e["label"]) * MONO_W + 10
            out.append(f'<rect x="{mx - lw / 2:.1f}" y="{my - 9:.1f}" width="{lw:.1f}" height="16" rx="3" style="fill:{T["panel"]}"/>'
                       f'<text x="{mx:.1f}" y="{my + 3:.1f}" text-anchor="middle" style="fill:{T["ink2"]};font:12px {T["mono"]}">{escape(e["label"])}</text>')
    for n in nodes.values():
        cls = n.get("cls", "same"); classes.add(cls)
        out.append(f'<rect x="{n["x"]:.1f}" y="{n["y"]:.1f}" width="{n["w"]:.1f}" height="{n["h"]:.1f}" rx="{22 if cls == "ext" else 3}" style="{NODE_RECT[cls]}"/>')
        cx = n["x"] + n["w"] / 2; ty = n["y"] + PAD + 12
        for l in n["lines"]:
            out.append(f'<text x="{cx:.1f}" y="{ty:.1f}" text-anchor="middle" style="fill:{NODE_TEXT[cls]};font-size:15px;font-weight:600">{escape(l)}</text>'); ty += 19
        if n.get("chip"):
            out.append(chip_svg(cx, ty - 12, n["chip"])); ty += 18
        if n.get("sub"):
            out.append(f'<text x="{cx:.1f}" y="{ty - 2:.1f}" text-anchor="middle" style="fill:{T["ink2"]};font:12px {T["mono"]}">{escape(n["sub"])}</text>')
        if cls in TAG:
            out.append(f'<rect x="{n["x"] + n["w"] - 18:.1f}" y="{n["y"] - 8:.1f}" width="20" height="18" rx="2" style="fill:{STROKE[cls]}"/>'
                       f'<text x="{n["x"] + n["w"] - 8:.1f}" y="{n["y"] + 5.5:.1f}" text-anchor="middle" style="fill:#fff;font:700 13px {T["mono"]}">{TAG[cls]}</text>')
    out.append("</svg>")
    return "".join(out), legend_html(classes, legend, styles)


def seq(spec):
    parts = spec["participants"]; steps = spec["steps"]; phases = spec.get("phases", []); legend = spec.get("legend", {})
    n = len(parts); W = 1100; ROW = 46
    spacing = (W - 24) / n
    xs = {p["id"]: 12 + spacing * (i + 0.5) for i, p in enumerate(parts)}
    has_chip = any(p.get("chip") for p in parts)
    ah = 44 + (16 if has_chip else 0); row0 = ah + 40
    H = row0 + ROW * len(steps) + 6
    out = [svg_open(W, H)]
    classes, styles = set(), set()
    line_y = lambda k: row0 + ROW * (k - 1)
    for ph in phases:
        x1 = xs[ph["from"]] - spacing / 2 + 8; x2 = xs[ph["to"]] + spacing / 2 - 8
        y1 = line_y(ph["start"]) - 30; y2 = line_y(ph["end"]) + 12
        cls = ph.get("cls", "add"); classes.add(cls)
        fill = T["addsoft"] if cls == "add" else T["modsoft"]
        out.append(f'<rect x="{x1:.1f}" y="{y1:.1f}" width="{x2 - x1:.1f}" height="{y2 - y1:.1f}" rx="4" style="fill:{fill};opacity:.55"/>'
                   f'<text x="{x2 - 8:.1f}" y="{y1 + 14:.1f}" text-anchor="end" style="fill:{STROKE[cls]};font:600 11px {T["mono"]};letter-spacing:.08em">{escape(ph["label"])}</text>')
    for p in parts:
        x = xs[p["id"]]
        out.append(f'<line x1="{x:.1f}" y1="{ah + 4}" x2="{x:.1f}" y2="{H - 4:.0f}" style="stroke:{T["rule"]};stroke-width:1.5"/>')
    for p in parts:
        x = xs[p["id"]]; w = min(spacing - 14, 240); cls = p.get("cls", "")
        st = {"add": f'fill:{T["addsoft"]};stroke:{T["add"]}', "ext": f'fill:{T["panel"]};stroke:{T["ext"]};stroke-dasharray:2 3'}.get(cls, f'fill:{T["secsoft"]};stroke:{T["secline"]}')
        out.append(f'<rect x="{x - w / 2:.1f}" y="4" width="{w:.1f}" height="{ah}" rx="{22 if cls == "ext" else 3}" style="{st};stroke-width:1.5"/>')
        ty = 4 + (ah / 2 + 5 if not p.get("chip") else 22)
        out.append(f'<text x="{x:.1f}" y="{ty:.1f}" text-anchor="middle" style="fill:{T["ink"]};font-size:15px;font-weight:600">{escape(p["label"])}</text>')
        if p.get("chip"):
            out.append(chip_svg(x, 4 + ah - 22, p["chip"]))
    k = 0
    for st in steps:
        k += 1; y = line_y(k)
        if "self" in st:
            x = xs[st["self"]]; tw = len(st["label"]) * 7.4 + 16
            out.append(f'<path d="M{x:.1f},{y - 14:.1f} h18 v14 h-18" marker-end="url(#arr-ink)" style="fill:none;stroke:{T["ink2"]};stroke-width:1.5"/>'
                       f'<rect x="{x + 22:.1f}" y="{y - 22:.1f}" width="{tw:.1f}" height="28" rx="3" style="fill:{T["panel"]};stroke:{T["ink2"]};stroke-width:1.5"/>'
                       f'<text x="{x + 30:.1f}" y="{y - 4:.1f}" style="fill:{T["ink"]};font-size:13px">{escape(st["label"])}</text>')
            continue
        if "note" in st:
            a, b = xs[st["note"][0]], xs[st["note"][1]]
            out.append(f'<text x="{(a + b) / 2:.1f}" y="{y - 6:.1f}" text-anchor="middle" style="fill:{T["ink2"]};font-size:13px;font-style:italic">{escape(st["label"])}</text>')
            continue
        x1, x2 = xs[st["from"]], xs[st["to"]]; back = bool(st.get("return")); left = x2 < x1
        cls = st.get("cls", "")
        if cls:
            classes.add(cls)
        styles.add("back" if back else "solid")
        mid = (x1 + x2) / 2; tw = len(st["label"]) * 7.6 + 12
        col = STROKE[cls]
        out.append(f'<line x1="{x1:.1f}" y1="{y}" x2="{x2 + (10 if left else -10):.1f}" y2="{y}" marker-end="url(#arr-{cls or "ink"})" '
                   f'style="stroke:{col};stroke-width:2{";stroke-dasharray:7 5" if back else ""}"/>')
        out.append(f'<rect x="{mid - tw / 2:.1f}" y="{y - 24:.1f}" width="{tw:.1f}" height="20" rx="3" style="fill:{T["panel"]}"/>'
                   f'<text x="{mid:.1f}" y="{y - 9:.1f}" text-anchor="middle" style="fill:{col};font-size:14px{";font-weight:600" if cls else ""}">{escape(st["label"])}</text>')
        out.append(f'<circle cx="{x1:.1f}" cy="{y}" r="10" style="fill:{T["ink"]}"/><text x="{x1:.1f}" y="{y + 4}" text-anchor="middle" style="fill:{T["paper"]};font:600 11px {T["mono"]}">{k}</text>')
    out.append("</svg>")
    return "".join(out), legend_html(classes, legend, styles)


def main():
    kind, path = sys.argv[1], sys.argv[2]
    caption = sys.argv[sys.argv.index("--caption") + 1] if "--caption" in sys.argv else "CAPTION"
    spec = json.load(open(path, encoding="utf-8"))
    svg, legend = flow(spec) if kind == "flow" else seq(spec)
    print(f'<figure class="diagram" style="margin:0;min-height:0;display:flex;flex-direction:column;gap:10px;flex:1">'
          f'<div style="flex:1;min-height:0;display:flex;align-items:center;justify-content:center;background:{T["panel"]};border:1px solid {T["rule"]};padding:14px 18px;box-sizing:border-box">{svg}</div>'
          f'<figcaption style="display:flex;justify-content:space-between;gap:24px;align-items:baseline;font-size:16px;color:{T["ink2"]}"><span style="max-width:80ch">{escape(caption)}</span>{legend}</figcaption></figure>')


if __name__ == "__main__":
    main()

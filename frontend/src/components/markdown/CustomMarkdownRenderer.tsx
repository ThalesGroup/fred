import { useEffect, useMemo, useRef, useState } from "react";
import { Box, Modal } from "@mui/material";
import { marked } from "marked";
import DOMPurify from "dompurify";
import mermaid from "mermaid";
import katex from "katex";
import "katex/dist/katex.min.css";
import CropFreeIcon from "@mui/icons-material/CropFree";
import ReactDOMServer from "react-dom/server";
interface Props {
    content: string;
    size?: "small" | "medium" | "large";
    highlight?: string;
    enableEmojiSubstitution?: boolean;
}

const fontSizeMap = {
    small: "14px",
    medium: "16px",
    large: "18px",
} as const;

function replaceStageDirectionsWithEmoji(text: string): string {
    return text
        .replace(/\badjusts glasses\b/gi, "🤓")
        .replace(/\bsmiles\b/gi, "😶")
        .replace(/\bshrugs\b/gi, "🤷")
        .replace(/\bnods\b/gi, "👍")
        .replace(/\blaughs\b/gi, "😂")
        .replace(/\bsighs\b/gi, "😮‍💨")
        .replace(/\bgrins\b/gi, "😁")
        .replace(/\bwinks\b/gi, "😉")
        .replace(/\bclears throat\b/gi, "😶‍🌫️");
}


export default function CustomMarkdownRenderer({
    content,
    size = "medium",
    highlight,
    enableEmojiSubstitution = false,
}: Props) {
    const containerRef = useRef<HTMLDivElement>(null);
    const [html, setHtml] = useState("");
    const [zoomSvg, setZoomSvg] = useState<string | null>(null);

    /* --------------------------------------------------------- */
    /* Transform markdown (emoji + highlight)                    */
    /* --------------------------------------------------------- */
    const processedMarkdown = useMemo(() => {
        const base = enableEmojiSubstitution ? replaceStageDirectionsWithEmoji(content) : content;
        if (!highlight?.trim()) return base;
        const safe = highlight.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&");
        return base.replace(new RegExp(`(${safe})`, "gi"), "**__$1__**");
    }, [content, highlight, enableEmojiSubstitution]);

    /* --------------------------------------------------------- */
    /* Mermaid init (once)                                       */
    /* --------------------------------------------------------- */
    useEffect(() => {
        mermaid.initialize({ startOnLoad: false, securityLevel: "loose" });
    }, []);

    /* --------------------------------------------------------- */
    /* Markdown → HTML                                           */
    /* --------------------------------------------------------- */
    useEffect(() => {
        const renderer = new marked.Renderer();

        renderer.code = ({ text, lang }) => {
            if (lang === "mermaid") {
                const id = `mermaid-${Math.random().toString(36).slice(2, 9)}`;
                const cropFreeSvg = ReactDOMServer.renderToStaticMarkup(
                    <CropFreeIcon fontSize="small" />
                );
                return `
                    <div class="mermaid-wrapper">
                        <button class="zoom-btn" title="Zoom diagram">
                            ${cropFreeSvg}
                        </button>
                        <div class="mermaid" id="${id}">${text}</div>
                    </div>`;

            }
            return `<pre><code>${DOMPurify.sanitize(text)}</code></pre>`;
        };

        // --- KaTeX extension ---
        const katexExtension = {
            name: "katex",
            level: "inline" as const,
            start(src: string) {
                const match = src.match(/\$+/);
                return match ? match.index : undefined;
            },
            tokenizer(src: string) {
                const inlineMath = /^\$([^\$\n]+?)\$/; // $...$
                const blockMath = /^\$\$([\s\S]+?)\$\$/; // $$...$$

                let match = blockMath.exec(src);
                if (match) {
                    return {
                        type: "katex",
                        raw: match[0],
                        text: match[1].trim(),
                        displayMode: true,
                    };
                }

                match = inlineMath.exec(src);
                if (match) {
                    return {
                        type: "katex",
                        raw: match[0],
                        text: match[1].trim(),
                        displayMode: false,
                    };
                }

                return undefined;
            },
            renderer(token: any) {
                try {
                    return katex.renderToString(token.text, {
                        throwOnError: false,
                        displayMode: token.displayMode,
                    });
                } catch (e) {
                    console.error("KaTeX render error:", e);
                    return token.raw;
                }
            },
        };

        // :::details
        const detailsExtension = {
            name: "details",
            level: "block" as const,
            start(src: string) {
                return src.match(/:::details/)?.index;
            },
            tokenizer(src: string) {
                const m = /^:::details\s*(.*)\n([\s\S]+?)\n:::/m.exec(src);
                if (!m) return undefined;
                return {
                    type: "details",
                    raw: m[0],
                    title: m[1] || "Details",
                    text: m[2],
                    tokens: marked.lexer(m[2]),
                } as any;
            },
            renderer(token: any) {
                return `<details><summary>${DOMPurify.sanitize(token.title)}</summary>${token.text}</details>`;
            },
        };

        marked.use({
            renderer,
            extensions: [detailsExtension, katexExtension],
            walkTokens(t: any) {
                if (t.type === "details" && t.tokens) t.text = marked.parser(t.tokens);
            },
        });

        (async () => {
            const raw = await marked.parse(processedMarkdown);
            // setHtml(DOMPurify.sanitize(raw, { USE_PROFILES: { html: true } }));
            setHtml(
                DOMPurify.sanitize(raw, {
                    // keep the default HTML rules *and* allow inline SVG
                    USE_PROFILES: { html: true, svg: true },
                    // explicitly permit the tags and attributes the icon SVG needs
                    ADD_TAGS: ['svg', 'path', 'g'],
                    ADD_ATTR: ['d', 'fill', 'stroke', 'stroke-width', 'viewBox'],
                }),
            );
        })();
    }, [processedMarkdown]);

    /* --------------------------------------------------------- */
    /* Render diagrams + attach zoom handlers                    */
    /* --------------------------------------------------------- */
    useEffect(() => {
        if (!containerRef.current) return;
        mermaid.run({ nodes: Array.from(containerRef.current.querySelectorAll(".mermaid")) as HTMLElement[] }).catch(console.error);

        const cleanups: (() => void)[] = [];
        containerRef.current.querySelectorAll<HTMLElement>(".mermaid-wrapper").forEach(wrapper => {
            const btn = wrapper.querySelector<HTMLElement>(".zoom-btn");
            if (!btn) return;
            const click = () => {
                const diagramSvg = wrapper.querySelector(".mermaid svg"); // ← pick diagram, not icon
                if (!diagramSvg) return;
                const clone = diagramSvg.cloneNode(true) as SVGSVGElement;
                clone.removeAttribute("width");
                clone.removeAttribute("height");
                clone.setAttribute("preserveAspectRatio", "xMidYMid meet");
                setZoomSvg(clone.outerHTML);
            };
            btn.addEventListener("click", click);
            cleanups.push(() => btn.removeEventListener("click", click));
        });
        return () => cleanups.forEach(fn => fn());
    }, [html]);

    /* --------------------------------------------------------- */
    /* JSX                                                       */
    /* --------------------------------------------------------- */
    return (
        <>
            <Box
                ref={containerRef}
                sx={{
                    fontFamily: `"Inter", sans-serif`,
                    fontWeight: 300,
                    fontSize: fontSizeMap[size],
                    lineHeight: 1.6,
                    overflowX: "auto",
                    wordBreak: "break-word",

                    /* Paragraphs & Lists */
                    "& p": { mb: 1.5 },
                    "& li": { mb: 0.5 },

                    /* Code blocks & inline code */
                    "& pre": {
                        fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
                        fontSize: "0.8rem",
                        bgcolor: "#f5f5f5",
                        p: 2,
                        borderRadius: 2,
                        overflowX: "auto",
                    },
                    "& code": {
                        fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
                        fontSize: "0.8rem",
                        bgcolor: "#f5f5f5",
                        px: "0.2rem",
                        py: "0.1rem",
                        borderRadius: "4px",
                    },

                    /* tables */
                    "& table": { width: "100%", borderCollapse: "collapse", my: 2 },
                    "& th, & td": { border: "1px solid #ddd", p: "0.5rem", textAlign: "left" },
                    "& th": { bgcolor: "#f3f3f3", fontWeight: 600 },
                    /* headings */
                    "& h1": { fontSize: "1.5rem", fontWeight: 600, mt: 2 },
                    "& h2": { fontSize: "1.3rem", fontWeight: 600, mt: 2 },
                    "& h3": { fontSize: "1.1rem", fontWeight: 600, mt: 1.5 },
                    /* details */
                    "& details": { bgcolor: "#fafafa", border: "1px solid #ccc", borderRadius: 1, p: 1, my: 2 },

                    /* Diagram styling */
                    "& .mermaid-wrapper": {
                        position: "relative",
                        display: "flex",
                        justifyContent: "center",
                        mx: "auto",
                        my: 2,
                        maxWidth: "100%",
                    },
                    "& .mermaid": {
                        display: "inline-block",
                        p: 1,
                        bgcolor: "#fff",
                        border: "1px solid #ddd",
                        borderRadius: 2,
                        overflowX: "auto",
                        width: "80%",   // fill 80% of wrapper width
                        maxWidth: "100%",
                    },
                    "& .mermaid svg": { maxWidth: "100%", height: "auto" },
                    "& .zoom-btn": {
                        position: "absolute",
                        top: 4,
                        right: 4,
                        background: "rgba(255,255,255,0.8)",
                        border: "1px solid #ccc",
                        borderRadius: "50%",
                        width: 24,
                        height: 24,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        cursor: "pointer",
                        transition: "background 0.2s",
                        "&:hover": { background: "#fff" },
                    },
                }}
                dangerouslySetInnerHTML={{ __html: html }}
            />

            <Modal open={Boolean(zoomSvg)} onClose={() => setZoomSvg(null)}>
                <Box
                    sx={{
                        position: "absolute",
                        top: "50%",
                        left: "50%",
                        transform: "translate(-50%, -50%)",
                        width: "90vw",
                        height: "90vh",
                        bgcolor: "background.paper",
                        p: 2,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        overflow: "auto",
                        "& svg": {
                            maxWidth: "100%",
                            maxHeight: "100%",
                            width: "auto",
                            height: "auto",
                            display: "block",
                            margin: "auto",
                        },
                    }}
                >
                    {zoomSvg && (
                        <div
                            className="zoom-content"
                            dangerouslySetInnerHTML={{ __html: zoomSvg }}
                            style={{
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                width: "100%",
                                height: "100%",
                            }}
                        />
                    )}
                </Box>
            </Modal>
        </>
    );
}

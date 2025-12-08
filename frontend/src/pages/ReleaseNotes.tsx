// ReleaseNotes.tsx
// Displays the bundled release notes (public/release.md) inside the app shell.

import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import Editor from "@monaco-editor/react";
import { Box, Button, Stack, ToggleButton, ToggleButtonGroup, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { useEffect, useMemo, useState } from "react";
import { getProperty } from "../common/config";

export default function ReleaseNotes() {
  const [brandMarkdown, setBrandMarkdown] = useState<string>("");
  const [baseMarkdown, setBaseMarkdown] = useState<string>("");
  const [brandLabel, setBrandLabel] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const theme = useTheme();

  useEffect(() => {
    const load = async () => {
      try {
        const toSlug = (v?: string | null) =>
          (v || "")
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9_-]+/g, "-")
            .replace(/^-+|-+$/g, "");
        const releaseBrand = toSlug(getProperty("releaseBrand") as string | undefined) || "fred";
        console.log("[ReleaseNotes] releaseBrand:", releaseBrand);

        const base = (import.meta.env?.BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";
        console.log("[ReleaseNotes] base URL:", base || "(root)");

        const fetchDoc = async (path: string) => {
          try {
            const url = `${base}${path.startsWith("/") ? path : `/${path}`}`;
            const resp = await fetch(url, { cache: "no-cache" });
            if (!resp.ok) return null;
            const ct = resp.headers.get("content-type") || "";
            const text = await resp.text();
            const looksHtml =
              ct.includes("text/html") || text.toLowerCase().includes("<!doctype") || text.includes("/@vite/client");
            return looksHtml ? null : text;
          } catch {
            return null;
          }
        };

        // Try brand-specific first
        let brandDoc: string | null = null;
        const brandPath = `/release-${releaseBrand}.md`;
        const brandContent = await fetchDoc(brandPath);
        if (brandContent) {
          brandDoc = brandContent;
          console.log("[ReleaseNotes] loaded brand release:", brandPath);
        } else {
          console.log("[ReleaseNotes] missing brand release:", brandPath);
        }

        const baseDoc = await fetchDoc("/release.md");
        console.log("[ReleaseNotes] base release present:", Boolean(baseDoc));

        if (!brandDoc && !baseDoc) {
          throw new Error("not found");
        }

        if (brandDoc) {
          setBrandMarkdown(brandDoc);
          setBrandLabel(releaseBrand || "Custom");
        }
        if (baseDoc) setBaseMarkdown(baseDoc);
      } catch (e: any) {
        setError("Release notes are unavailable.");
      } finally {
        setIsLoading(false);
      }
    };

    void load();
  }, []);

  const cards = useMemo(() => {
    const list: Array<{ key: "brand" | "base"; title: string; content: string }> = [];
    if (brandMarkdown)
      list.push({
        key: "brand",
        title: brandLabel ? `Release (${brandLabel})` : "Release (brand)",
        content: brandMarkdown,
      });
    if (baseMarkdown) list.push({ key: "base", title: "Base Release (release.md)", content: baseMarkdown });
    return list;
  }, [baseMarkdown, brandLabel, brandMarkdown]);

  const [selectedKey, setSelectedKey] = useState<"brand" | "base" | null>(null);

  useEffect(() => {
    if (cards.length && !selectedKey) {
      setSelectedKey(cards[0].key);
    }
  }, [cards, selectedKey]);

  const handleCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // silent fallback; no toast system in this page
    }
  };

  return (
    <Box sx={{ p: 3, height: "100%", display: "flex", flexDirection: "column", gap: 2 }}>
      <Stack direction="row" alignItems="center" spacing={1}>
        <InfoOutlinedIcon color="primary" fontSize="small" />
        <Typography variant="h6" fontWeight={600}>
          Release Notes
        </Typography>
      </Stack>
      <Box sx={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 2 }}>
        {cards.length > 1 && (
          <ToggleButtonGroup
            exclusive
            value={selectedKey}
            onChange={(_, val) => val && setSelectedKey(val)}
            size="small"
            sx={{
              alignSelf: "flex-start",
              "& .MuiToggleButton-root": {
                textTransform: "none",
                fontWeight: 600,
                borderRadius: 6,
                borderColor: (theme) => theme.palette.divider,
                px: 1.5,
                py: 0.3,
                "&.Mui-selected": {
                  backgroundColor: (theme) => theme.palette.action.selected,
                  color: (theme) => theme.palette.primary.main,
                  borderColor: (theme) => theme.palette.primary.main,
                },
              },
            }}
          >
            {cards.map((card) => (
              <ToggleButton key={card.key} value={card.key}>
                {card.title}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
        )}

        {cards.length === 0 && <Typography variant="body2">{error ?? "No release notes available."}</Typography>}

        {selectedKey && (
          <Box sx={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", gap: 1 }}>
            <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1}>
              <Typography variant="subtitle2" fontWeight={700} noWrap>
                {cards.find((c) => c.key === selectedKey)?.title}
              </Typography>
              <Button
                size="small"
                startIcon={<ContentCopyIcon fontSize="small" />}
                onClick={() => handleCopy(cards.find((c) => c.key === selectedKey)?.content || "")}
                sx={{ textTransform: "none", fontWeight: 600 }}
              >
                Copy
              </Button>
            </Stack>
            <Box sx={{ flex: 1, minHeight: 0, borderRadius: 1, overflow: "hidden", border: (theme) => `1px solid ${theme.palette.divider}` }}>
              <Editor
                height="100%"
                defaultLanguage="markdown"
                value={isLoading ? "" : cards.find((c) => c.key === selectedKey)?.content || ""}
                options={{
                  readOnly: true,
                  minimap: { enabled: false },
                  scrollBeyondLastLine: false,
                  lineNumbers: "off",
                  folding: false,
                  wordWrap: "on",
                  fontSize: 13,
                  smoothScrolling: true,
                  renderLineHighlight: "none",
                  renderWhitespace: "none",
                  scrollbar: { verticalScrollbarSize: 6, horizontalScrollbarSize: 6 },
                }}
                theme={theme.palette.mode === "dark" ? "vs-dark" : "vs"}
              />
            </Box>
          </Box>
        )}
      </Box>
    </Box>
  );
}

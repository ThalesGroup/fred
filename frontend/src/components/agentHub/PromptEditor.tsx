// PromptEditor.tsx — changes only in the token toolbar + insertion logic
import { useMemo, useRef, useState } from "react";
import { Box, Tabs, Tab, IconButton, Tooltip, Stack, Typography, Divider, Chip, useTheme } from "@mui/material";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import RestoreIcon from "@mui/icons-material/Restore";
import PreviewIcon from "@mui/icons-material/Preview";
import EditIcon from "@mui/icons-material/Edit";
import ReactMarkdown from "react-markdown";
import Editor, { OnMount } from "@monaco-editor/react";
import * as monaco from "monaco-editor";

type Props = {
  label: string;
  value: string;
  defaultValue?: string;
  onChange: (next: string) => void;
  tokens?: string[]; // e.g. ["{objective}", "{step_number}", "{step}", "{options}"]
};

export function PromptEditor({ label, value, defaultValue = "", onChange, tokens = [] }: Props) {
  const [tab, setTab] = useState<"edit" | "preview">("edit");
  const theme = useTheme();

  // keep a ref to monaco editor instance (optional, when Monaco is present)
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const onMount: OnMount = (editor) => {
    editorRef.current = editor;
  };

  const hasChanged = useMemo(() => (value ?? "") !== (defaultValue ?? ""), [value, defaultValue]);
  const previewStyles = {
    px: 1.5,
    py: 1.25,
    maxHeight: 300,
    overflow: "auto",
    fontSize: 13, // 👈 match Monaco’s 13
    lineHeight: 1.5,
    // keep headings modest so they don’t look bigger than the editor
    "& h1, & h2, & h3": { fontSize: 14, marginTop: 8, marginBottom: 4 },
    // ensure common blocks inherit the same size
    "& p, & li, & code, & pre, & blockquote": { fontSize: 13 },
    "& code": { px: 0.5, py: 0.1, borderRadius: 1, bgcolor: "action.hover" },
    "& pre": { p: 1, borderRadius: 1, bgcolor: "action.hover", overflow: "auto" },
    "& blockquote": { borderLeft: 2, borderColor: "divider", pl: 1.5, color: "text.secondary" },
  } as const;
  // insert token either at cursor (Monaco) or append at end
  const insertToken = (tok: string) => {
    const ed = editorRef.current;
    if (ed) {
      const sel = ed.getSelection();
      const model = ed.getModel();
      if (model && sel) {
        ed.executeEdits("insert-token", [{ range: sel, text: tok, forceMoveMarkers: true }]);
        ed.focus();
        return;
      }
    }
    // fallback: append with spacing
    const next = (value || "") + (value?.endsWith(" ") ? "" : " ") + tok + " ";
    onChange(next);
  };

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(value || "");
    } catch {}
  };
  const resetToDefault = () => onChange(defaultValue || "");

  return (
    <Box sx={{ border: `1px solid ${theme.palette.divider}`, borderRadius: 1.5, overflow: "hidden" }}>
      {/* Header */}
      <Box sx={{ px: 1.25, py: 0.75, display: "flex", alignItems: "center", gap: 1, bgcolor: "action.hover" }}>
        <Typography variant="subtitle2">{label}</Typography>
        {hasChanged && (
          <Chip
            size="small"
            color="warning"
            variant="outlined"
            label="modified"
            sx={{ ml: 0.5, height: 18, fontSize: 11 }}
          />
        )}
        <Box sx={{ ml: "auto", display: "flex", alignItems: "center", gap: 0.5 }}>
          <Tooltip title="Reset to default">
            <span>
              <IconButton size="small" onClick={resetToDefault} disabled={!hasChanged}>
                <RestoreIcon fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title="Copy prompt">
            <IconButton size="small" onClick={copyToClipboard}>
              <ContentCopyIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
      </Box>

      {/* Compact token toolbar (chips) */}
      {tokens.length > 0 && (
        <>
          <Box sx={{ px: 1.25, py: 0.5 }}>
            <Stack direction="row" alignItems="center" gap={0.75} flexWrap="wrap">
              <Typography variant="caption" color="text.secondary">
                Insert
              </Typography>
              {tokens.map((t) => (
                <Chip
                  key={t}
                  label={t}
                  size="small"
                  color="primary"
                  variant="outlined"
                  onClick={() => insertToken(t)}
                  sx={{
                    height: 22,
                    fontSize: 11,
                    borderRadius: 1,
                    cursor: "pointer",
                    "& .MuiChip-label": { px: 0.75 },
                  }}
                />
              ))}
            </Stack>
          </Box>
          <Divider />
        </>
      )}

      {/* Tabs */}
      <Box sx={{ px: 1 }}>
        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v)}
          sx={{ minHeight: 32, "& .MuiTab-root": { minHeight: 32, textTransform: "none", fontSize: 13 } }}
        >
          <Tab icon={<EditIcon fontSize="small" />} iconPosition="start" value="edit" label="Edit" />
          <Tab icon={<PreviewIcon fontSize="small" />} iconPosition="start" value="preview" label="Preview" />
        </Tabs>
      </Box>
      <Divider />

      {/* Content */}
      {tab === "edit" ? (
        <Box sx={{ height: 240 }}>
          <Editor
            onMount={onMount}
            height="100%"
            language="markdown"
            value={value}
            theme={theme.palette.mode === "dark" ? "vs-dark" : "vs"}
            onChange={(v) => onChange(v ?? "")}
            options={{
              wordWrap: "on",
              minimap: { enabled: false },
              fontSize: 13,
              lineNumbers: "on",
              renderWhitespace: "selection",
              scrollBeyondLastLine: false,
            }}
          />
        </Box>
      ) : (
        <Box sx={previewStyles}>
          <ReactMarkdown>{value || ""}</ReactMarkdown>
        </Box>
      )}

      {hasChanged && (
        <>
          <Divider />
          <Box sx={{ px: 1.5, py: 1.25, maxHeight: 300, overflow: "auto" }}>
            <ReactMarkdown>{value || ""}</ReactMarkdown>
          </Box>
        </>
      )}
    </Box>
  );
}

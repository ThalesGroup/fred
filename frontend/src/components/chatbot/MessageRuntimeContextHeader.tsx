// MessageRuntimeContextHeader.tsx
// Header indicators for Libraries/ChatContext + info icon that opens the popover.

import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import LibraryBooksOutlinedIcon from "@mui/icons-material/LibraryBooksOutlined";
import PersonOutlinedIcon from "@mui/icons-material/PersonOutline";
import { Box, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { SimpleTooltip } from "../../shared/ui/tooltips/Tooltips";
import { ChatMessage } from "../../slices/agentic/agenticOpenApi";
import { getExtras } from "./ChatBotUtils";
import MessageRuntimeContextPopover from "./MessageRuntimeContextPopover";

type Props = {
  message: ChatMessage;
  libraryNameById?: Record<string, string>;
  chatContextNameById?: Record<string, string>;
};

export default function MessageRuntimeContextHeader({ message, libraryNameById, chatContextNameById }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();

  // Popover anchor + bridged hover to avoid flicker
  const [insightAnchorEl, setInsightAnchorEl] = useState<HTMLElement | null>(null);
  const insightHoverRef = useRef(false);

  const openInsights = (el: HTMLElement | null) => {
    setInsightAnchorEl(el);
    insightHoverRef.current = true;
  };
  const closeInsights = () => {
    insightHoverRef.current = false;
    setTimeout(() => {
      if (!insightHoverRef.current) setInsightAnchorEl(null);
    }, 120);
  };

  // ---- Extract data from message.metadata.runtime_context
  const meta: any = message.metadata ?? {};
  const rc: any = meta?.runtime_context ?? {};

  const getList = (obj: any, keys: string[]): string[] => {
    for (const k of keys) {
      const v = obj?.[k];
      if (Array.isArray(v) && v.length) return v.filter(Boolean).map(String);
    }
    return [];
  };
  const getFirst = (obj: any, keys: string[]): string | undefined => {
    for (const k of keys) {
      const v = obj?.[k];
      if (v != null && v !== "") return String(v);
    }
    return undefined;
  };

  const libsIds = getList(rc, [
    "selected_document_libraries_ids",
    "document_library_ids",
    "selectedDocumentLibrariesIds",
    "documentLibraryIds",
  ]);

  // ✅ Chat context first, legacy profiles as fallback
  const chatCtxIds = getList(rc, [
    "selected_chat_context_ids",
    "chat_context_ids",
    "selected_profile_ids",
    "profile_resource_ids",
    "selectedProfileIds",
    "profileResourceIds",
  ]);

  const searchPolicy = getFirst(rc, ["search_policy", "searchPolicy"]);
  const usedTemperature =
    meta?.temperature != null ? Number(meta.temperature) : rc?.temperature != null ? Number(rc.temperature) : undefined;

  const labelize = (ids: string[] | undefined, map?: Record<string, string>) =>
    (ids ?? []).filter(Boolean).map((id) => map?.[id] || id);

  const libsLabeled = useMemo(() => labelize(libsIds, libraryNameById), [libsIds, libraryNameById]);
  const ctxLabeled = useMemo(() => labelize(chatCtxIds, chatContextNameById), [chatCtxIds, chatContextNameById]);

  const libsTextFull = libsLabeled.join(", ");
  const chatCtxTextFull = ctxLabeled.join(", ");

  const librariesLabel = libsLabeled.length > 1 ? t("header.librariesPlural") : t("header.librariesSingular");
  const chatContextLabel = ctxLabeled.length > 1 ? t("header.chatContextsPlural") : t("header.chatContextSingular");

  const extras = getExtras(message);
  const modelName: string | undefined = meta?.model ?? undefined;
  const latencyMs: number | undefined = meta?.latency_ms ?? meta?.timings?.durationMs ?? meta?.latency?.ms ?? undefined;
  const inTokens = message.metadata?.token_usage?.input_tokens;
  const outTokens = message.metadata?.token_usage?.output_tokens;

  const showLibs = libsLabeled.length > 0;
  const showChatCtx = ctxLabeled.length > 0;
  const showAny = showLibs || showChatCtx;

  if (!showAny && !searchPolicy && usedTemperature == null && modelName == null && latencyMs == null) {
    return null;
  }

  return (
    <Box
      sx={{
        ml: "auto",
        display: "flex",
        alignItems: "center",
        gap: 0.5,
        opacity: 1,
        transition: "opacity .15s ease",
      }}
    >
      {showLibs && (
        <SimpleTooltip
          title={
            <Box>
              <Typography variant="caption" sx={{ opacity: 0.7, display: "block", mb: 0.25 }}>
                {librariesLabel}
              </Typography>
              <Typography variant="caption">{libsTextFull}</Typography>
            </Box>
          }
        >
          <Box
            sx={{
              display: "inline-flex",
              alignItems: "center",
              gap: 0.5,
              px: 0.75,
              py: 0.25,
              borderRadius: 1,
              border: `1px solid ${theme.palette.divider}`,
              maxWidth: 320,
            }}
          >
            <LibraryBooksOutlinedIcon sx={{ fontSize: 14 }} />
            <Typography
              variant="caption"
              sx={{ lineHeight: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
            >
              {t("header.librariesInline", { label: librariesLabel, names: libsTextFull })}
            </Typography>
          </Box>
        </SimpleTooltip>
      )}

      {showChatCtx && (
        <SimpleTooltip
          title={
            <Box>
              <Typography variant="caption" sx={{ opacity: 0.7, display: "block", mb: 0.25 }}>
                {chatContextLabel}
              </Typography>
              <Typography variant="caption">{chatCtxTextFull}</Typography>
            </Box>
          }
        >
          <Box
            sx={{
              display: "inline-flex",
              alignItems: "center",
              gap: 0.5,
              px: 0.75,
              py: 0.25,
              borderRadius: 1,
              border: `1px solid ${theme.palette.divider}`,
              maxWidth: 320,
            }}
          >
            <PersonOutlinedIcon sx={{ fontSize: 14 }} />
            <Typography
              variant="caption"
              sx={{ lineHeight: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
            >
              {t("header.chatContextsInline", { label: chatContextLabel, names: chatCtxTextFull })}
            </Typography>
          </Box>
        </SimpleTooltip>
      )}

      {/* Info icon + popover */}
      <Box
        onMouseEnter={(e) => openInsights(e.currentTarget)}
        onMouseLeave={closeInsights}
        sx={{ display: "inline-flex", cursor: "default" }}
        aria-label={t("insights.aria")}
      >
        <InfoOutlinedIcon fontSize="small" sx={{ ml: 0.5 }} />

        <MessageRuntimeContextPopover
          anchorEl={insightAnchorEl}
          onMouseEnter={() => (insightHoverRef.current = true)}
          onMouseLeave={() => {
            insightHoverRef.current = false;
            setTimeout(() => {
              if (!insightHoverRef.current) setInsightAnchorEl(null);
            }, 120);
          }}
          task={extras?.task}
          node={extras?.node}
          modelName={modelName}
          tokens={{ in: inTokens, out: outTokens }}
          latencyMs={latencyMs}
          searchPolicy={searchPolicy}
          temperature={typeof usedTemperature === "number" ? usedTemperature : undefined}
          libsLabeled={libsLabeled}
          ctxLabeled={ctxLabeled}
        />
      </Box>
    </Box>
  );
}

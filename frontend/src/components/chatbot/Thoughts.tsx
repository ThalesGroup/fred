// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// ...

import Editor from "@monaco-editor/react";
import EmojiObjectsIcon from "@mui/icons-material/EmojiObjects";
import PsychologyAltIcon from "@mui/icons-material/PsychologyAlt";
import WebhookIcon from "@mui/icons-material/Webhook";
import {
  Timeline,
  TimelineConnector,
  TimelineContent,
  TimelineDot,
  TimelineItem,
  timelineItemClasses,
  TimelineSeparator,
} from "@mui/lab";
import { Box, Fade, Grid2, IconButton, Modal, Tooltip, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { useMemo, useState } from "react";
import FoldableChatSection from "./FoldableChatSection";
import { ChatMessagePayload } from "../../slices/agentic/agenticOpenApi";

/**
 * Thoughts
 * Renders a timeline of grouped intermediate messages (plan, thought, execution, tool_result)
 * plus task-scoped finals. Provides two modals:
 *  - Full reasoning path (non-tool + tool mixed, readable)
 *  - Tools usage details (only tool messages)
 */
export default function Thoughts({
  messages,
  isOpenByDefault = false,
}: {
  messages: Record<string, ChatMessagePayload[]>;
  isOpenByDefault: boolean;
}) {
  const theme = useTheme();

  const [thoughtsDetails, setThoughtsDetails] = useState<string>("");
  const [modalThoughtsDetails, setModalThoughtsDetails] = useState<boolean>(false);

  // Precompute a list to know whether any group has a tool message (for showing the wrench icon).
  const groupsHaveTools = useMemo(() => {
    const map: Record<string, boolean> = {};
    for (const [task, msgs] of Object.entries(messages)) {
      map[task] = msgs.some((m) => m.type === "tool" || m.subtype === "tool_result");
    }
    return map;
  }, [messages]);

  const openModal = (content: string) => {
    setThoughtsDetails(content);
    setModalThoughtsDetails(true);
  };
  const closeModal = () => setModalThoughtsDetails(false);

  // ---- Builders for modal content (plain text / markdown-ish) ----------------

  const summarizeToolCall = (m: ChatMessagePayload) => {
    const tc = m.metadata?.tool_call;
    if (!tc) return "";
    const argPreview =
      tc.args && Object.keys(tc.args).length > 0
        ? `args: ${JSON.stringify(tc.args, null, 2)}\n`
        : "";
    const preview = tc.result_preview ? `preview: ${tc.result_preview}\n` : "";
    const latency = typeof tc.latency_ms === "number" ? `latency: ${tc.latency_ms}ms\n` : "";
    const err = tc.error ? `error: ${tc.error}\n` : "";
    return `tool: ${tc.name}\n${argPreview}${preview}${latency}${err}`.trim();
  };

  const headerForGroup = (groupMsgs: ChatMessagePayload[]) => {
    const agentName =
      groupMsgs[0]?.metadata?.agent_name ??
      (typeof groupMsgs[0]?.metadata?.fred?.agentic_flow === "string"
        ? // backward-compat if server still populates it
          (groupMsgs[0]?.metadata?.fred as any).agentic_flow
        : undefined) ??
      "Agent";
    return `# Responses from ${agentName}\n\n`;
  };

  // Full reasoning path (mix of all messages in the group)
  const buildReasoningContent = (groupMsgs: ChatMessagePayload[]) => {
    let content = headerForGroup(groupMsgs);
    content += "---\n";
    for (const m of groupMsgs) {
      const subtype = m.subtype ?? "—";
      const ts = m.timestamp ? new Date(m.timestamp).toLocaleString() : "";
      // Choose a readable title per message
      const title =
        m.type === "tool"
          ? `Tool call (${m.metadata?.tool_call?.name ?? "tool"})`
          : `Step: ${subtype}`;

      content += `## ${title}\n`;
      if (ts) content += `*${ts}*\n`;

      if (m.type === "tool") {
        // Show tool metadata, then the tool output/content
        const tc = summarizeToolCall(m);
        if (tc) content += tc + "\n\n";
        if (m.content?.trim()) {
          content += "```\n" + m.content.trim() + "\n```\n\n";
        }
      } else {
        // For non-tool messages, just show their content
        if (m.content?.trim()) {
          content += m.content.trim() + "\n\n";
        }
      }
      content += "---\n";
    }
    return content;
  };

  // Only tool messages (tool inputs/outputs)
  const buildToolsOnlyContent = (groupMsgs: ChatMessagePayload[]) => {
    const toolMsgs = groupMsgs.filter((m) => m.type === "tool" || m.subtype === "tool_result");
    let content = headerForGroup(groupMsgs);
    if (toolMsgs.length === 0) {
      content += "_No tools were invoked in this group._\n";
      return content;
    }
    for (const m of toolMsgs) {
      const ts = m.timestamp ? new Date(m.timestamp).toLocaleString() : "";
      const title = `Tool: ${m.metadata?.tool_call?.name ?? "tool"}`;
      content += `## ${title}\n`;
      if (ts) content += `*${ts}*\n`;
      const tc = summarizeToolCall(m);
      if (tc) content += tc + "\n\n";
      if (m.content?.trim()) {
        content += "```\n" + m.content.trim() + "\n```\n\n";
      }
      content += "---\n";
    }
    return content;
  };

  // ---------------------------------------------------------------------------

  return (
    <>
      {Object.keys(messages).length > 0 && (
        <FoldableChatSection title="Thoughts" icon={<EmojiObjectsIcon />} defaultOpen={isOpenByDefault} sx={{ mt: 2 }}>
          <Timeline
            sx={{
              [`& .${timelineItemClasses.root}:before`]: {
                flex: 0,
                padding: 0,
              },
              margin: "0px",
            }}
          >
            {Object.entries(messages).map(([taskName, msgs], index, arr) => {
              const hasTools = groupsHaveTools[taskName];
              const isLast = index === arr.length - 1;

              return (
                <TimelineItem
                  key={`thought-${taskName}-${index}`}
                  style={{
                    minHeight: !isLast ? "60px" : "0px",
                  }}
                >
                  <TimelineSeparator>
                    <TimelineDot
                      style={{
                        backgroundColor: theme.palette.primary.main,
                      }}
                    />
                    {!isLast && <TimelineConnector />}
                  </TimelineSeparator>

                  <TimelineContent>
                    <Grid2 container display="flex" flexDirection="row">
                      <Grid2 size={11}>
                        <Typography variant="body2">{taskName}</Typography>
                      </Grid2>

                      <Grid2
                        size={1}
                        display="flex"
                        flexDirection="row"
                        alignItems="flex-start"
                        justifyContent="center"
                        gap={0}
                      >
                        <Tooltip title={"View the reasoning path"}>
                          <IconButton
                            aria-label="View details"
                            style={{ color: theme.palette.primary.main, padding: 0 }}
                            onClick={() => openModal(buildReasoningContent(msgs))}
                          >
                            <PsychologyAltIcon color="primary" sx={{ fontSize: "1.8rem" }} />
                          </IconButton>
                        </Tooltip>

                        {hasTools && (
                          <Tooltip title={"View the tools used and their results"}>
                            <IconButton
                              aria-label="View tools usage"
                              style={{ color: theme.palette.warning.main, padding: 0 }}
                              onClick={() => openModal(buildToolsOnlyContent(msgs))}
                            >
                              <WebhookIcon color="primary" sx={{ fontSize: "1.8rem" }} />
                            </IconButton>
                          </Tooltip>
                        )}
                      </Grid2>
                    </Grid2>
                  </TimelineContent>
                </TimelineItem>
              );
            })}
          </Timeline>
        </FoldableChatSection>
      )}

      <Modal open={modalThoughtsDetails} onClose={closeModal}>
        <Fade in={modalThoughtsDetails} timeout={100}>
          <Box
            sx={{
              position: "absolute",
              top: "50%",
              left: { xs: "calc(50% + 40px)", md: "calc(50% + 80px)" },
              transform: "translate(-50%, -50%)",
              width: { xs: "calc(100% - 140px)", md: "calc(80% - 140px)", lg: "calc(55% - 140px)" },
              maxHeight: "80vh",
              bgcolor: "background.paper",
              color: "text.primary",
              borderRadius: 3,
              p: 4,
              display: "flex",
              flexDirection: "column",
              scrollBehavior: "smooth",
              scrollbarWidth: "10px",
              boxShadow: 48,
              overflowY: "auto",
            }}
          >
            {thoughtsDetails && (
              <Editor
                theme={theme.palette.mode === "dark" ? "vs-dark" : "vs"}
                height="100vh"
                defaultLanguage="markdown"
                options={{ readOnly: true, wordWrap: "on", minimap: { enabled: false } }}
                defaultValue={thoughtsDetails}
              />
            )}
          </Box>
        </Fade>
      </Modal>
    </>
  );
}

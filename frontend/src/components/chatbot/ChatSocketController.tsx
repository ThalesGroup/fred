// src/pages/ChatPOC.tsx
// Copyright Thales 2025
// Apache-2.0

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AppBar,
  Toolbar,
  IconButton,
  Typography,
  Box,
  Paper,
  Stack,
  Button,
  List,
  ListItemButton,
  ListItemText,
  Divider,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Grid2 as Grid,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import PersonIcon from "@mui/icons-material/Person";
import SendIcon from "@mui/icons-material/Send";

import { useAgenticData } from "../../hooks/useAgenticData";
import { useUserPrefs, useAgentPrefs, useSessionAgent } from "../../hooks/usePrefs";

import {
  AgenticFlow,
  ChatMessage,
  RuntimeContext,
  SessionSchema,
  useLazyGetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetQuery,
} from "../../slices/agentic/agenticOpenApi";
import { SearchPolicyName } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";

// -----------------------------
// Small input bar (pure UI)
// -----------------------------
function SendBar({ disabled, onSend }: { disabled?: boolean; onSend: (text: string) => void }) {
  const [text, setText] = useState("");
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const v = text.trim();
    if (!v) return;
    onSend(v);
    setText("");
  };
  return (
    <Box component="form" onSubmit={submit} sx={{ display: "flex", gap: 1, maxWidth: 900 }}>
      <TextField fullWidth placeholder="Ask something…" value={text} onChange={(e) => setText(e.target.value)} disabled={disabled} />
      <Button type="submit" variant="contained" endIcon={<SendIcon />} disabled={disabled}>
        Send
      </Button>
    </Box>
  );
}

// =============================
// Chat POC Page
// =============================
export default function ChatPOC() {
  // 1) Fetch flows + sessions (no selection logic here)
  const { loading, flows, sessions, updateOrAddSession, deleteSession, refetchSessions } = useAgenticData();

  // 2) Page-level selection of the current conversation
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const currentSession: SessionSchema | null = useMemo(
    () => (currentSessionId ? sessions.find((s) => s.id === currentSessionId) ?? null : null),
    [currentSessionId, sessions],
  );

  // Default selection once data arrives
  useEffect(() => {
    if (currentSessionId) return;
    if (sessions.length > 0) setCurrentSessionId(sessions[0].id);
    else setCurrentSessionId(null); // draft
  }, [sessions, currentSessionId]);

  // 3) Persisted binding: which agent is used for the active session (or draft)
  const { agentId, setAgentForSession, migrateSessionId } = useSessionAgent(currentSessionId ?? "draft");
  const currentAgent: AgenticFlow | null = useMemo(
    () => flows.find((f) => f.name === agentId) ?? flows[0] ?? null,
    [flows, agentId],
  );

  // 4) Per-agent preferences (become runtime_context for each send)
  const { prefs, setSearchPolicy, setLibraries, updatePrefs } = useAgentPrefs(currentAgent?.name ?? null);

  // 5) Global user profile (system prompt)
  const { profile, setSystemPrompt } = useUserPrefs();
  const [profileOpen, setProfileOpen] = useState(false);

  // 6) History loader (authoritative list from server when session changes)
  const [fetchHistory] = useLazyGetSessionHistoryAgenticV1ChatbotSessionSessionIdHistoryGetQuery();

  // Helper: compute runtime_context from per-agent prefs + optional user profile
  const buildRuntimeContext = useCallback((): RuntimeContext => {
    const rc: RuntimeContext = {
      search_policy: (prefs.search_policy ?? "hybrid") as SearchPolicyName,
      selected_document_libraries_ids: prefs.selected_document_libraries_ids ?? [],
      selected_prompt_ids: prefs.selected_prompt_ids ?? null,
      selected_template_ids: prefs.selected_template_ids ?? null,
      // you can pass the global user system prompt as a contextual hint (backend index signature allows extra keys)
      user_system_prompt: profile.systemPrompt || undefined,
    };
    return rc;
  }, [prefs, profile.systemPrompt]);

  // UI actions
  const onNewConversation = () => {
    setCurrentSessionId(null); // draft
    // messages will be cleared by the socket controller's reset handler inside children
  };

  const onSelectSession = (s: SessionSchema) => {
    setCurrentSessionId(s.id);
  };

  const onSelectAgent = (flow: AgenticFlow) => {
    setAgentForSession(flow.name);
  };

  // -----------------------------
  // Render (with ChatSocketController)
  // -----------------------------
  if (loading || !currentAgent) {
    return (
      <Box sx={{ p: 3 }}>
        <Typography variant="body1">Loading chat…</Typography>
      </Box>
    );
  }

  return (
    <ChatSocketController
      currentSession={currentSession}
      currentAgenticFlow={currentAgent}
      onUpdateOrAddSession={(s) => {
        // Upsert the session (sidebar freshness)
        updateOrAddSession(s);
        // Focus this session in the UI if it isn't the current
        if (!currentSession || currentSession.id !== s.id) setCurrentSessionId(s.id);
      }}
      onBindDraftAgentToSessionId={(realId) => {
        // bind draft → real for per-session agent mapping
        migrateSessionId("draft", realId);
        setCurrentSessionId(realId);
      }}
    >
      {({ messages, waitResponse, send, reset, replaceAllMessages }) => {
        // Load history when session changes
        useEffect(() => {
          if (!currentSession?.id) {
            reset();
            return;
          }
          fetchHistory({ sessionId: currentSession.id })
            .unwrap()
            .then((serverMessages: ChatMessage[]) => {
              replaceAllMessages(serverMessages);
              // When history is first loaded for a "freshly-seen" session,
              // the controller parent will also bind draft if needed via onBindDraftAgentToSessionId
            })
            .catch((e) => console.error("[ChatPOC] history load failed:", e));
          // eslint-disable-next-line react-hooks/exhaustive-deps
        }, [currentSession?.id]);

        const onSendText = async (text: string) => {
          await send(text, buildRuntimeContext());
        };

        return (
          <Box sx={{ height: "100vh", display: "flex", flexDirection: "column" }}>
            {/* Top bar */}
            <AppBar position="static" elevation={0}>
              <Toolbar sx={{ gap: 2 }}>
                <Typography variant="h6" sx={{ flexGrow: 1 }}>
                  Fred — Chat
                </Typography>
                <Typography variant="body2" sx={{ opacity: 0.8 }}>
                  Agent: <b>{currentAgent.nickname ?? currentAgent.name}</b>
                </Typography>
                <Divider orientation="vertical" flexItem sx={{ mx: 2, opacity: 0.25 }} />
                <IconButton color="inherit" onClick={() => setProfileOpen(true)}>
                  <PersonIcon />
                </IconButton>
              </Toolbar>
            </AppBar>

            <Grid container sx={{ flex: 1, minHeight: 0 }}>
              {/* Left column — Agents + Conversations */}
              <Grid size={3} sx={{ borderRight: (t) => `1px solid ${t.palette.divider}`, minWidth: 260 }}>
                {/* Agents */}
                <Box sx={{ p: 1.5 }}>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>
                    Assistants
                  </Typography>
                  <Paper variant="outlined">
                    <List dense>
                      {flows.map((f) => {
                        const selected = f.name === currentAgent.name;
                        return (
                          <ListItemButton key={f.name} selected={selected} onClick={() => onSelectAgent(f)}>
                            <ListItemText
                              primary={f.nickname ?? f.name}
                              secondary={f.role}
                              secondaryTypographyProps={{ noWrap: true }}
                              primaryTypographyProps={{ fontWeight: selected ? 600 : 500 }}
                            />
                          </ListItemButton>
                        );
                      })}
                    </List>
                  </Paper>

                  {/* Per-agent prefs quick controls (POC) */}
                  <Box sx={{ mt: 1.5 }}>
                    <Typography variant="caption" sx={{ opacity: 0.7 }}>
                      Search policy
                    </Typography>
                    <Stack direction="row" spacing={1} sx={{ mt: 0.5, flexWrap: "wrap" }}>
                      {(["hybrid", "semantic", "strict"] as SearchPolicyName[]).map((p) => (
                        <Button
                          key={p}
                          size="small"
                          variant={prefs.search_policy === p ? "contained" : "outlined"}
                          onClick={() => setSearchPolicy(p)}
                        >
                          {p}
                        </Button>
                      ))}
                    </Stack>
                    {/* Example stub to set document libraries */}
                    {/* <Box sx={{ mt: 1 }}>
                      <Button size="small" onClick={() => setLibraries(["lib-123", "lib-xyz"])}>Use sample libraries</Button>
                    </Box> */}
                  </Box>
                </Box>

                <Divider />

                {/* Conversations */}
                <Box sx={{ p: 1.5 }}>
                  <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1 }}>
                    <Typography variant="subtitle2">Conversations</Typography>
                    <Button size="small" startIcon={<AddIcon />} onClick={onNewConversation}>
                      New
                    </Button>
                  </Box>

                  <Paper variant="outlined">
                    <List dense>
                      {/* Draft row */}
                      <ListItemButton selected={!currentSession} onClick={() => setCurrentSessionId(null)}>
                        <ListItemText primary="(Draft)" secondary="Not saved yet" />
                      </ListItemButton>

                      {sessions.map((s) => (
                        <ListItemButton key={s.id} selected={currentSession?.id === s.id} onClick={() => onSelectSession(s)}>
                          <ListItemText
                            primary={s.title ?? s.id}
                            secondary={new Date(s.updated_at).toLocaleString()}
                            secondaryTypographyProps={{ noWrap: true }}
                          />
                          {/* Optional delete button:
                          <IconButton edge="end" size="small" onClick={(e) => { e.stopPropagation(); deleteSession(s); }}>
                            <DeleteOutlineIcon fontSize="small" />
                          </IconButton> */}
                        </ListItemButton>
                      ))}
                    </List>
                  </Paper>
                </Box>
              </Grid>

              {/* Right column — Messages + Input */}
              <Grid size="grow" sx={{ minWidth: 0 }}>
                {/* Messages */}
                <Box sx={{ p: 2, height: "calc(100% - 90px)", overflowY: "auto" }}>
                  {messages.length === 0 && (
                    <Box sx={{ opacity: 0.6, textAlign: "center", mt: 6 }}>
                      <Typography variant="h6">Start a conversation</Typography>
                      <Typography variant="body2">Choose an assistant on the left and type your question below.</Typography>
                    </Box>
                  )}

                  <Stack spacing={1.25}>
                    {messages.map((m: ChatMessage, i: number) => (
                      <Box key={m.id ?? i} sx={{ maxWidth: 840 }}>
                        <Typography variant="caption" sx={{ opacity: 0.6 }}>
                          {m.role} — {new Date(m.created_at ?? Date.now()).toLocaleTimeString()}
                        </Typography>
                        <Paper variant="outlined" sx={{ p: 1, mt: 0.25, whiteSpace: "pre-wrap" }}>
                          {m.content}
                        </Paper>
                      </Box>
                    ))}
                  </Stack>
                </Box>

                {/* Input */}
                <Box sx={{ p: 2, borderTop: (t) => `1px solid ${t.palette.divider}` }}>
                  <SendBar disabled={waitResponse} onSend={onSendText} />
                </Box>
              </Grid>
            </Grid>

            {/* User profile dialog (global) */}
            <Dialog open={profileOpen} onClose={() => setProfileOpen(false)} fullWidth maxWidth="sm">
              <DialogTitle>User Profile</DialogTitle>
              <DialogContent dividers>
                <Typography variant="body2" sx={{ mb: 1, opacity: 0.7 }}>
                  System prompt (applies to all agents & conversations)
                </Typography>
                <TextField
                  fullWidth
                  multiline
                  minRows={4}
                  value={profile.systemPrompt}
                  onChange={(e) => setSystemPrompt(e.target.value)}
                  placeholder="e.g., You are a concise, trustworthy enterprise assistant…"
                />
              </DialogContent>
              <DialogActions>
                <Button onClick={() => setProfileOpen(false)}>Close</Button>
              </DialogActions>
            </Dialog>
          </Box>
        );
      }}
    </ChatSocketController>
  );
}

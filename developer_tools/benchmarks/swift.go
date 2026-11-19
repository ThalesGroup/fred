package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/url"
	"strings"
	"sync/atomic"
	"time"

	"nhooyr.io/websocket"
)

// sseExecuteRequest maps to RuntimeExecuteRequest. Exactly one of AgentID
// (direct template mode) or AgentInstanceID (managed mode, team comes from
// RuntimeContext.team_id) must be set — see RUNTIME-EXECUTION-CONTRACT.md §2.3.
type sseExecuteRequest struct {
	AgentID         string            `json:"agent_id,omitempty"`
	AgentInstanceID string            `json:"agent_instance_id,omitempty"`
	Input           string            `json:"input"`
	SessionID       string            `json:"session_id,omitempty"`
	RuntimeContext  map[string]string `json:"runtime_context,omitempty"`
}

// buildSSEExecuteRequest maps cfg + sessionID to the RuntimeExecuteRequest wire
// shape. Managed mode (AgentInstanceID set) sends agent_instance_id and never
// agent_id; direct mode (the historical behaviour) sends agent_id only.
func buildSSEExecuteRequest(cfg config, sessionID string) sseExecuteRequest {
	// runtime_context carries user_id so sessions are keyed per-user, not all under "unknown".
	runtimeCtx := map[string]string{"user_id": "bench"}
	if cfg.SSEUserID != "" {
		runtimeCtx["user_id"] = cfg.SSEUserID
	}
	if cfg.SSETeamID != "" {
		runtimeCtx["team_id"] = cfg.SSETeamID
	}

	body := sseExecuteRequest{
		Input:          cfg.Message,
		SessionID:      sessionID,
		RuntimeContext: runtimeCtx,
	}
	if cfg.AgentInstanceID != "" {
		// Managed mode: agent_instance_id + runtime_context.team_id, never agent_id
		// (RuntimeExecuteRequest requires exactly one of the two — RUNTIME-EXECUTION-CONTRACT.md §2.3).
		body.AgentInstanceID = cfg.AgentInstanceID
	} else {
		body.AgentID = cfg.AgentID
	}
	return body
}

// Swift owns session preparation and payload/event interpretation. There is no
// turn loop here, and no registry or speculative Weaver implementation.
type swiftAdapter struct {
	cfg           config
	http          *http.Client
	prepared      []string
	cleanupErrors atomic.Int64
}

func newSwiftAdapter(cfg config) *swiftAdapter {
	return &swiftAdapter{cfg: cfg, http: sseHTTPClient(cfg)}
}

func (a *swiftAdapter) Prepare(ctx context.Context) error {
	cfg := a.cfg
	if cfg.Protocol == "ws" && cfg.RequestsPerClient > 0 && cfg.SessionID == "" && cfg.CreateSession && cfg.PrepareSessions {
		var err error
		a.prepared, err = createSessions(ctx, cfg, cfg.Clients)
		return err
	}
	return nil
}

func (a *swiftAdapter) Close() {
	a.http.CloseIdleConnections()
	if a.cfg.DeleteSession {
		deleteSessions(a.cfg, a.prepared)
		a.prepared = nil
	}
}

type swiftConversation struct {
	adapter   *swiftAdapter
	sessionID string
	conn      *websocket.Conn
	created   bool
}

func (a *swiftAdapter) Open(ctx context.Context, client int) (conversation, error) {
	cfg := a.cfg
	c := &swiftConversation{adapter: a, sessionID: cfg.SessionID}
	if client < len(a.prepared) {
		c.sessionID = a.prepared[client]
	}
	if cfg.Protocol == "sse" {
		// Preserve historical total-request mode (no implicit stable session).
		if c.sessionID == "" && cfg.CreateSession && cfg.RequestsPerClient > 0 {
			c.sessionID = newExchangeID()
		}
		if cfg.Scenario == "conversation" && cfg.CredentialFile != "" && cfg.AgentInstanceID != "" {
			return c, c.register(ctx)
		}
		return c, nil
	}
	if c.sessionID == "" && cfg.CreateSession {
		id, err := createSession(ctx, cfg)
		if err != nil {
			return c, err
		}
		c.sessionID, c.created = id, true
	}
	endpoint, err := buildURL(cfg.URL, cfg.Token, cfg.TokenInQuery)
	if err != nil {
		return c, err
	}
	opts := &websocket.DialOptions{CompressionMode: websocket.CompressionDisabled, HTTPClient: a.http}
	if cfg.Token != "" && !cfg.TokenInQuery {
		opts.HTTPHeader = http.Header{"Authorization": []string{"Bearer " + cfg.Token}}
	}
	c.conn, _, err = websocket.Dial(ctx, endpoint, opts)
	if err == nil {
		applyConnReadLimit(c.conn, cfg)
	}
	return c, err
}

// The scenario registers the same locally generated ID as the managed UI. The
// shared engine opens once before turn timing; legacy Swift stays runtime-only.
func (a *swiftAdapter) sessionAPI() *weaverAdapter {
	cfg := a.cfg
	u, _ := url.Parse(cfg.URL) // scenarioSteps has validated the public execution URL.
	cfg.FredOrigin = u.Scheme + "://" + u.Host
	return &weaverAdapter{cfg: cfg, http: a.http}
}

func (c *swiftConversation) sessionPath() string {
	cfg := c.adapter.cfg
	return cfg.ControlPlanePath + "/teams/" + url.PathEscape(cfg.SSETeamID) + "/sessions"
}

func (c *swiftConversation) register(ctx context.Context) error {
	cfg := c.adapter.cfg
	body := struct {
		SessionID       string `json:"session_id"`
		AgentInstanceID string `json:"agent_instance_id"`
		Title           string `json:"title"`
	}{c.sessionID, cfg.AgentInstanceID, cfg.SessionTitle}
	var session struct {
		SessionID       string `json:"session_id"`
		TeamID          string `json:"team_id"`
		AgentInstanceID string `json:"agent_instance_id"`
	}
	status, err := c.adapter.sessionAPI().json(ctx, http.MethodPost, c.sessionPath(), body, &session)
	// A 201 proves ownership even if its body is invalid. Never reuse or clean up
	// an existing row on a collision, or retry an ambiguous failed POST.
	c.created = status == http.StatusCreated
	if err != nil {
		return err
	}
	if !c.created {
		return benchmarkError("session_not_created")
	}
	if session.SessionID != c.sessionID || session.TeamID != cfg.SSETeamID || session.AgentInstanceID != cfg.AgentInstanceID {
		return benchmarkError("invalid_session")
	}
	return nil
}

func (c *swiftConversation) ID() string { return c.sessionID }
func (c *swiftConversation) Execute(ctx context.Context) result {
	if c.adapter.cfg.Protocol == "sse" {
		return executeSwiftSSE(ctx, c.adapter.http, c.adapter.cfg, c.sessionID)
	}
	return runOverOpenConn(ctx, c.conn, c.adapter.cfg, c.sessionID)
}
func (c *swiftConversation) Close() { c.closeContext(context.Background()) }

func (c *swiftConversation) closeContext(parent context.Context) {
	if c.conn != nil {
		_ = c.conn.Close(websocket.StatusNormalClosure, "done")
	}
	if c.created && c.adapter.cfg.DeleteSession {
		ctx, cancel := context.WithTimeout(context.WithoutCancel(parent), c.adapter.cfg.Timeout)
		defer cancel()
		c.created = false
		if c.adapter.cfg.Protocol == "sse" {
			// CP owns the governed deletion window and runtime erasure. A 204
			// acknowledges deletion; it does not prove physical purge completion.
			status, err := c.adapter.sessionAPI().json(ctx, http.MethodDelete, c.sessionPath()+"/"+url.PathEscape(c.sessionID), nil, nil)
			if err != nil || status != http.StatusNoContent {
				c.adapter.cleanupErrors.Add(1)
			}
		} else {
			_ = deleteSession(ctx, c.adapter.cfg, c.sessionID)
		}
	}
}

func executeSwiftSSE(ctx context.Context, client *http.Client, cfg config, sessionID string) result {
	start := time.Now()
	body, err := json.Marshal(buildSSEExecuteRequest(cfg, sessionID))
	if err != nil {
		return result{Err: err, Measurement: turnMeasurement{StartedAt: start}}
	}
	endpoint, err := buildURL(cfg.URL, cfg.Token, cfg.TokenInQuery)
	if err != nil {
		return result{Err: err, Measurement: turnMeasurement{StartedAt: start}}
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, strings.NewReader(string(body)))
	if err != nil {
		return result{Err: err, Measurement: turnMeasurement{StartedAt: start}}
	}
	req.Header.Set("Content-Type", "application/json")
	injectTurnTrace(req)
	req.Header.Set("Accept", "text/event-stream")
	if cfg.Token != "" && !cfg.TokenInQuery {
		req.Header.Set("Authorization", "Bearer "+cfg.Token)
	}
	decoder := cfg.RuntimeDecoder
	if decoder == nil {
		decoder = decodeRuntimeEvent
	}
	res := executeSSE(client, req, start, decoder)
	if cfg.Scenario != "" {
		res.Measurement.ExecutionStartedAt = &start
	}
	return res
}

// Retained test entry point for Swift managed/direct payload compatibility.
func runSSEWithSession(cfg config, sessionID string) result {
	ctx, cancel := context.WithTimeout(context.Background(), cfg.Timeout)
	defer cancel()
	client := sseHTTPClient(cfg)
	defer client.CloseIdleConnections()
	return executeSwiftSSE(ctx, client, cfg, sessionID)
}

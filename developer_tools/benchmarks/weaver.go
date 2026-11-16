package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"sync/atomic"
	"time"
)

var canonicalPublicPath = regexp.MustCompile(`^/[A-Za-z0-9._~/-]+$`)
var canonicalUUID = regexp.MustCompile(`^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`)

// Match runtimeExecutionUrl.ts: only canonical, origin-relative paths with a
// nonempty mount. Never resolve absolute URLs supplied by discovery.
func weaverPublicPath(candidate, suffix string) bool {
	if !canonicalPublicPath.MatchString(candidate) || strings.Contains(candidate, "//") || !strings.HasSuffix(candidate, suffix) || candidate == suffix {
		return false
	}
	for _, segment := range strings.Split(candidate, "/") {
		if segment == "." || segment == ".." {
			return false
		}
	}
	return true
}

func validateWeaverConfig(cfg config) error {
	if cfg.Protocol != "sse" || cfg.RequestsPerClient <= 0 {
		return fmt.Errorf("weaver requires -protocol=sse and -requests-per-client>0")
	}
	u, err := url.Parse(cfg.FredOrigin)
	if err != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Hostname() == "" || u.User != nil || u.RawQuery != "" || u.ForceQuery || u.Fragment != "" || (u.Path != "" && u.Path != "/") {
		return fmt.Errorf("weaver requires -fred-origin as an HTTP(S) origin without credentials, query or path")
	}
	if !weaverPublicPath(cfg.ControlPlanePath+"/spaces", "/spaces") {
		return fmt.Errorf("weaver requires a canonical -control-plane-path mount")
	}
	if !canonicalUUID.MatchString(cfg.SpaceID) || !canonicalUUID.MatchString(cfg.AgentInstanceID) {
		return fmt.Errorf("weaver requires UUID -space-id and -agent-instance-id")
	}
	if cfg.Token == "" || strings.ContainsAny(cfg.Token, "\r\n") || cfg.AllowEmptyTok || cfg.TokenInQuery {
		return fmt.Errorf("weaver requires an existing user JWT via -token or AGENTIC_TOKEN; query/empty-token modes are unsupported")
	}
	if cfg.SessionID != "" && (!canonicalUUID.MatchString(cfg.SessionID) || cfg.Clients != 1) {
		return fmt.Errorf("weaver -session requires a UUID and exactly one client")
	}
	if !cfg.CreateSession && cfg.SessionID == "" {
		return fmt.Errorf("weaver requires session creation or an explicit -session")
	}
	if cfg.URL != "" || cfg.AgentID != "" || cfg.AgentUUID != "" || cfg.AgentCreateURL != "" || cfg.EnsureV2DefinitionRef != "" || cfg.EnsureV2ProfileID != "" || cfg.EnsureAgentName != "" || cfg.DeleteCreatedAgent || cfg.SessionURL != "" || cfg.PrepareSessions || cfg.SSEUserID != "" || cfg.SSETeamID != "" || cfg.DebugEvents || cfg.InsecureTLS || len(cfg.DocumentLibraryIDs) != 0 || len(cfg.DocumentUIDs) != 0 || cfg.SearchPolicy != "" || cfg.SearchRagScope != "" || cfg.IncludeSessionScope != nil || cfg.IncludeCorpusScope != nil {
		return fmt.Errorf("weaver does not support Swift endpoint, identity, bootstrap, preparation, TLS bypass or legacy runtime-context flags")
	}
	for _, name := range cfg.ExplicitFlags {
		switch name {
		case "url", "agent", "agent-uuid", "agent-create-url", "ensure-v2-definition-ref", "ensure-v2-profile-id", "ensure-agent-name", "delete-created-agent", "session-url", "prepare-sessions", "prepare-concurrency", "sse-user-id", "sse-team-id", "debug-events", "read-limit-bytes", "insecure", "token-in-query", "allow-empty-token", "requests", "document-library-ids", "document-uids", "search-policy", "search-rag-scope", "include-session-scope", "include-corpus-scope":
			return fmt.Errorf("-%s is unsupported for weaver", name)
		}
	}
	return nil
}

type weaverAdapter struct {
	cfg           config
	http          *http.Client
	cleanupErrors atomic.Int64
}

func newWeaverAdapter(cfg config) *weaverAdapter {
	return &weaverAdapter{cfg: cfg, http: sseHTTPClient(cfg)}
}
func (a *weaverAdapter) Close() { a.http.CloseIdleConnections() }
func (a *weaverAdapter) spacePath() string {
	return a.cfg.ControlPlanePath + "/spaces/" + a.cfg.SpaceID
}
func (a *weaverAdapter) instancePath() string {
	return a.spacePath() + "/agent-instances/" + a.cfg.AgentInstanceID
}
func (a *weaverAdapter) request(ctx context.Context, method, path string, body any) (*http.Request, error) {
	var data []byte
	var err error
	if body != nil {
		data, err = json.Marshal(body)
		if err != nil {
			return nil, err
		}
	}
	req, err := http.NewRequestWithContext(ctx, method, strings.TrimRight(a.cfg.FredOrigin, "/")+path, bytes.NewReader(data))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+a.cfg.Token)
	req.Header.Set("Content-Type", "application/json")
	injectTurnTrace(req)
	return req, nil
}

// Bound JSON reads and never expose upstream bodies or request URLs in errors.
func (a *weaverAdapter) json(ctx context.Context, method, path string, body, out any) (int, error) {
	req, err := a.request(ctx, method, path, body)
	if err != nil {
		return 0, err
	}
	resp, err := a.http.Do(req)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return resp.StatusCode, benchmarkError(fmt.Sprintf("http_%d", resp.StatusCode))
	}
	if out == nil {
		return resp.StatusCode, nil
	}
	const limit = 4 * 1024 * 1024
	data, err := io.ReadAll(io.LimitReader(resp.Body, limit+1))
	if err != nil {
		return resp.StatusCode, err
	}
	if len(data) > limit || json.Unmarshal(data, out) != nil {
		return resp.StatusCode, benchmarkError("invalid_response")
	}
	return resp.StatusCode, nil
}

type weaverBinding struct {
	SpaceID         string `json:"space_id"`
	AgentInstanceID string `json:"agent_instance_id"`
	Revision        int64  `json:"agent_configuration_revision"`
}

func (b weaverBinding) matches(cfg config, revision int64) bool {
	return b.SpaceID == cfg.SpaceID && b.AgentInstanceID == cfg.AgentInstanceID && b.Revision == revision && revision > 0
}

type weaverSession struct {
	weaverBinding
	SessionID   string `json:"session_id"`
	Changed     bool   `json:"agent_configuration_changed"`
	Deleted     bool   `json:"agent_deleted"`
	Disabled    bool   `json:"agent_disabled"`
	MessagesURL string `json:"messages_url"`
}

type weaverConversation struct {
	adapter   *weaverAdapter
	sessionID string
	revision  int64
	created   bool
}

func (a *weaverAdapter) Open(ctx context.Context, _ int) (conversation, error) {
	c := &weaverConversation{adapter: a, sessionID: a.cfg.SessionID}
	var instance struct {
		SpaceID         string `json:"space_id"`
		AgentInstanceID string `json:"agent_instance_id"`
		Revision        int64  `json:"configuration_revision"`
	}
	if _, err := a.json(ctx, http.MethodGet, a.instancePath(), nil, &instance); err != nil {
		return c, err
	}
	c.revision = instance.Revision
	if !(weaverBinding{instance.SpaceID, instance.AgentInstanceID, instance.Revision}).matches(a.cfg, c.revision) {
		return c, benchmarkError("invalid_binding")
	}
	var session weaverSession
	if c.sessionID == "" {
		var id [16]byte
		if _, err := rand.Read(id[:]); err != nil {
			return c, err
		}
		id[6], id[8] = (id[6]&0x0f)|0x40, (id[8]&0x3f)|0x80
		c.sessionID = fmt.Sprintf("%x-%x-%x-%x-%x", id[:4], id[4:6], id[6:8], id[8:10], id[10:])
		body := struct {
			SessionID       string `json:"session_id"`
			AgentInstanceID string `json:"agent_instance_id"`
			Revision        int64  `json:"agent_configuration_revision"`
			Title           string `json:"title"`
		}{c.sessionID, a.cfg.AgentInstanceID, c.revision, a.cfg.SessionTitle}
		status, err := a.json(ctx, http.MethodPost, a.spacePath()+"/sessions", body, &session)
		// Only 201 proves ownership by this run. A 200 must not reuse/delete a
		// pre-existing conversation, even in the improbable event of an ID collision.
		c.created = status == http.StatusCreated
		if err != nil {
			return c, err
		}
		if !c.created {
			return c, benchmarkError("session_not_created")
		}
	} else {
		if _, err := a.json(ctx, http.MethodGet, c.path(), nil, &session); err != nil {
			return c, err
		}
	}
	if !session.matches(a.cfg, c.revision) || session.SessionID != c.sessionID || session.Changed || session.Deleted || session.Disabled {
		return c, benchmarkError("invalid_session")
	}
	return c, nil
}
func (c *weaverConversation) ID() string   { return c.sessionID }
func (c *weaverConversation) path() string { return c.adapter.spacePath() + "/sessions/" + c.sessionID }
func (c *weaverConversation) Close() {
	if !c.created || !c.adapter.cfg.DeleteSession {
		return
	}
	c.created = false
	ctx, cancel := context.WithTimeout(context.Background(), c.adapter.cfg.Timeout)
	defer cancel()
	// Acceptance of asynchronous deletion is not proof of physical erasure.
	var receipt struct {
		TargetID   string `json:"target_id"`
		TargetKind string `json:"target_kind"`
		Status     string `json:"status"`
	}
	status, err := c.adapter.json(ctx, http.MethodDelete, c.path(), nil, &receipt)
	valid := receipt.TargetID == c.sessionID && receipt.TargetKind == "session" &&
		((status == http.StatusOK && receipt.Status == "completed") ||
			(status == http.StatusAccepted && (receipt.Status == "queued" || receipt.Status == "running")))
	if err != nil || !valid {
		c.adapter.cleanupErrors.Add(1)
	}
}

type weaverPreparation struct {
	weaverBinding
	Transport         string          `json:"execution_transport"`
	SupportsStreaming bool            `json:"supports_streaming"`
	StreamURL         string          `json:"execute_stream_url"`
	ModelError        json.RawMessage `json:"model_error"`
	Inference         *struct {
		Key struct {
			SourceID   string `json:"source_id"`
			UpstreamID string `json:"upstream_model_id"`
		} `json:"key"`
	} `json:"inference"`
}

func (c *weaverConversation) Execute(ctx context.Context) result {
	a := c.adapter
	prep := &phaseMeasurement{StartedAt: time.Now()}
	res := result{Measurement: turnMeasurement{StartedAt: prep.StartedAt, Preparation: prep}}
	var p weaverPreparation
	_, err := a.json(ctx, http.MethodPost, a.instancePath()+"/prepare-execution?session_id="+url.QueryEscape(c.sessionID), nil, &p)
	if err == nil {
		switch {
		case !p.matches(a.cfg, c.revision):
			err = benchmarkError("invalid_binding")
		case p.Transport != "sse" || !p.SupportsStreaming:
			err = benchmarkError("unsupported_transport")
		case len(p.ModelError) > 0 && string(p.ModelError) != "null":
			err = benchmarkError("model_unavailable")
		case p.Inference == nil || p.Inference.Key.SourceID == "" || p.Inference.Key.UpstreamID == "":
			err = benchmarkError("model_unavailable")
		case !weaverPublicPath(p.StreamURL, "/agents/execute/stream"):
			err = benchmarkError("invalid_execution_url")
		}
	}
	prep.finish(err)
	if err != nil {
		res.Err = err
		return res
	}
	body := sseExecuteRequest{AgentInstanceID: a.cfg.AgentInstanceID, Input: a.cfg.Message, SessionID: c.sessionID, RuntimeContext: map[string]string{"space_id": a.cfg.SpaceID}}
	req, err := a.request(ctx, http.MethodPost, p.StreamURL, body)
	if err != nil {
		res.Err = err
		return res
	}
	req.Header.Set("Accept", "text/event-stream")
	if err := ctx.Err(); err != nil {
		res.Err = err
		return res
	}
	executionStart := time.Now()
	decoder := a.cfg.RuntimeDecoder
	if decoder == nil {
		decoder = decodeRuntimeEvent
	}
	res = executeSSE(a.http, req, prep.StartedAt, decoder)
	res.Measurement.Preparation, res.Measurement.ExecutionStartedAt = prep, &executionStart
	if res.Err != nil || a.cfg.Scenario != "" {
		return res
	}
	// The session's public route is independent of the current execution route,
	// just as useSessionHistory reads SessionDetails.messages_url in the UI.
	history := &phaseMeasurement{StartedAt: time.Now()}
	res.Measurement.History = history
	var session weaverSession
	_, err = a.json(ctx, http.MethodGet, c.path(), nil, &session)
	if err == nil && (!session.matches(a.cfg, c.revision) || session.SessionID != c.sessionID) {
		err = benchmarkError("invalid_session")
	}
	suffix := "/agents/sessions/" + c.sessionID + "/messages"
	if err == nil && !weaverPublicPath(session.MessagesURL, suffix) {
		err = benchmarkError("history_unavailable")
	}
	if err == nil {
		var messages []json.RawMessage
		_, err = a.json(ctx, http.MethodGet, session.MessagesURL, nil, &messages)
		if err == nil && messages == nil {
			err = benchmarkError("invalid_history")
		}
		if err == nil {
			count := len(messages)
			res.Measurement.HistoryMessages = &count
		}
	}
	history.finish(err)
	res.Err = err
	return res
}

package main

import (
	"context"
	"crypto/rand"
	"crypto/tls"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"strings"
	"sync"
	"time"

	"nhooyr.io/websocket"
)

type askPayload struct {
	Type             string                 `json:"type,omitempty"`
	SessionID        string                 `json:"session_id,omitempty"`
	Message          string                 `json:"message"`
	AgentID          string                 `json:"agent_id,omitempty"`
	RuntimeContext   *runtimeContextPayload `json:"runtime_context,omitempty"`
	ClientExchangeID string                 `json:"client_exchange_id,omitempty"`
}

type runtimeContextPayload struct {
	SessionID                    string   `json:"session_id,omitempty"`
	SelectedDocumentLibrariesIDs []string `json:"selected_document_libraries_ids,omitempty"`
	SelectedDocumentUIDs         []string `json:"selected_document_uids,omitempty"`
	SearchPolicy                 string   `json:"search_policy,omitempty"`
	SearchRagScope               string   `json:"search_rag_scope,omitempty"`
	IncludeSessionScope          *bool    `json:"include_session_scope,omitempty"`
	IncludeCorpusScope           *bool    `json:"include_corpus_scope,omitempty"`
}

type eventEnvelope struct {
	Type    string          `json:"type"`
	Content json.RawMessage `json:"content"`
}

type createV2AgentPayload struct {
	Name          string `json:"name"`
	DefinitionRef string `json:"definition_ref,omitempty"`
	ProfileID     string `json:"profile_id,omitempty"`
}

type createdAgentResponse struct {
	ID string `json:"id"`
}

// runOverOpenConn sends one ask over an existing connection and waits for final.
func runOverOpenConn(ctx context.Context, conn *websocket.Conn, cfg config, sessionID string) (res result) {
	start := time.Now()
	res.Measurement.StartedAt = start

	payload := buildAskPayload(cfg, sessionID)
	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		res.Err = err
		return
	}

	if err := conn.Write(ctx, websocket.MessageText, payloadBytes); err != nil {
		res.Err = err
		return
	}

	for {
		_, msg, err := conn.Read(ctx)
		if err != nil {
			res.Err = err
			return
		}
		if cfg.DebugEvents {
			fmt.Println("WebSocket event received")
		}
		var env eventEnvelope
		if err := json.Unmarshal(msg, &env); err != nil {
			res.Err = benchmarkError("invalid_event")
			return
		}
		switch env.Type {
		case "stream", "final":
			var text string
			_ = json.Unmarshal(env.Content, &text)
			res.observe(streamEvent{Text: text != "", Final: env.Type == "final"})
			if env.Type == "final" {
				return
			}

		case "error":
			res.Err = benchmarkError("execution_error")
			return
		default:
			res.Err = benchmarkError("invalid_event")
			return
		}
	}
}

// buildAskPayload exists to keep the websocket request contract in one place.
// Usage: call before serializing an ask sent to `/chatbot/query/ws`.
func buildAskPayload(cfg config, sessionID string) askPayload {
	payload := askPayload{
		Type:             "ask",
		SessionID:        sessionID,
		Message:          cfg.Message,
		AgentID:          cfg.AgentID,
		ClientExchangeID: newExchangeID(),
	}
	if runtimeContext := buildRuntimeContextPayload(cfg, sessionID); runtimeContext != nil {
		payload.RuntimeContext = runtimeContext
	}
	return payload
}

// buildRuntimeContextPayload exists to pass retrieval-scoping hints to Rico.
// Usage: populate library filters or `search_rag_scope` to benchmark corpus search paths.
func buildRuntimeContextPayload(cfg config, sessionID string) *runtimeContextPayload {
	if sessionID == "" &&
		len(cfg.DocumentLibraryIDs) == 0 &&
		len(cfg.DocumentUIDs) == 0 &&
		cfg.SearchPolicy == "" &&
		cfg.SearchRagScope == "" &&
		cfg.IncludeSessionScope == nil &&
		cfg.IncludeCorpusScope == nil {
		return nil
	}

	return &runtimeContextPayload{
		SessionID:                    sessionID,
		SelectedDocumentLibrariesIDs: cfg.DocumentLibraryIDs,
		SelectedDocumentUIDs:         cfg.DocumentUIDs,
		SearchPolicy:                 cfg.SearchPolicy,
		SearchRagScope:               cfg.SearchRagScope,
		IncludeSessionScope:          cfg.IncludeSessionScope,
		IncludeCorpusScope:           cfg.IncludeCorpusScope,
	}
}

// applyConnReadLimit exists to let the benchmark receive larger RAG and MCP
// payloads without tripping the websocket library's conservative default cap.
// Usage: call immediately after each successful websocket dial.
func applyConnReadLimit(conn *websocket.Conn, cfg config) {
	if conn == nil || cfg.ReadLimitBytes <= 0 {
		return
	}
	conn.SetReadLimit(cfg.ReadLimitBytes)
}

func buildURL(rawURL, token string, tokenInQuery bool) (string, error) {
	if !tokenInQuery || token == "" {
		return rawURL, nil
	}
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return "", err
	}
	query := parsed.Query()
	query.Set("token", token)
	parsed.RawQuery = query.Encode()
	return parsed.String(), nil
}

func urlHasToken(rawURL string) bool {
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return false
	}
	return parsed.Query().Get("token") != ""
}

func newExchangeID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		return fmt.Sprintf("ex-%d", time.Now().UnixNano())
	}
	return hex.EncodeToString(b[:])
}

// shouldEnsureV2Agent exists so an explicit benchmark target agent always wins
// over the bench bootstrap flow. Use it before creating or deleting temporary
// agents. Example: `if shouldEnsureV2Agent(cfg) { ... }`.
func shouldEnsureV2Agent(cfg config) bool {
	if strings.TrimSpace(cfg.AgentUUID) != "" {
		return false
	}
	return cfg.EnsureV2DefinitionRef != "" || cfg.EnsureV2ProfileID != ""
}

// ensureV2Agent exists to create one dynamic v2 agent before the benchmark so
// the load test can hit a real v2 RAG runtime instead of a v1 fallback.
// Usage: pass either `-ensure-v2-definition-ref` or `-ensure-v2-profile-id`.
func ensureV2Agent(cfg config) (string, error) {
	agentCreateURL, err := getAgentCreateURL(cfg)
	if err != nil {
		return "", err
	}

	payload := createV2AgentPayload{
		Name:          cfg.EnsureAgentName,
		DefinitionRef: cfg.EnsureV2DefinitionRef,
		ProfileID:     cfg.EnsureV2ProfileID,
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}

	ctx, cancel := context.WithTimeout(context.Background(), cfg.Timeout)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, agentCreateURL, strings.NewReader(string(body)))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	if cfg.Token != "" {
		req.Header.Set("Authorization", "Bearer "+cfg.Token)
	}

	client := &http.Client{}
	if cfg.InsecureTLS {
		client.Transport = &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
		}
	}

	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", fmt.Errorf("create v2 agent failed: %s", resp.Status)
	}

	var created createdAgentResponse
	if err := json.NewDecoder(resp.Body).Decode(&created); err != nil {
		return "", err
	}
	if created.ID == "" {
		return "", fmt.Errorf("create v2 agent returned empty id")
	}
	return created.ID, nil
}

// parseCSVFlag exists to keep list-style benchmark flags compact for CLI and
// Helm usage. Example: `-document-library-ids=lib-a,lib-b`.
func parseCSVFlag(raw string) []string {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return nil
	}
	parts := strings.Split(trimmed, ",")
	values := make([]string, 0, len(parts))
	for _, part := range parts {
		value := strings.TrimSpace(part)
		if value != "" {
			values = append(values, value)
		}
	}
	if len(values) == 0 {
		return nil
	}
	return values
}

// parseOptionalBoolFlag exists because runtime_context booleans need a tri-state:
// unset, true, or false. Example: `-include-corpus-scope=false`.
func parseOptionalBoolFlag(raw string) *bool {
	trimmed := strings.TrimSpace(strings.ToLower(raw))
	if trimmed == "" {
		return nil
	}
	value := trimmed == "true"
	return &value
}

func createSession(ctx context.Context, cfg config) (string, error) {
	sessionURL, err := getSessionURL(cfg)
	if err != nil {
		return "", err
	}

	payload := map[string]string{
		"agent_id": cfg.AgentID,
		"title":    cfg.SessionTitle,
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, sessionURL, strings.NewReader(string(body)))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	if cfg.Token != "" {
		req.Header.Set("Authorization", "Bearer "+cfg.Token)
	}

	client := &http.Client{}
	if cfg.InsecureTLS {
		client.Transport = &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
		}
	}

	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", fmt.Errorf("create session failed: %s", resp.Status)
	}

	var session struct {
		ID string `json:"id"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&session); err != nil {
		return "", err
	}
	if session.ID == "" {
		return "", fmt.Errorf("create session returned empty id")
	}
	return session.ID, nil
}

// deleteAgent exists to clean up an agent created only for one benchmark run.
// Usage: enable with `-delete-created-agent=true` when the bench creates a v2 agent.
func deleteAgent(ctx context.Context, cfg config, agentID string) error {
	deleteURL, err := getAgentDeleteURL(cfg, agentID)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, deleteURL, nil)
	if err != nil {
		return err
	}
	if cfg.Token != "" {
		req.Header.Set("Authorization", "Bearer "+cfg.Token)
	}

	client := &http.Client{}
	if cfg.InsecureTLS {
		client.Transport = &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
		}
	}

	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("delete agent failed: %s", resp.Status)
	}
	return nil
}

func createSessions(ctx context.Context, cfg config, count int) ([]string, error) {
	if count <= 0 {
		return []string{}, nil
	}
	type sessionResult struct {
		index int
		id    string
		err   error
	}
	ids := make([]string, count)
	results := make(chan sessionResult, count)
	jobs := make(chan int)
	workers := minInt(count, cfg.PrepareConcurrency)
	if workers < 1 {
		workers = 1
	}
	var wg sync.WaitGroup
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for idx := range jobs {
				if ctx.Err() != nil {
					return
				}
				requestCtx, cancel := context.WithTimeout(ctx, cfg.Timeout)
				id, err := createSession(requestCtx, cfg)
				cancel()
				results <- sessionResult{index: idx, id: id, err: err}
			}
		}()
	}
dispatch:
	for i := 0; i < count; i++ {
		select {
		case <-ctx.Done():
			break dispatch
		case jobs <- i:
		}
	}
	close(jobs)
	wg.Wait()
	close(results)

	firstErr := ctx.Err()
	for res := range results {
		if res.err != nil && firstErr == nil {
			firstErr = res.err
		}
		ids[res.index] = res.id
	}
	if firstErr != nil {
		return ids, firstErr
	}
	return ids, nil
}

func deleteSession(ctx context.Context, cfg config, sessionID string) error {
	deleteURL, err := getSessionDeleteURL(cfg, sessionID)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, deleteURL, nil)
	if err != nil {
		return err
	}
	if cfg.Token != "" {
		req.Header.Set("Authorization", "Bearer "+cfg.Token)
	}

	client := &http.Client{}
	if cfg.InsecureTLS {
		client.Transport = &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
		}
	}

	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("delete session failed: %s", resp.Status)
	}
	return nil
}

func deleteSessions(cfg config, sessionIDs []string) {
	if len(sessionIDs) == 0 {
		return
	}
	// Cleanup survives load cancellation but shares one bounded budget.
	ctx, cancel := context.WithTimeout(context.Background(), cfg.Timeout)
	defer cancel()
	jobs := make(chan string)
	workers := minInt(len(sessionIDs), cfg.PrepareConcurrency)
	if workers < 1 {
		workers = 1
	}
	var wg sync.WaitGroup
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for id := range jobs {
				if ctx.Err() != nil {
					return
				}
				if err := deleteSession(ctx, cfg, id); err != nil {
					fmt.Fprintf(os.Stderr, "delete session failed: %s\n", classifyError(err))
				}
			}
		}()
	}
dispatch:
	for _, id := range sessionIDs {
		if id == "" {
			continue
		}
		select {
		case <-ctx.Done():
			break dispatch
		case jobs <- id:
		}
	}
	close(jobs)
	wg.Wait()
}

func getSessionURL(cfg config) (string, error) {
	if cfg.SessionURL != "" {
		return cfg.SessionURL, nil
	}
	return deriveSessionURL(cfg.URL)
}

// getAgentCreateURL exists to derive the agent management endpoint from the
// websocket target so the benchmark can bootstrap a dynamic v2 agent itself.
// Usage: override with `-agent-create-url` when the default path is not correct.
func getAgentCreateURL(cfg config) (string, error) {
	if cfg.AgentCreateURL != "" {
		return cfg.AgentCreateURL, nil
	}
	parsed, err := url.Parse(cfg.URL)
	if err != nil {
		return "", err
	}
	switch parsed.Scheme {
	case "ws":
		parsed.Scheme = "http"
	case "wss":
		parsed.Scheme = "https"
	}
	replacements := []string{
		"/chatbot/query/ws-baseline",
		"/chatbot/query/ws",
	}
	for _, old := range replacements {
		if strings.Contains(parsed.Path, old) {
			parsed.Path = strings.Replace(parsed.Path, old, "/agents/v2/create", 1)
			return parsed.String(), nil
		}
	}
	return "", fmt.Errorf("cannot derive agent create URL from %s (set -agent-create-url)", cfg.URL)
}

// getAgentDeleteURL exists to address the delete endpoint for one benchmark-
// created agent after the run completes.
// Usage: only used when `-delete-created-agent=true`.
func getAgentDeleteURL(cfg config, agentID string) (string, error) {
	createURL, err := getAgentCreateURL(cfg)
	if err != nil {
		return "", err
	}
	parsed, err := url.Parse(createURL)
	if err != nil {
		return "", err
	}
	parsed.Path = strings.TrimSuffix(parsed.Path, "/v2/create") + "/" + agentID
	return parsed.String(), nil
}

func getSessionDeleteURL(cfg config, sessionID string) (string, error) {
	base, err := getSessionURL(cfg)
	if err != nil {
		return "", err
	}
	parsed, err := url.Parse(base)
	if err != nil {
		return "", err
	}
	parsed.Path = strings.TrimRight(parsed.Path, "/") + "/" + sessionID
	return parsed.String(), nil
}

func deriveSessionURL(wsURL string) (string, error) {
	parsed, err := url.Parse(wsURL)
	if err != nil {
		return "", err
	}
	switch parsed.Scheme {
	case "ws":
		parsed.Scheme = "http"
	case "wss":
		parsed.Scheme = "https"
	}

	// Support both main and baseline websocket routes.
	replacements := []string{
		"/chatbot/query/ws-baseline",
		"/chatbot/query/ws",
	}
	for _, old := range replacements {
		if strings.Contains(parsed.Path, old) {
			parsed.Path = strings.Replace(parsed.Path, old, "/chatbot/session", 1)
			return parsed.String(), nil
		}
	}

	return "", fmt.Errorf("cannot derive session URL from %s (set -session-url)", wsURL)
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}

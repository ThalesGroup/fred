package main

import (
	"bufio"
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

// sseExecuteRequest maps to RuntimeExecuteRequest (direct agent_id mode, no grant required).
// Use agent_id for dev/bench; production frontends use agent_instance_id + execution_grant.
type sseExecuteRequest struct {
	AgentID        string            `json:"agent_id,omitempty"`
	Input          string            `json:"input"`
	SessionID      string            `json:"session_id,omitempty"`
	RuntimeContext map[string]string `json:"runtime_context,omitempty"`
}

// sseEvent covers both normal events (have "kind") and execution errors (have "error", no "kind").
// Normal error path: runtime yields {"error": "..."} on unhandled exceptions (no kind field).
// Structured events: all carry a "kind" discriminator per RuntimeEventKind.
type sseEvent struct {
	Kind  string `json:"kind"`
	Error string `json:"error,omitempty"`
}

// sseMaxLineBytes is the scanner buffer ceiling.
// RAG tool results or large final.content can exceed 64 KB (the bufio default).
const sseMaxLineBytes = 2 * 1024 * 1024 // 2 MB

func sseHTTPClient(cfg config) *http.Client {
	if cfg.InsecureTLS {
		return &http.Client{
			Transport: &http.Transport{
				TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
			},
		}
	}
	return &http.Client{}
}

func runSSEOnce(cfg config) result {
	return runSSEWithSession(cfg, cfg.SessionID)
}

func runSSEWithSession(cfg config, sessionID string) result {
	start := time.Now()
	ctx, cancel := context.WithTimeout(context.Background(), cfg.Timeout)
	defer cancel()

	// runtime_context carries user_id so sessions are keyed per-user, not all under "unknown".
	runtimeCtx := map[string]string{"user_id": "bench"}
	if cfg.SSEUserID != "" {
		runtimeCtx["user_id"] = cfg.SSEUserID
	}
	if cfg.SSETeamID != "" {
		runtimeCtx["team_id"] = cfg.SSETeamID
	}

	body := sseExecuteRequest{
		AgentID:        cfg.AgentID,
		Input:          cfg.Message,
		SessionID:      sessionID,
		RuntimeContext: runtimeCtx,
	}
	bodyBytes, err := json.Marshal(body)
	if err != nil {
		return result{Err: err}
	}

	urlStr, err := buildURL(cfg.URL, cfg.Token, cfg.TokenInQuery)
	if err != nil {
		return result{Err: err}
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, urlStr, strings.NewReader(string(bodyBytes)))
	if err != nil {
		return result{Err: err}
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")
	if cfg.Token != "" && !cfg.TokenInQuery {
		req.Header.Set("Authorization", "Bearer "+cfg.Token)
	}

	resp, err := sseHTTPClient(cfg).Do(req)
	if err != nil {
		return result{Err: err}
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return result{Err: fmt.Errorf("HTTP %d", resp.StatusCode)}
	}

	scanner := bufio.NewScanner(resp.Body)
	scanner.Buffer(make([]byte, sseMaxLineBytes), sseMaxLineBytes)

	for scanner.Scan() {
		line := scanner.Text()
		if cfg.DebugEvents {
			fmt.Printf("sse raw: %s\n", line)
		}
		if !strings.HasPrefix(line, "data: ") {
			continue
		}
		raw := line[len("data: "):]
		var evt sseEvent
		if err := json.Unmarshal([]byte(raw), &evt); err != nil {
			continue
		}
		// Execution crash: runtime yields {"error": "..."} with no kind field.
		if evt.Error != "" {
			return result{Err: fmt.Errorf("agent error: %s", evt.Error)}
		}
		if evt.Kind == "final" {
			return result{Duration: time.Since(start)}
		}
	}
	if err := scanner.Err(); err != nil {
		return result{Err: err}
	}
	return result{Err: fmt.Errorf("stream closed before final event")}
}

// runSSEClientPersistent runs multiple SSE requests reusing the same session_id.
// Sessions are implicit in fred-runtime: a stable UUID is enough, no HTTP create/delete API.
func runSSEClientPersistent(cfg config, sessionID string) []result {
	results := make([]result, 0, maxInt(1, cfg.RequestsPerClient))

	if sessionID == "" && cfg.CreateSession {
		sessionID = newExchangeID()
	}

	for i := 0; i < cfg.RequestsPerClient; i++ {
		res := runSSEWithSession(cfg, sessionID)
		results = append(results, res)
		if res.Err != nil {
			break
		}
	}

	return results
}

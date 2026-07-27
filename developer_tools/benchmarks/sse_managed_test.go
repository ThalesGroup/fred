package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"
)

// TestRunSSEWithSession_NodeErrorThenFinal proves node_error is NOT terminal:
// the client must keep reading past it and report success once final arrives.
func TestRunSSEWithSession_NodeErrorThenFinal(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
		flusher, ok := w.(http.Flusher)
		if !ok {
			t.Fatal("test server does not support flushing")
		}
		fmt.Fprintf(w, "data: %s\n\n", `{"kind":"node_error","node_id":"tool_x","error_message":"transient failure","routed_to":"retry"}`)
		flusher.Flush()
		fmt.Fprintf(w, "data: %s\n\n", `{"kind":"final","content":"done"}`)
		flusher.Flush()
	}))
	defer server.Close()

	cfg := config{
		URL:     server.URL,
		Message: "hello",
		Timeout: 5 * time.Second,
	}

	res := runSSEWithSession(cfg, "session-1")
	if res.Err != nil {
		t.Fatalf("expected success after node_error -> final, got error: %v", res.Err)
	}
}

func TestBuildSSEExecuteRequest_Direct(t *testing.T) {
	cfg := config{
		AgentID: "Georges",
		Message: "hello",
	}
	body := buildSSEExecuteRequest(cfg, "session-1")

	raw, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal failed: %v", err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}

	if decoded["agent_id"] != "Georges" {
		t.Errorf("expected agent_id %q, got %v", "Georges", decoded["agent_id"])
	}
	if _, present := decoded["agent_instance_id"]; present {
		t.Errorf("direct payload must not contain agent_instance_id, got %v", decoded["agent_instance_id"])
	}
}

func TestBuildSSEExecuteRequest_Managed(t *testing.T) {
	cfg := config{
		AgentInstanceID: "inst-42",
		SSETeamID:       "personal-admin",
		Message:         "hello",
	}
	body := buildSSEExecuteRequest(cfg, "session-1")

	raw, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal failed: %v", err)
	}
	var decoded map[string]any
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}

	if decoded["agent_instance_id"] != "inst-42" {
		t.Errorf("expected agent_instance_id %q, got %v", "inst-42", decoded["agent_instance_id"])
	}
	if _, present := decoded["agent_id"]; present {
		t.Errorf("managed payload must not contain agent_id, got %v", decoded["agent_id"])
	}

	runtimeContext, ok := decoded["runtime_context"].(map[string]any)
	if !ok {
		t.Fatalf("expected runtime_context object, got %v", decoded["runtime_context"])
	}
	if runtimeContext["team_id"] != "personal-admin" {
		t.Errorf("expected runtime_context.team_id %q, got %v", "personal-admin", runtimeContext["team_id"])
	}
}

func TestValidateConfig_ManagedRequiresTeamID(t *testing.T) {
	cfg := config{
		Protocol:        "sse",
		AgentInstanceID: "inst-42",
	}
	if err := validateConfig(cfg); err == nil {
		t.Fatal("expected an error when managed mode is missing -sse-team-id")
	}
}

func TestValidateConfig_ManagedRequiresSSEProtocol(t *testing.T) {
	cfg := config{
		Protocol:        "ws",
		AgentInstanceID: "inst-42",
		SSETeamID:       "personal-admin",
	}
	if err := validateConfig(cfg); err == nil {
		t.Fatal("expected an error when -agent-instance-id is combined with -protocol=ws")
	}
}

func TestValidateConfig_ManagedWithSSEAndTeamIDPasses(t *testing.T) {
	cfg := config{
		Protocol:        "sse",
		AgentInstanceID: "inst-42",
		SSETeamID:       "personal-admin",
	}
	if err := validateConfig(cfg); err != nil {
		t.Fatalf("expected no error for valid managed config, got %v", err)
	}
}

func TestValidateConfig_DirectModeUnaffected(t *testing.T) {
	cfg := config{
		Protocol: "ws",
		AgentID:  "Georges",
	}
	if err := validateConfig(cfg); err != nil {
		t.Fatalf("expected no error for historical direct/ws config, got %v", err)
	}

	sseCfg := config{
		Protocol: "sse",
		AgentID:  "Georges",
	}
	if err := validateConfig(sseCfg); err != nil {
		t.Fatalf("expected no error for historical direct SSE config, got %v", err)
	}
}

func TestValidateConfig_AgentUUIDUnaffected(t *testing.T) {
	// -agent-uuid belongs to the WS existing-agent mode and must not be rejected
	// by the SSE managed-mode validation.
	cfg := config{
		Protocol:  "ws",
		AgentUUID: "6451efbb-2a9b-4792-8e3a-9bee05af7dd0",
	}
	if err := validateConfig(cfg); err != nil {
		t.Fatalf("expected no error, -agent-uuid is unrelated to managed SSE mode: %v", err)
	}
}

func TestPrintConfigRecap_NeverPrintsToken(t *testing.T) {
	const secretToken = "super-secret-jwt-value-should-not-leak"
	cfg := config{
		Protocol:        "sse",
		AgentInstanceID: "inst-42",
		SSETeamID:       "personal-admin",
		Token:           secretToken,
		SessionTitle:    "Benchmark",
		Timeout:         30,
	}

	output := captureStdout(t, func() {
		printConfigRecap(cfg, true, 1, 1)
	})

	if strings.Contains(output, secretToken) {
		t.Fatalf("config recap leaked the bearer token: %s", output)
	}
}

func TestPrintSummary_NeverPrintsToken(t *testing.T) {
	const secretToken = "super-secret-jwt-value-should-not-leak"
	cfg := config{
		Protocol:        "sse",
		AgentInstanceID: "inst-42",
		SSETeamID:       "personal-admin",
		Token:           secretToken,
	}

	output := captureStdout(t, func() {
		printSummary(cfg, 1, nil, 1, []string{"boom"}, 0)
	})

	if strings.Contains(output, secretToken) {
		t.Fatalf("summary leaked the bearer token: %s", output)
	}
	if !strings.Contains(output, "managed") {
		t.Errorf("summary must show SSE mode managed, got: %s", output)
	}
	if !strings.Contains(output, "personal-admin") {
		t.Errorf("summary must show the team ID, got: %s", output)
	}
}

func TestBuildJSONReport_ManagedAndRedacted(t *testing.T) {
	const (
		secretToken = "super-secret-jwt-value-should-not-leak"
		prompt      = "private benchmark prompt"
	)
	cfg := config{
		Protocol:          "sse",
		URL:               "http://127.0.0.1:8000/execute?token=" + secretToken,
		AgentInstanceID:   "inst-42",
		SSETeamID:         "personal-admin",
		Token:             secretToken,
		Message:           prompt,
		Clients:           5,
		RequestsPerClient: 3,
	}

	report := buildJSONReport(
		cfg,
		15,
		[]time.Duration{100 * time.Millisecond, 200 * time.Millisecond, 300 * time.Millisecond},
		1,
		[]string{"request failed for " + prompt + " using " + secretToken},
		time.Second,
	)

	if report.SSEMode != "managed" || report.AgentInstanceID != "inst-42" || report.TeamID != "personal-admin" {
		t.Fatalf("managed SSE identity missing from report: %+v", report)
	}
	if report.TotalRequests != 15 || report.Success != 3 || report.Errors != 1 {
		t.Fatalf("unexpected request counts: %+v", report)
	}
	if report.Latency == nil || report.Latency.P50 != 200 {
		t.Fatalf("unexpected latency summary: %+v", report.Latency)
	}

	raw, err := json.Marshal(report)
	if err != nil {
		t.Fatalf("marshal failed: %v", err)
	}
	for _, forbidden := range []string{secretToken, prompt} {
		if strings.Contains(string(raw), forbidden) {
			t.Fatalf("JSON report leaked %q: %s", forbidden, raw)
		}
	}
}

func TestWriteJSONReport(t *testing.T) {
	path := t.TempDir() + "/nested/report.json"
	report := benchmarkJSONReport{
		SchemaVersion: "v1",
		Outcome:       "OK",
		Protocol:      "sse",
	}

	if err := writeJSONReport(path, report); err != nil {
		t.Fatalf("write JSON report: %v", err)
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read JSON report: %v", err)
	}
	var decoded benchmarkJSONReport
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatalf("decode JSON report: %v", err)
	}
	if decoded.SchemaVersion != "v1" || decoded.Outcome != "OK" {
		t.Fatalf("unexpected decoded report: %+v", decoded)
	}
}

func captureStdout(t *testing.T, fn func()) string {
	t.Helper()
	old := os.Stdout
	r, w, err := os.Pipe()
	if err != nil {
		t.Fatalf("failed to create pipe: %v", err)
	}
	os.Stdout = w

	fn()

	if err := w.Close(); err != nil {
		t.Fatalf("failed to close pipe writer: %v", err)
	}
	os.Stdout = old

	var buf bytes.Buffer
	if _, err := io.Copy(&buf, r); err != nil {
		t.Fatalf("failed to read pipe: %v", err)
	}
	return buf.String()
}

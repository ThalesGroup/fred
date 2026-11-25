package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strings"
	"sync"
	"testing"
	"time"
)

const testSpace = "11111111-1111-4111-8111-111111111111"
const testInstance = "22222222-2222-4222-8222-222222222222"
const testSession = "33333333-3333-4333-8333-333333333333"

type weaverCall struct {
	Method, Path, Session string
	Body                  map[string]any
}
type weaverFixture struct {
	t        *testing.T
	server   *httptest.Server
	cfg      config
	mu       sync.Mutex
	calls    []weaverCall
	turns    map[string]int
	override func(http.ResponseWriter, *http.Request, string, map[string]any) bool
}

func newWeaverFixture(t *testing.T) *weaverFixture {
	t.Helper()
	f := &weaverFixture{t: t, turns: make(map[string]int)}
	f.cfg = config{Target: "weaver", Protocol: "sse", ControlPlanePath: "/control-plane/v1", SpaceID: testSpace, AgentInstanceID: testInstance, Token: "private-test-token", Message: "private-test-prompt", Clients: 1, RequestsPerClient: 2, CreateSession: true, DeleteSession: true, Timeout: time.Second, SessionTitle: "Benchmark"}
	f.server = httptest.NewServer(http.HandlerFunc(f.serve))
	f.cfg.FredOrigin = f.server.URL
	t.Cleanup(f.server.Close)
	return f
}
func (f *weaverFixture) setOverride(fn func(http.ResponseWriter, *http.Request, string, map[string]any) bool) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.override = fn
}

func (f *weaverFixture) session(id string) map[string]any {
	return map[string]any{"session_id": id, "space_id": testSpace, "agent_instance_id": testInstance, "agent_configuration_revision": 7, "messages_url": "/runtime/agents/sessions/" + id + "/messages"}
}
func (f *weaverFixture) preparation() map[string]any {
	return map[string]any{"space_id": testSpace, "agent_instance_id": testInstance, "agent_configuration_revision": 7, "execution_transport": "sse", "supports_streaming": true, "execute_stream_url": "/runtime/agents/execute/stream", "model_error": nil, "inference": map[string]any{"key": map[string]any{"source_id": "test-source", "upstream_model_id": "test-model"}}}
}
func (f *weaverFixture) serve(w http.ResponseWriter, r *http.Request) {
	if r.Header.Get("Authorization") != "Bearer "+f.cfg.Token {
		f.t.Error("incorrect authorization")
	}
	var body map[string]any
	if r.Body != nil {
		_ = json.NewDecoder(r.Body).Decode(&body)
	}
	id, _ := body["session_id"].(string)
	path := r.URL.Path
	phase := ""
	switch {
	case strings.HasSuffix(path, "/prepare-execution"):
		phase = "prepare"
		id = r.URL.Query().Get("session_id")
	case strings.HasSuffix(path, "/agent-instances/"+testInstance):
		phase = "instance"
	case strings.HasSuffix(path, "/agents/execute/stream"):
		phase = "execute"
	case strings.HasSuffix(path, "/messages"):
		phase = "history"
		id = strings.Split(path, "/")[4]
	case strings.HasSuffix(path, "/sessions"):
		phase = "register"
	default:
		id = path[strings.LastIndex(path, "/")+1:]
		phase = "session"
		if r.Method == http.MethodDelete {
			phase = "delete"
		}
	}
	f.mu.Lock()
	f.calls = append(f.calls, weaverCall{r.Method, phase, id, body})
	f.mu.Unlock()
	f.mu.Lock()
	override := f.override
	f.mu.Unlock()
	if override != nil && override(w, r, phase, body) {
		return
	}
	w.Header().Set("Content-Type", "application/json")
	var response any
	switch phase {
	case "instance":
		response = map[string]any{"space_id": testSpace, "agent_instance_id": testInstance, "configuration_revision": 7}
	case "register":
		w.WriteHeader(201)
		response = f.session(id)
	case "session":
		response = f.session(id)
	case "prepare":
		response = f.preparation()
	case "execute":
		w.Header().Set("Content-Type", "text/event-stream")
		fmt.Fprint(w, "data: {\"kind\":\"status\"}\n\ndata: {\"kind\":\"assistant_delta\",\"delta\":\"answer\"}\n\ndata: {\"kind\":\"final\",\"content\":\"answer\"}\n\n")
		f.mu.Lock()
		f.turns[id]++
		f.mu.Unlock()
		return
	case "history":
		f.mu.Lock()
		count := f.turns[id]
		f.mu.Unlock()
		rows := make([]map[string]any, 0, count*2)
		for i := 0; i < count; i++ {
			rows = append(rows, map[string]any{"role": "user", "exchange_id": fmt.Sprint(i)}, map[string]any{"role": "assistant", "exchange_id": fmt.Sprint(i)})
		}
		response = rows
	case "delete":
		w.WriteHeader(202)
		response = map[string]any{"status": "queued", "target_kind": "session", "target_id": id}
	}
	_ = json.NewEncoder(w).Encode(response)
}
func (f *weaverFixture) run() ([]result, *weaverAdapter) {
	a := newWeaverAdapter(f.cfg)
	f.t.Cleanup(a.Close)
	results := runLoad(context.Background(), loadPlan{Clients: f.cfg.Clients, Turns: f.cfg.RequestsPerClient, Timeout: f.cfg.Timeout}, a.Open)
	return results, a
}
func (f *weaverFixture) snapshot() []weaverCall {
	f.mu.Lock()
	defer f.mu.Unlock()
	return append([]weaverCall(nil), f.calls...)
}

func TestWeaverTwoTurnsAndClientIsolation(t *testing.T) {
	f := newWeaverFixture(t)
	f.cfg.Clients = 2
	if err := validateConfig(f.cfg); err != nil {
		t.Fatal(err)
	}
	results, a := f.run()
	if len(results) != 4 || a.cleanupErrors.Load() != 0 {
		t.Fatalf("results=%d cleanup=%d", len(results), a.cleanupErrors.Load())
	}
	identities := map[int]string{}
	for _, r := range results {
		m := r.Measurement
		if r.Err != nil || m.Preparation == nil || m.Preparation.Error != "" || m.ExecutionStartedAt == nil || m.FirstTextAt == nil || m.FinalAt == nil || m.StreamClosedAt == nil || m.History == nil || m.HistoryMessages == nil || *m.HistoryMessages != m.Turn*2 {
			t.Fatalf("bad observations: %+v, err=%v", m, r.Err)
		}
		if m.Preparation.StartedAt != m.StartedAt || m.Preparation.FinishedAt.After(*m.ExecutionStartedAt) || m.ExecutionStartedAt.After(*m.FirstTextAt) || m.FinalAt.After(*m.StreamClosedAt) || m.StreamClosedAt.After(m.History.StartedAt) {
			t.Fatalf("unordered observations: %+v", m)
		}
		if r.Duration != m.FinalAt.Sub(m.StartedAt) {
			t.Fatal("summary is not attempt-to-final")
		}
		if previous := identities[m.ClientID]; previous != "" && previous != m.ConversationID {
			t.Fatal("conversation changed between turns")
		}
		identities[m.ClientID] = m.ConversationID
	}
	if identities[1] == identities[2] {
		t.Fatal("clients share a conversation")
	}
	sequences := map[string][]string{}
	for _, call := range f.snapshot() {
		if call.Path == "instance" {
			continue
		}
		sequences[call.Session] = append(sequences[call.Session], call.Path)
		if call.Path == "register" {
			if call.Method != "POST" || call.Body["agent_configuration_revision"] != float64(7) || call.Body["agent_instance_id"] != testInstance || len(call.Body) != 4 || !canonicalUUID.MatchString(call.Session) {
				t.Fatalf("registration payload %+v", call)
			}
		}
		if call.Path == "prepare" && (call.Method != "POST" || call.Session == "") {
			t.Fatalf("invalid preparation %+v", call)
		}
		if call.Path == "execute" {
			expected := map[string]any{"agent_instance_id": testInstance, "input": f.cfg.Message, "session_id": call.Session, "runtime_context": map[string]any{"space_id": testSpace}}
			if !reflect.DeepEqual(call.Body, expected) {
				t.Fatalf("execution payload %+v", call.Body)
			}
		}
	}
	if len(sequences) != 2 {
		t.Fatalf("session count %d", len(sequences))
	}
	for _, sequence := range sequences {
		expected := []string{"register", "prepare", "execute", "session", "history", "prepare", "execute", "session", "history", "delete"}
		if !reflect.DeepEqual(sequence, expected) {
			t.Fatalf("order %v", sequence)
		}
	}
}

func TestWeaverPreparationRefusals(t *testing.T) {
	tests := []struct {
		name, category string
		mutate         func(map[string]any)
	}{
		{"revision", "invalid_binding", func(p map[string]any) { p["agent_configuration_revision"] = 8 }},
		{"space", "invalid_binding", func(p map[string]any) { p["space_id"] = testInstance }},
		{"instance", "invalid_binding", func(p map[string]any) { p["agent_instance_id"] = testSpace }},
		{"streaming", "unsupported_transport", func(p map[string]any) { p["supports_streaming"] = false }},
		{"transport", "unsupported_transport", func(p map[string]any) { p["execution_transport"] = "ws" }},
		{"model error", "model_unavailable", func(p map[string]any) { p["model_error"] = map[string]any{"message": "secret"} }},
		{"no inference", "model_unavailable", func(p map[string]any) { p["inference"] = nil }},
		{"empty inference", "model_unavailable", func(p map[string]any) { p["inference"] = map[string]any{} }},
		{"external URL", "invalid_execution_url", func(p map[string]any) {
			p["execute_stream_url"] = "https://attacker.invalid/runtime/agents/execute/stream"
		}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			f := newWeaverFixture(t)
			f.setOverride(func(w http.ResponseWriter, r *http.Request, phase string, _ map[string]any) bool {
				if phase != "prepare" {
					return false
				}
				p := f.preparation()
				tt.mutate(p)
				_ = json.NewEncoder(w).Encode(p)
				return true
			})
			results, _ := f.run()
			if len(results) != 1 || results[0].Measurement.Error != tt.category {
				t.Fatalf("results %+v", results)
			}
			m := results[0].Measurement
			if m.Preparation == nil || m.Preparation.Error != tt.category || m.ExecutionStartedAt != nil || m.FirstTextAt != nil || m.FinalAt != nil || m.StreamClosedAt != nil || m.History != nil {
				t.Fatalf("invented observations %+v", m)
			}
			for _, call := range f.snapshot() {
				if call.Path == "execute" || call.Path == "history" {
					t.Fatalf("unexpected %s", call.Path)
				}
			}
		})
	}
}

func TestWeaverHTTPRefusalsAndRedirects(t *testing.T) {
	for _, phase := range []string{"instance", "register", "prepare", "execute", "session", "history", "delete"} {
		for _, status := range []int{401, 403, 409, 307} {
			t.Run(fmt.Sprintf("%s-%d", phase, status), func(t *testing.T) {
				f := newWeaverFixture(t)
				f.cfg.RequestsPerClient = 1
				// A redirect on the same origin is also forbidden, including auth headers.
				f.setOverride(func(w http.ResponseWriter, r *http.Request, p string, _ map[string]any) bool {
					if r.URL.Path == "/redirect-destination" {
						t.Error("redirect followed")
						w.WriteHeader(500)
						return true
					}
					if p != phase {
						return false
					}
					w.Header().Set("Location", f.server.URL+"/redirect-destination")
					w.WriteHeader(status)
					fmt.Fprint(w, "private upstream body")
					return true
				})
				results, a := f.run()
				if len(results) != 1 {
					t.Fatalf("results %d", len(results))
				}
				if phase == "delete" {
					if a.cleanupErrors.Load() != 1 || results[0].Err != nil {
						t.Fatal("cleanup not separately reported")
					}
					return
				}
				if results[0].Err == nil {
					t.Fatal("refusal succeeded")
				}
				calls := f.snapshot()
				for _, call := range calls {
					if (phase == "instance" || phase == "register" || phase == "prepare") && call.Path == "execute" {
						t.Fatal("execution after refusal")
					}
				}
			})
		}
	}
}

func TestWeaverOpeningAndRetention(t *testing.T) {
	for _, mode := range []string{"provided", "retain", "collision", "wrong revision", "wrong session", "wrong instance"} {
		t.Run(mode, func(t *testing.T) {
			f := newWeaverFixture(t)
			f.cfg.RequestsPerClient = 1
			if mode == "provided" {
				f.cfg.SessionID = testSession
			}
			if mode == "retain" {
				f.cfg.DeleteSession = false
			}
			f.setOverride(func(w http.ResponseWriter, r *http.Request, phase string, body map[string]any) bool {
				if mode == "wrong instance" && phase == "instance" {
					_ = json.NewEncoder(w).Encode(map[string]any{"configuration_revision": 7, "space_id": testInstance, "agent_instance_id": testInstance})
					return true
				}
				if phase != "register" || (mode != "collision" && mode != "wrong revision" && mode != "wrong session") {
					return false
				}
				id, _ := body["session_id"].(string)
				s := f.session(id)
				if mode == "wrong revision" {
					s["agent_configuration_revision"] = 8
				}
				if mode == "wrong session" {
					s["session_id"] = testSession
				}
				if mode != "collision" {
					w.WriteHeader(201)
				}
				_ = json.NewEncoder(w).Encode(s)
				return true
			})
			results, _ := f.run()
			success := mode == "provided" || mode == "retain"
			if len(results) != 1 || (results[0].Err == nil) != success {
				t.Fatalf("results %+v", results)
			}
			for _, call := range f.snapshot() {
				if call.Path == "delete" && (mode == "provided" || mode == "retain" || mode == "collision" || mode == "wrong instance") {
					t.Fatalf("unexpected deletion in %s", mode)
				}
				if mode == "provided" && call.Path == "register" {
					t.Fatal("provided session registered again")
				}
			}
		})
	}
}

func TestWeaverWaitsForEOFFinalAndTerminalErrors(t *testing.T) {
	for _, mode := range []string{"final then EOF", "truncated", "terminal"} {
		t.Run(mode, func(t *testing.T) {
			f := newWeaverFixture(t)
			reached, release := make(chan struct{}), make(chan struct{})
			var once sync.Once
			f.setOverride(func(w http.ResponseWriter, r *http.Request, phase string, _ map[string]any) bool {
				if phase != "execute" {
					return false
				}
				if mode == "truncated" {
					fmt.Fprint(w, "data: {\"kind\":\"final\"}\n")
					return true
				}
				if mode == "terminal" {
					fmt.Fprint(w, "data: {\"kind\":\"execution_error\",\"error\":\"secret\"}\n\ndata: {\"kind\":\"final\"}\n\n")
					return true
				}
				fmt.Fprint(w, "data: {\"kind\":\"final\"}\n\n")
				w.(http.Flusher).Flush()
				once.Do(func() { close(reached); <-release })
				return true
			})
			done := make(chan []result, 1)
			go func() {
				a := newWeaverAdapter(f.cfg)
				defer a.Close()
				done <- runLoad(context.Background(), loadPlan{Clients: 1, Turns: 2, Timeout: time.Second}, a.Open)
			}()
			if mode == "final then EOF" {
				<-reached
				for _, call := range f.snapshot() {
					if call.Path == "history" || call.Path == "session" {
						t.Error("read before EOF")
					}
				}
				select {
				case <-done:
					t.Error("completed before EOF")
				default:
				}
				close(release)
			}
			results := <-done
			if mode == "final then EOF" {
				if len(results) != 2 || results[0].Err != nil || results[1].Err != nil {
					t.Fatalf("results %+v", results)
				}
			} else {
				category := "incomplete_stream"
				if mode == "terminal" {
					category = "execution_error"
				}
				if len(results) != 1 || results[0].Measurement.Error != category {
					t.Fatalf("results %+v", results)
				}
			}
		})
	}
}

func TestWeaverCancellationAndTimeout(t *testing.T) {
	for _, phase := range []string{"prepare", "execute"} {
		for _, mode := range []string{"cancel", "timeout"} {
			t.Run(phase+"-"+mode, func(t *testing.T) {
				f := newWeaverFixture(t)
				reached := make(chan struct{})
				f.setOverride(func(w http.ResponseWriter, r *http.Request, p string, _ map[string]any) bool {
					if p != phase {
						return false
					}
					if phase == "execute" {
						fmt.Fprint(w, "data: {\"kind\":\"assistant_delta\",\"delta\":\"text\"}\n\n")
						w.(http.Flusher).Flush()
					}
					close(reached)
					<-r.Context().Done()
					return true
				})
				a := newWeaverAdapter(f.cfg)
				defer a.Close()
				c, err := a.Open(context.Background(), 0)
				if err != nil {
					t.Fatal(err)
				}
				defer c.Close()
				ctx, cancel := context.WithCancel(context.Background())
				if mode == "timeout" {
					cancel()
					ctx, cancel = context.WithTimeout(context.Background(), 50*time.Millisecond)
				}
				defer cancel()
				done := make(chan result, 1)
				go func() { done <- c.Execute(ctx) }()
				<-reached
				if mode == "cancel" {
					cancel()
				}
				r := <-done
				expected := "canceled"
				if mode == "timeout" {
					expected = "timeout"
				}
				if classifyError(r.Err) != expected || r.Measurement.FinalAt != nil || r.Measurement.StreamClosedAt != nil || r.Measurement.History != nil {
					t.Fatalf("result %+v", r)
				}
				if phase == "prepare" && (r.Measurement.ExecutionStartedAt != nil || r.Measurement.FirstTextAt != nil) {
					t.Fatal("execution invented")
				}
			})
		}
	}
}

func TestWeaverURLPolicy(t *testing.T) {
	for _, path := range []string{"https://evil.invalid/x/agents/execute/stream", "//evil.invalid/x/agents/execute/stream", "/agents/execute/stream", "/x/../x/agents/execute/stream", "/x/./agents/execute/stream", "/x//agents/execute/stream", "/x/%2e/agents/execute/stream", "/x/agents/execute/stream?token=secret", "/x/agents/execute/stream#x", "/x\\evil/agents/execute/stream"} {
		if weaverPublicPath(path, "/agents/execute/stream") {
			t.Errorf("accepted %q", path)
		}
	}
	for _, path := range []string{"/runtime/agents/execute/stream", "/control-plane/v1/agents/execute/stream"} {
		if !weaverPublicPath(path, "/agents/execute/stream") {
			t.Errorf("refused %q", path)
		}
	}
}

func TestWeaverRawExportAndCLI(t *testing.T) {
	f := newWeaverFixture(t)
	raw, summary := filepath.Join(t.TempDir(), "turns.jsonl"), filepath.Join(t.TempDir(), "summary.json")
	args := []string{"-target=weaver", "-protocol=sse", "-fred-origin=" + f.server.URL, "-space-id=" + testSpace, "-agent-instance-id=" + testInstance, "-clients=1", "-requests-per-client=2", "-ramp-duration=0s", "-message=" + f.cfg.Message, "-raw-report=" + raw, "-json-report=" + summary}
	cmd := exec.Command(os.Args[0], "-test.run=^TestCLIHelper$")
	cmd.Env = append(os.Environ(), "BENCH_TEST_CLI=1", "AGENTIC_TOKEN="+f.cfg.Token, "BENCH_TEST_ARGS="+strings.Join(args, "\n"))
	output, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("CLI: %v, %s", err, output)
	}
	rawData, err := os.ReadFile(raw)
	if err != nil {
		t.Fatal(err)
	}
	summaryData, err := os.ReadFile(summary)
	if err != nil {
		t.Fatal(err)
	}
	for _, data := range [][]byte{rawData, summaryData, output} {
		for _, secret := range []string{f.cfg.Token, f.cfg.Message} {
			if strings.Contains(string(data), secret) {
				t.Fatal("credential or prompt leaked")
			}
		}
	}
	rows := strings.Split(strings.TrimSpace(string(rawData)), "\n")
	if len(rows) != 2 {
		t.Fatalf("rows %d", len(rows))
	}
	for _, line := range rows {
		var row map[string]any
		if err := json.Unmarshal([]byte(line), &row); err != nil {
			t.Fatal(err)
		}
		if row["schema_version"] != "fred.bench.turn.v2" || row["target"] != "weaver" || row["preparation_mode"] != "per_turn" || row["execution_started_at"] == nil || row["history_messages"] == nil {
			t.Fatalf("row %+v", row)
		}
	}
	var report benchmarkJSONReport
	if err := json.Unmarshal(summaryData, &report); err != nil {
		t.Fatal(err)
	}
	if report.Target != f.server.URL || report.SpaceID != testSpace || report.Success != 2 || report.Outcome != "OK" {
		t.Fatalf("summary %+v", report)
	}
	for _, call := range f.snapshot() {
		if call.Session != "" && strings.Contains(string(rawData), call.Session) {
			t.Fatal("session ID exported")
		}
	}
}

func TestWeaverConfigRejectsBeforeNetwork(t *testing.T) {
	f := newWeaverFixture(t)
	cases := []struct {
		name   string
		change func(*config)
	}{
		{"websocket", func(c *config) { c.Protocol = "ws" }},
		{"total mode", func(c *config) { c.RequestsPerClient = 0 }},
		{"no origin", func(c *config) { c.FredOrigin = "" }},
		{"origin userinfo", func(c *config) { c.FredOrigin = "https://user:secret@example.invalid" }},
		{"origin path", func(c *config) { c.FredOrigin += "/runtime" }},
		{"origin query", func(c *config) { c.FredOrigin += "?token=secret" }},
		{"origin fragment", func(c *config) { c.FredOrigin += "#fragment" }},
		{"mount traversal", func(c *config) { c.ControlPlanePath = "/x/../control-plane" }},
		{"invalid space", func(c *config) { c.SpaceID = "not-a-uuid" }},
		{"missing instance", func(c *config) { c.AgentInstanceID = "" }},
		{"no token", func(c *config) { c.Token = "" }},
		{"shared session", func(c *config) { c.SessionID = testSession; c.Clients = 2 }},
		{"no conversation", func(c *config) { c.CreateSession = false }},
		{"query auth", func(c *config) { c.TokenInQuery = true }},
		{"legacy scope", func(c *config) { c.SSETeamID = testSpace }},
	}
	for _, tt := range cases {
		t.Run(tt.name, func(t *testing.T) {
			cfg := f.cfg
			tt.change(&cfg)
			if validateConfig(cfg) == nil {
				t.Fatal("accepted invalid config")
			}
		})
	}
	for _, name := range []string{"url", "agent", "agent-uuid", "agent-create-url", "ensure-v2-definition-ref", "ensure-v2-profile-id", "ensure-agent-name", "delete-created-agent", "session-url", "prepare-sessions", "prepare-concurrency", "sse-user-id", "sse-team-id", "debug-events", "read-limit-bytes", "insecure", "token-in-query", "allow-empty-token", "requests", "document-library-ids", "document-uids", "search-policy", "search-rag-scope", "include-session-scope", "include-corpus-scope"} {
		cfg := f.cfg
		cfg.ExplicitFlags = []string{name}
		if validateConfig(cfg) == nil {
			t.Errorf("explicit flag %s accepted", name)
		}
	}
	base := []string{"-target=weaver", "-protocol=sse", "-fred-origin=" + f.server.URL, "-space-id=" + testSpace, "-agent-instance-id=" + testInstance, "-clients=1", "-requests-per-client=2"}
	for _, extra := range []string{"-agent=Georges", "-url=" + f.server.URL, "-prepare-sessions=false", "-token-in-query=false", ""} {
		args := append([]string(nil), base...)
		token := f.cfg.Token
		if extra == "" {
			token = ""
		} else {
			args = append(args, extra)
		}
		cmd := exec.Command(os.Args[0], "-test.run=^TestCLIHelper$")
		cmd.Env = append(os.Environ(), "BENCH_TEST_CLI=1", "AGENTIC_TOKEN="+token, "BENCH_TEST_ARGS="+strings.Join(args, "\n"))
		out, err := cmd.CombinedOutput()
		exit, ok := err.(*exec.ExitError)
		if !ok || exit.ExitCode() != 2 {
			t.Fatalf("extra %q: %v %s", extra, err, out)
		}
	}
	if len(f.snapshot()) != 0 {
		t.Fatal("invalid config performed network calls")
	}
}

func TestWeaverExternalDestinationsNeverReceiveToken(t *testing.T) {
	for _, phase := range []string{"prepare", "execute", "session", "history"} {
		t.Run(phase, func(t *testing.T) {
			f := newWeaverFixture(t)
			external := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Error("contacted external destination") }))
			defer external.Close()
			f.setOverride(func(w http.ResponseWriter, r *http.Request, p string, _ map[string]any) bool {
				if p != phase {
					return false
				}
				switch phase {
				case "prepare":
					prep := f.preparation()
					prep["execute_stream_url"] = external.URL + "/runtime/agents/execute/stream"
					_ = json.NewEncoder(w).Encode(prep)
				case "session":
					id := r.URL.Path[strings.LastIndex(r.URL.Path, "/")+1:]
					s := f.session(id)
					s["messages_url"] = external.URL + "/runtime/agents/sessions/" + id + "/messages"
					_ = json.NewEncoder(w).Encode(s)
				default:
					w.Header().Set("Location", external.URL)
					w.WriteHeader(http.StatusTemporaryRedirect)
				}
				return true
			})
			results, _ := f.run()
			if len(results) != 1 || results[0].Err == nil {
				t.Fatal("external destination accepted")
			}
		})
	}
}

func TestWeaverCleanupFailureCLI(t *testing.T) {
	f := newWeaverFixture(t)
	f.setOverride(func(w http.ResponseWriter, r *http.Request, phase string, _ map[string]any) bool {
		if phase != "delete" {
			return false
		}
		w.WriteHeader(202)
		_ = json.NewEncoder(w).Encode(map[string]any{"status": "blocked", "target_kind": "session", "target_id": r.URL.Path[strings.LastIndex(r.URL.Path, "/")+1:], "error_code": "private upstream error"})
		return true
	})
	summary := filepath.Join(t.TempDir(), "summary.json")
	args := []string{"-target=weaver", "-protocol=sse", "-fred-origin=" + f.server.URL, "-space-id=" + testSpace, "-agent-instance-id=" + testInstance, "-clients=1", "-requests-per-client=1", "-ramp-duration=0s", "-json-report=" + summary}
	cmd := exec.Command(os.Args[0], "-test.run=^TestCLIHelper$")
	cmd.Env = append(os.Environ(), "BENCH_TEST_CLI=1", "AGENTIC_TOKEN="+f.cfg.Token, "BENCH_TEST_ARGS="+strings.Join(args, "\n"))
	output, err := cmd.CombinedOutput()
	exit, ok := err.(*exec.ExitError)
	if !ok || exit.ExitCode() != 1 || !strings.Contains(string(output), "DEGRADED") || !strings.Contains(string(output), "cleanup failed") || strings.Contains(string(output), "private upstream") {
		t.Fatalf("CLI %v %s", err, output)
	}
	data, err := os.ReadFile(summary)
	if err != nil {
		t.Fatal(err)
	}
	var report benchmarkJSONReport
	if err := json.Unmarshal(data, &report); err != nil {
		t.Fatal(err)
	}
	if report.Success != 1 || report.Errors != 0 || report.CleanupErrors != 1 || report.Outcome != "DEGRADED" {
		t.Fatalf("cleanup changed turn results: %+v", report)
	}
}

func TestWeaverFailedPreparationExport(t *testing.T) {
	f := newWeaverFixture(t)
	f.setOverride(func(w http.ResponseWriter, r *http.Request, phase string, _ map[string]any) bool {
		if phase != "prepare" {
			return false
		}
		w.WriteHeader(403)
		fmt.Fprint(w, f.cfg.Token+f.cfg.Message)
		return true
	})
	results, _ := f.run()
	path := filepath.Join(t.TempDir(), "turns.jsonl")
	if err := writeRawReport(path, f.cfg, results); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var row map[string]any
	if err := json.Unmarshal(data, &row); err != nil {
		t.Fatal(err)
	}
	if row["target"] != "weaver" || row["schema_version"] != "fred.bench.turn.v2" || row["error"] != "http_403" || row["preparation"] == nil {
		t.Fatalf("row %+v", row)
	}
	for _, key := range []string{"execution_started_at", "first_text_at", "final_at", "stream_closed_at", "history", "admission_at"} {
		if row[key] != nil {
			t.Errorf("invented %s", key)
		}
	}
	for _, secret := range []string{f.cfg.Token, f.cfg.Message} {
		if strings.Contains(string(data), secret) {
			t.Fatal("secret in failed preparation export")
		}
	}
}

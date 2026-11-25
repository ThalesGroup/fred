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
	"strings"
	"sync"
	"testing"
	"time"
)

type scenarioFixture struct {
	t                                                 *testing.T
	mu                                                sync.Mutex
	server                                            *httptest.Server
	fragments                                         int
	turns                                             map[string]int
	messages                                          map[string][]json.RawMessage
	owners                                            map[string]string
	registered                                        map[string]time.Time
	registrationStatus, cleanupStatus                 int
	invalidRegistration                               bool
	registrations                                     int
	active, logins, executions, historyReads, deletes int
	badStream, badHistory, failLogin                  bool
	stallSecond                                       chan struct{}
	rejectUser                                        string
}

func newScenarioFixture(t *testing.T, wrappers ...func(http.Handler) http.Handler) *scenarioFixture {
	f := &scenarioFixture{t: t, fragments: 1, turns: map[string]int{}, messages: map[string][]json.RawMessage{}, owners: map[string]string{}, registered: map[string]time.Time{}}
	var handler http.Handler = http.HandlerFunc(f.serve)
	for _, wrap := range wrappers {
		handler = wrap(handler)
	}
	f.server = httptest.NewServer(handler)
	t.Cleanup(f.server.Close)
	return f
}
func (f *scenarioFixture) cfg(target, mode string) config {
	return config{Scenario: "conversation", Target: target, Protocol: "sse", CredentialFile: testCredentialPath(f.t, f.server.URL+"/realms/app", 4), ConcurrencySteps: "1,2", IdentityMode: mode, AuthConcurrency: 2, FredOrigin: f.server.URL, ControlPlanePath: "/control-plane/v1", SpaceID: testSpace, AgentInstanceID: testInstance, SSETeamID: "same-team", URL: f.server.URL + "/runtime/agents/execute/stream", RequestsPerClient: 3, CreateSession: true, DeleteSession: true, Timeout: time.Second, RawReportPath: filepath.Join(f.t.TempDir(), "turns.jsonl"), JSONReportPath: filepath.Join(f.t.TempDir(), "summary.json"), SessionTitle: "Benchmark", Message: "PRIVATE_PROMPT"}
}
func (f *scenarioFixture) serve(w http.ResponseWriter, r *http.Request) {
	if strings.HasSuffix(r.URL.Path, "/frontend/config") {
		fmt.Fprint(w, `{"gcu_version":null,"root_bootstrap_required":false}`)
		return
	}
	if strings.HasSuffix(r.URL.Path, "/token") {
		_ = r.ParseForm()
		f.mu.Lock()
		f.logins++
		failed := f.failLogin
		f.mu.Unlock()
		if failed {
			w.WriteHeader(401)
			fmt.Fprint(w, "PRIVATE_PASSWORD PRIVATE_CLIENT_SECRET")
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{"access_token": testJWT(r.Form.Get("username")), "refresh_token": "PRIVATE_REFRESH", "expires_in": 300, "token_type": "Bearer"})
		return
	}
	sub := ""
	for i := 0; i < 4; i++ {
		user := fmt.Sprintf("private-user-%d", i)
		if r.Header.Get("Authorization") == "Bearer "+testJWT(user) {
			sub = user
		}
	}
	if sub == "" {
		f.t.Error("missing user identity")
		w.WriteHeader(401)
		return
	}
	path := r.URL.Path
	var body map[string]any
	if r.Method == "POST" {
		_ = json.NewDecoder(r.Body).Decode(&body)
	}
	session, _ := body["session_id"].(string)
	if strings.HasSuffix(path, "/agents/execute/stream") {
		if sub == f.rejectUser {
			f.mu.Lock()
			f.executions++
			f.mu.Unlock()
			w.WriteHeader(401)
			fmt.Fprint(w, "PRIVATE_UPSTREAM")
			return
		}
		input, _ := body["input"].(string)
		ctx, _ := body["runtime_context"].(map[string]any)
		if ctx["team_id"] != "same-team" && ctx["space_id"] != testSpace {
			f.t.Error("wrong team/space")
		}
		if ctx["team_id"] != nil && ctx["user_id"] != sub {
			f.t.Error("Swift identity is not token sub")
		}
		f.mu.Lock()
		if previous := f.owners[session]; previous != "" && previous != sub {
			f.t.Error("session shared across identities")
		}
		if f.registered[session].IsZero() {
			f.t.Error("execution without registered session")
		}
		f.owners[session] = sub
		turn := f.turns[session] + 1
		f.active++
		f.executions++
		bad, stall, fragments := f.badStream, f.stallSecond, f.fragments
		f.mu.Unlock()
		defer func() { f.mu.Lock(); f.active--; f.mu.Unlock() }()
		if stall != nil && turn == 2 {
			select {
			case stall <- struct{}{}:
			default:
			}
			<-r.Context().Done()
			return
		}
		answer := strings.Repeat("A normal answer about the documents.\n", fragments)
		w.Header().Set("Content-Type", "text/event-stream")
		for _, line := range strings.SplitAfter(answer, "\n") {
			if line == "" {
				continue
			}
			data, _ := json.Marshal(map[string]string{"kind": "assistant_delta", "delta": line})
			fmt.Fprintf(w, "data: %s\n\n", data)
		}
		final := answer
		if bad && turn == 2 {
			final = "Different final text"
		}
		data, _ := json.Marshal(map[string]string{"kind": "final", "content": final})
		fmt.Fprintf(w, "data: %s\n\n", data)
		f.mu.Lock()
		f.turns[session] = turn
		exchange := fmt.Sprintf("e%d", turn)
		for _, message := range []map[string]any{
			{"session_id": session, "exchange_id": exchange, "rank": turn*2 - 1, "role": "user", "channel": "final", "parts": []map[string]string{{"type": "text", "text": input}}},
			{"session_id": session, "exchange_id": exchange, "rank": turn * 2, "role": "assistant", "channel": "final", "parts": []map[string]string{{"type": "text", "text": answer}}},
		} {
			data, _ := json.Marshal(message)
			f.messages[session] = append(f.messages[session], data)
		}
		f.mu.Unlock()
		return
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	w.Header().Set("Content-Type", "application/json")
	switch {
	case strings.HasSuffix(path, "/prepare-execution"):
		if session := r.URL.Query().Get("session_id"); session != "" && f.owners[session] != sub {
			f.t.Error("preparation lost identity")
		}
		_ = json.NewEncoder(w).Encode(map[string]any{"team_id": "same-team", "space_id": testSpace, "agent_instance_id": testInstance, "agent_configuration_revision": 7, "execution_transport": "sse", "supports_streaming": true, "execute_stream_url": "/runtime/agents/execute/stream", "inference": map[string]any{"key": map[string]string{"source_id": "mock", "upstream_model_id": "gpt-4o"}}})
	case strings.HasSuffix(path, "/agent-instances/"+testInstance):
		_ = json.NewEncoder(w).Encode(map[string]any{"space_id": testSpace, "agent_instance_id": testInstance, "configuration_revision": 7})
	case strings.HasSuffix(path, "/sessions") && r.Method == "POST":
		f.registrations++
		if body["agent_instance_id"] != testInstance || body["title"] != "Benchmark" || session == "" {
			f.t.Error("invalid session registration payload")
		}
		if strings.Contains(path, "/teams/") && (len(body) != 3 || len(session) != 32 || path != "/control-plane/v1/teams/same-team/sessions") {
			f.t.Error("Swift registration differs from managed UI contract")
		}
		status := f.registrationStatus
		if status == 0 {
			status = http.StatusCreated
		}
		if status == http.StatusCreated {
			f.owners[session] = sub
			f.registered[session] = time.Now()
		}
		w.WriteHeader(status)
		if f.invalidRegistration {
			fmt.Fprint(w, `{}`)
		} else {
			f.session(w, session)
		}
	case strings.HasSuffix(path, "/messages"):
		if f.active != 0 {
			f.t.Error("history overlaps load")
		}
		f.historyReads++
		parts := strings.Split(path, "/")
		session = parts[len(parts)-2]
		if owner := f.owners[session]; owner != "" && owner != sub {
			f.t.Error("history wrong owner")
		}
		if f.badHistory {
			fmt.Fprint(w, "[]")
		} else {
			_ = json.NewEncoder(w).Encode(f.messages[session])
		}
	case r.Method == "DELETE":
		if f.active != 0 {
			f.t.Error("cleanup overlaps load")
		}
		f.deletes++
		session = path[strings.LastIndex(path, "/")+1:]
		if f.registered[session].IsZero() || f.owners[session] != sub {
			f.t.Error("cleanup without session ownership")
		}
		if f.cleanupStatus != 0 {
			w.WriteHeader(f.cleanupStatus)
			return
		}
		if strings.Contains(path, "/teams/") {
			delete(f.registered, session)
			w.WriteHeader(http.StatusNoContent)
		} else if strings.HasPrefix(path, "/control-plane") {
			delete(f.registered, session)
			w.WriteHeader(202)
			_ = json.NewEncoder(w).Encode(map[string]any{"status": "queued", "target_kind": "session", "target_id": session})
		} else {
			f.t.Error("scenario bypassed CP deletion policy")
			w.WriteHeader(500)
		}
	default:
		session = path[strings.LastIndex(path, "/")+1:]
		f.session(w, session)
	}
}
func (f *scenarioFixture) session(w http.ResponseWriter, id string) {
	_ = json.NewEncoder(w).Encode(map[string]any{"session_id": id, "team_id": "same-team", "space_id": testSpace, "agent_instance_id": testInstance, "agent_configuration_revision": 7, "messages_url": "/runtime/agents/sessions/" + id + "/messages"})
}
func fixtureConfig(f *scenarioFixture, target, mode string) config {
	cfg := f.cfg(target, mode)
	if target == "weaver" {
		cfg.URL = ""
		cfg.SSETeamID = ""
	} else {
		cfg.FredOrigin = ""
		cfg.SpaceID = ""
	}
	return cfg
}

func TestScenarioBothTargetsStepsIdentitiesAndHistory(t *testing.T) {
	for _, target := range []string{"swift", "weaver"} {
		for _, mode := range []string{"shared", "per-conversation"} {
			t.Run(target+"/"+mode, func(t *testing.T) {
				f := newScenarioFixture(t)
				cfg := fixtureConfig(f, target, mode)
				report, err := runScenario(context.Background(), cfg)
				if err != nil || report.Outcome != "OK" || len(report.Steps) != 2 {
					t.Fatalf("%v %+v", err, report)
				}
				for i, s := range report.Steps {
					if s.Planned != (i+1)*3 || s.Attempted != s.Planned || s.Success != s.Planned || s.HistoryVerified != i+1 || s.First.Turns != i+1 || s.Following.Turns != (i+1)*2 {
						t.Fatalf("%+v", s)
					}
				}
				f.mu.Lock()
				logins, reads, deletes := f.logins, f.historyReads, f.deletes
				f.mu.Unlock()
				want := 1
				if mode == "per-conversation" {
					want = 2
				}
				if logins != want || reads != 3 || deletes != 3 {
					t.Fatalf("login/history/delete %d/%d/%d", logins, reads, deletes)
				}
				data, err := os.ReadFile(cfg.RawReportPath)
				if err != nil {
					t.Fatal(err)
				}
				for _, secret := range []string{"PRIVATE", "private-user", "signature", "session_id", f.server.URL} {
					if strings.Contains(string(data), secret) {
						t.Fatal("raw leaked", secret)
					}
				}
				info, _ := os.Stat(cfg.RawReportPath)
				if info.Mode().Perm() != 0600 {
					t.Fatal("raw is not private")
				}
				turns := map[string]int{}
				histories := map[string]bool{}
				identities := map[string]bool{}
				for _, line := range strings.Split(strings.TrimSpace(string(data)), "\n") {
					var row map[string]any
					if json.Unmarshal([]byte(line), &row) != nil {
						t.Fatal("invalid JSONL")
					}
					if row["kind"] == "turn" {
						id := row["conversation_id"].(string)
						turns[id]++
						identities[row["identity_id"].(string)] = true
						if row["schema_version"] != "fred.bench.scenario.turn.v1" || row["text_fragments"].(float64) != 1 {
							t.Fatal("bad turn", row)
						}
					}
					if row["kind"] == "history" {
						histories[row["conversation_id"].(string)] = true
					}
				}
				if len(turns) != 3 || len(identities) != want {
					t.Fatalf("wrong conversation/identity cardinality %d/%d", len(turns), len(identities))
				}
				for id, n := range turns {
					if n != 3 || !histories[id] {
						t.Fatal("turn/history correlation lost")
					}
				}
			})
		}
	}
}

func TestScenarioFailuresAndNoFictitiousSuccess(t *testing.T) {
	for _, failure := range []string{"login", "stream", "history"} {
		t.Run(failure, func(t *testing.T) {
			f := newScenarioFixture(t)
			f.failLogin = failure == "login"
			f.badStream = failure == "stream"
			f.badHistory = failure == "history"
			cfg := fixtureConfig(f, "weaver", "shared")
			cfg.ConcurrencySteps = "2"
			report, err := runScenario(context.Background(), cfg)
			if err != nil || report.Outcome == "OK" {
				t.Fatalf("%v %+v", err, report)
			}
			s := report.Steps[0]
			switch failure {
			case "login":
				if s.Attempted != 0 || s.NotStarted != 6 || f.executions != 0 || report.AuthErrors != 1 {
					t.Fatal("login failure allowed load")
				}
			case "stream":
				if s.Attempted != 4 || s.NotStarted != 2 || s.IntegrityErrors != 2 || s.PerformanceErrors != 0 || s.Success != 2 {
					t.Fatalf("%+v", s)
				}
			case "history":
				if s.HistoryErrors != 2 || s.Success != 6 || s.IntegrityErrors != 0 {
					t.Fatalf("%+v", s)
				}
			}
		})
	}
}

func TestScenarioDurableRowsBeforeCancellation(t *testing.T) {
	f := newScenarioFixture(t)
	f.stallSecond = make(chan struct{}, 1)
	cfg := fixtureConfig(f, "swift", "shared")
	cfg.ConcurrencySteps = "1"
	cfg.Timeout = 3 * time.Second
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan scenarioReport, 1)
	go func() {
		report, err := runScenario(ctx, cfg)
		if err != nil {
			t.Error(err)
		}
		done <- report
	}()
	select {
	case <-f.stallSecond:
	case <-time.After(time.Second):
		t.Fatal("second turn not reached")
	}
	// The second request can begin while the collector fsyncs the first row.
	deadline := time.Now().Add(time.Second)
	for {
		data, _ := os.ReadFile(cfg.RawReportPath)
		if strings.Contains(string(data), `"kind":"turn"`) {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("completed turn not written progressively")
		}
		time.Sleep(time.Millisecond)
	}
	cancel()
	report := <-done
	s := report.Steps[0]
	if s.Attempted != 2 || s.Success != 1 || s.Errors != 1 || s.NotStarted != 1 || report.Outcome == "OK" {
		t.Fatalf("%+v", report)
	}
	data, _ := os.ReadFile(cfg.RawReportPath)
	if strings.Count(string(data), `"kind":"turn"`) != 2 || !strings.Contains(string(data), `"kind":"summary"`) {
		t.Fatal("canceled report incomplete")
	}
}

func TestScenarioStreamingMetricsAndExclusiveOutputs(t *testing.T) {
	f := newScenarioFixture(t)
	f.fragments = 100
	cfg := fixtureConfig(f, "swift", "shared")
	cfg.ConcurrencySteps = "1"
	cfg.RequestsPerClient = 1
	report, err := runScenario(context.Background(), cfg)
	if err != nil || report.Outcome != "OK" || report.Steps[0].First.ExecutionEOF.Count != 1 {
		t.Fatalf("%v %+v", err, report)
	}
	data, _ := os.ReadFile(cfg.RawReportPath)
	if !strings.Contains(string(data), `"text_fragments":100`) {
		t.Fatal("logical fragments lost")
	}
	if _, err := runScenario(context.Background(), cfg); err == nil {
		t.Fatal("existing raw overwritten")
	}
	after, _ := os.ReadFile(cfg.RawReportPath)
	if string(data) != string(after) {
		t.Fatal("raw changed")
	}
}

func TestScenarioOneFailedConversationDoesNotStopOthersOrRetryPOST(t *testing.T) {
	f := newScenarioFixture(t)
	f.rejectUser = "private-user-0"
	cfg := fixtureConfig(f, "swift", "per-conversation")
	cfg.ConcurrencySteps = "2"
	report, err := runScenario(context.Background(), cfg)
	if err != nil {
		t.Fatal(err)
	}
	s := report.Steps[0]
	if s.Attempted != 4 || s.Success != 3 || s.Errors != 1 || s.NotStarted != 2 || s.PerformanceErrors != 1 || f.executions != 4 {
		t.Fatalf("failed turn retried or other client stopped: %+v executions=%d", s, f.executions)
	}
}

func TestScenarioCLIUsesCredentialsAndNewReportSchema(t *testing.T) {
	f := newScenarioFixture(t)
	cfg := fixtureConfig(f, "weaver", "shared")
	args := []string{"-scenario=conversation", "-target=weaver", "-protocol=sse", "-credential-file=" + cfg.CredentialFile, "-fred-origin=" + f.server.URL, "-space-id=" + testSpace, "-agent-instance-id=" + testInstance, "-concurrency-steps=1", "-identity-mode=shared", "-requests-per-client=2", "-raw-report=" + cfg.RawReportPath, "-json-report=" + cfg.JSONReportPath}
	cmd := exec.Command(os.Args[0], "-test.run=^TestCLIHelper$")
	cmd.Env = append(os.Environ(), "BENCH_TEST_CLI=1", "AGENTIC_TOKEN=IGNORED_PRIVATE_ENV_TOKEN", "BENCH_TEST_ARGS="+strings.Join(args, "\n"))
	output, err := cmd.CombinedOutput()
	if err != nil || !strings.Contains(string(output), "OK") {
		t.Fatalf("CLI: %v %s", err, output)
	}
	data, err := os.ReadFile(cfg.JSONReportPath)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(data), `"schema_version":"fred.bench.scenario.v1"`) || strings.Contains(string(output)+string(data), "PRIVATE") {
		t.Fatal("CLI schema/privacy")
	}
	invalid := []string{"-scenario=conversation", "-target=weaver", "-protocol=sse", "-credential-file=" + cfg.CredentialFile, "-concurrency-steps=1", "-raw-report=" + filepath.Join(t.TempDir(), "invalid.jsonl"), "-accept-test-terms=current"}
	cmd = exec.Command(os.Args[0], "-test.run=^TestCLIHelper$")
	cmd.Env = append(os.Environ(), "BENCH_TEST_CLI=1", "BENCH_TEST_ARGS="+strings.Join(invalid, "\n"))
	if output, err = cmd.CombinedOutput(); err == nil || !strings.Contains(string(output), "requires prepare-only") {
		t.Fatalf("implicit acceptance allowed: %v %s", err, output)
	}
}

func TestSwiftScenarioRegistrationRetentionAndTiming(t *testing.T) {
	f := newScenarioFixture(t)
	cfg := fixtureConfig(f, "swift", "shared")
	cfg.ConcurrencySteps, cfg.DeleteSession = "1", false
	report, err := runScenario(context.Background(), cfg)
	if err != nil || report.Outcome != "OK" {
		t.Fatalf("%v %+v", err, report)
	}
	if f.registrations != 1 || len(f.registered) != 1 || f.deletes != 0 || f.executions != 3 {
		t.Fatalf("registration/retention failed: %d/%d/%d/%d", f.registrations, len(f.registered), f.deletes, f.executions)
	}
	var registeredAt time.Time
	for _, at := range f.registered {
		registeredAt = at
	}
	data, err := os.ReadFile(cfg.RawReportPath)
	if err != nil {
		t.Fatal(err)
	}
	for _, line := range strings.Split(strings.TrimSpace(string(data)), "\n") {
		var record struct {
			Kind string `json:"kind"`
		}
		if err := json.Unmarshal([]byte(line), &record); err != nil {
			t.Fatal(err)
		}
		if record.Kind != "turn" {
			continue
		}
		var row scenarioTurn
		if err := json.Unmarshal([]byte(line), &row); err != nil {
			t.Fatal(err)
		}
		if !row.StartedAt.After(registeredAt) || row.ExecutionStartedAt == nil || row.ExecutionStartedAt.Before(row.StartedAt) || row.Preparation != nil || row.PreparationMode != "not_performed" {
			t.Fatalf("registration polluted turn metrics: %+v", row)
		}
	}
}

func TestSwiftScenarioRegistrationFailureOwnershipAndCleanup(t *testing.T) {
	for _, tc := range []struct {
		name                               string
		status                             int
		invalid                            bool
		cleanupStatus                      int
		executions, deletes, cleanupErrors int
	}{
		{name: "collision", status: 409},
		{name: "existing_200", status: 200},
		{name: "post_refused", status: 403},
		{name: "post_failure", status: 500},
		{name: "created_invalid_body", status: 201, invalid: true, deletes: 1},
		{name: "created_invalid_body_cleanup_failure", status: 201, invalid: true, cleanupStatus: 500, deletes: 1, cleanupErrors: 1},
		{name: "cleanup_failure", status: 201, cleanupStatus: 500, executions: 3, deletes: 1, cleanupErrors: 1},
		{name: "cleanup_unexpected_receipt", status: 201, cleanupStatus: 200, executions: 3, deletes: 1, cleanupErrors: 1},
	} {
		t.Run(tc.name, func(t *testing.T) {
			f := newScenarioFixture(t)
			f.registrationStatus, f.invalidRegistration, f.cleanupStatus = tc.status, tc.invalid, tc.cleanupStatus
			cfg := fixtureConfig(f, "swift", "shared")
			cfg.ConcurrencySteps = "1"
			report, err := runScenario(context.Background(), cfg)
			if err != nil || report.Outcome == "OK" {
				t.Fatalf("%v %+v", err, report)
			}
			if f.registrations != 1 || f.executions != tc.executions || f.deletes != tc.deletes || report.Steps[0].CleanupErrors != tc.cleanupErrors {
				t.Fatalf("lifecycle registration=%d executions=%d deletes=%d report=%+v", f.registrations, f.executions, f.deletes, report)
			}
			if tc.executions == 0 {
				data, _ := os.ReadFile(cfg.RawReportPath)
				if strings.Contains(string(data), `"execution_started_at"`) || strings.Contains(string(data), `"final_at"`) {
					t.Fatal("registration failure invented execution timestamps")
				}
			}
		})
	}
}

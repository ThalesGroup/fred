package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestBenchBrowserLoginPKCEAndRefresh(t *testing.T) {
	var endpoint, challenge, redirect string
	var exchanges atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/realms/app/.well-known/openid-configuration":
			json.NewEncoder(w).Encode(map[string]string{"issuer": endpoint + "/realms/app", "authorization_endpoint": endpoint + "/authorize", "token_endpoint": endpoint + "/token"})
		case "/token":
			r.ParseForm()
			if r.Form.Has("client_secret") || r.Form.Get("client_id") != "app" {
				t.Error("public client contract violated")
			}
			if exchanges.Add(1) == 1 {
				sum := sha256.Sum256([]byte(r.Form.Get("code_verifier")))
				if base64.RawURLEncoding.EncodeToString(sum[:]) != challenge || r.Form.Get("code") != "PRIVATE_CODE" || r.Form.Get("redirect_uri") != redirect || r.Form.Get("grant_type") != "authorization_code" {
					t.Error("PKCE exchange mismatch")
				}
			} else if r.Form.Get("grant_type") != "refresh_token" || r.Form.Get("refresh_token") != "PRIVATE_REFRESH" {
				t.Error("refresh mismatch")
			}
			json.NewEncoder(w).Encode(map[string]any{"access_token": testJWT("private-user-0"), "refresh_token": "PRIVATE_REFRESH", "expires_in": 300, "token_type": "Bearer"})
		default:
			t.Errorf("unexpected network operation %s", r.URL.Path)
			w.WriteHeader(404)
		}
	}))
	defer server.Close()
	endpoint = server.URL
	client := sseHTTPClient(config{})
	defer client.CloseIdleConnections()
	open := func(raw string) error {
		u, _ := url.Parse(raw)
		q := u.Query()
		challenge, redirect = q.Get("code_challenge"), q.Get("redirect_uri")
		if q.Get("code_challenge_method") != "S256" || len(q.Get("state")) < 32 || q.Get("response_type") != "code" {
			t.Fatal("unsafe browser authorization")
		}
		callback, _ := url.Parse(redirect)
		values := url.Values{"state": {"wrong"}, "code": {"PRIVATE_CODE"}}
		callback.RawQuery = values.Encode()
		resp, err := client.Get(callback.String())
		if err != nil {
			t.Fatal(err)
		}
		resp.Body.Close()
		if resp.StatusCode != 400 {
			t.Fatal("wrong state accepted")
		}
		values.Set("state", q.Get("state"))
		values.Set("iss", endpoint+"/realms/app")
		callback.RawQuery = values.Encode()
		resp, err = client.Get(callback.String())
		if err != nil {
			t.Fatal(err)
		}
		resp.Body.Close()
		if resp.StatusCode != 200 {
			t.Fatal("valid callback refused")
		}
		return nil
	}
	var messages strings.Builder
	identity, err := browserBenchLogin(context.Background(), benchPublicAuth{Enabled: true, Realm: endpoint + "/realms/app", ClientID: "app", Provider: "keycloak", UIDClaim: "sub"}, client, open, func(s string) { messages.WriteString(s) })
	if err != nil {
		t.Fatal(err)
	}
	identity.refreshAt = time.Now().Add(-time.Minute)
	if _, _, err := identity.token(context.Background()); err != nil {
		t.Fatal(err)
	}
	if exchanges.Load() != 2 || strings.Contains(messages.String(), "PRIVATE") {
		t.Fatal("refresh or redaction failed")
	}
}

func TestBenchCatalogNamesPaginationAndAuthority(t *testing.T) {
	second := "30000000-0000-0000-0000-000000000002"
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer "+testJWT("user") || (r.Method != http.MethodGet && !(r.Method == http.MethodPost && strings.HasSuffix(r.URL.Path, "/prepare-execution"))) {
			t.Error("unauthenticated or mutating discovery")
		}
		switch r.URL.Path {
		case "/control-plane/v1/me/spaces":
			json.NewEncoder(w).Encode([]map[string]any{{"id": second, "kind": "organization", "name": "Acme"}, {"id": testSpace, "kind": "team", "name": "Research", "organization_id": second, "path": []string{testSpace}}})
		case "/control-plane/v1/spaces/" + testSpace + "/agent-instances/" + testInstance + "/prepare-execution":
			if r.Method != http.MethodPost || r.URL.RawQuery != "" {
				t.Error("model preview must not create or select a session")
			}
			json.NewEncoder(w).Encode(map[string]any{"inference": map[string]any{"key": map[string]string{"source_id": "configured-source", "upstream_model_id": "current-default"}}})
		case "/control-plane/v1/spaces/" + testSpace + "/agent-instances":
			if r.URL.Query().Get("after") == "first" {
				json.NewEncoder(w).Encode(map[string]any{"items": []map[string]any{{"agent_instance_id": second, "display_name": "Disabled", "status": "disabled"}}, "next_cursor": nil})
			} else {
				json.NewEncoder(w).Encode(map[string]any{"items": []map[string]any{{"agent_instance_id": testInstance, "display_name": "Benchmark", "status": "enabled", "recommended_model": map[string]string{"upstream_model_id": "example-model"}}}, "next_cursor": "first"})
			}
		default:
			t.Error("unexpected route", r.URL.Path)
			w.WriteHeader(404)
		}
	}))
	defer server.Close()
	client := sseHTTPClient(config{})
	defer client.CloseIdleConnections()
	identity := &benchmarkIdentity{gate: make(chan struct{}, 1), access: testJWT("user")}
	catalog := benchCatalog{&weaverAdapter{cfg: config{FredOrigin: server.URL, ControlPlanePath: "/control-plane/v1"}, http: client}, identity}
	spaces, err := catalog.spaces(context.Background())
	if err != nil || len(spaces) != 1 || spaces[0].Label != "Acme / Research" {
		t.Fatalf("spaces: %+v %v", spaces, err)
	}
	agents, err := catalog.agents(context.Background(), testSpace)
	if err != nil || len(agents) != 1 || agents[0].Name != "Benchmark" {
		t.Fatalf("agents: %+v %v", agents, err)
	}
	var preparation weaverPreparation
	if err := catalog.request(context.Background(), http.MethodPost, "/spaces/"+testSpace+"/agent-instances/"+testInstance+"/prepare-execution", &preparation); err != nil || preparation.Inference == nil || preparation.Inference.Key.UpstreamID != "current-default" {
		t.Fatalf("model preview did not read Fred's current selection: %+v %v", preparation, err)
	}
	if _, err := catalog.agents(context.Background(), "../admin"); err == nil {
		t.Fatal("unvalidated identifier")
	}
}

func TestBenchBuiltInQuestionsUseExistingScenarioAndReport(t *testing.T) {
	f := newScenarioFixture(t)
	cfg := fixtureConfig(f, "weaver", "shared")
	cfg.CredentialFile, cfg.Token = "", testJWT("private-user-0")
	cfg.ConcurrencySteps, cfg.Questions = "1", append([]string(nil), generalBenchQuestions...)
	cfg.TraceTurns, cfg.DeleteSession = true, false
	count := 0
	cfg.ObserveTurn = func(row scenarioTurn) {
		count++
		if row.TraceID == "" || row.Outcome != "success" {
			t.Error("turn missing success/correlation")
		}
	}
	report, err := runScenario(context.Background(), cfg)
	if err != nil || report.Outcome != "OK" || count != 10 {
		t.Fatalf("%+v %v turns=%d", report, err, count)
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.executions != 10 || f.logins != 0 || f.deletes != 0 || f.historyReads != 1 {
		t.Fatal("scenario contract changed")
	}
	for _, messages := range f.messages {
		var sent []string
		for _, raw := range messages {
			var m historyMessage
			json.Unmarshal(raw, &m)
			if m.Role == "user" {
				sent = append(sent, m.Parts[0].Text)
			}
		}
		if !reflect.DeepEqual(sent, generalBenchQuestions) {
			t.Fatal("built-in questions not sent unchanged")
		}
	}
	dir := filepath.Dir(cfg.RawReportPath)
	runs, err := readHTMLRuns(dir)
	if err != nil {
		t.Fatal(err)
	}
	var spans []map[string]any
	for _, run := range runs {
		for _, turn := range run.Turns {
			span := testOTLPSpan(turn.Detail.start, newExchangeID()[:16], turn.Detail.RootID, "runtime", 0, time.Nanosecond)
			span["traceId"] = turn.Detail.TraceID
			spans = append(spans, span)
		}
	}
	traceFile := writeOTLP(t, spans...)
	traceData, err := os.ReadFile(traceFile)
	if err != nil {
		t.Fatal(err)
	}
	collector := &benchCollector{node: "k3d-fred-agent-0", directory: "/test", command: func(_ context.Context, name string, args ...string) ([]byte, error) {
		if name != "docker" || len(args) < 4 {
			t.Fatal("unexpected trace operation")
		}
		switch args[2] {
		case "find":
			return []byte("/test/traces.otlp.jsonl\n"), nil
		case "cat":
			return traceData, nil
		}
		t.Fatal("mutating trace operation")
		return nil, nil
	}}
	matched, clean, err := collector.collect(context.Background(), dir)
	if err != nil || matched != 10 || clean != 10 {
		t.Fatalf("trace snapshot coverage: %d/%d %v", matched, clean, err)
	}
	if err := generateHTMLReport(dir, filepath.Join(dir, "report.html")); err != nil {
		t.Fatal(err)
	}
	docs := documentBenchQuestions("RAGuard")
	if len(docs) != 10 {
		t.Fatal("document questions")
	}
	for _, q := range docs {
		if !strings.Contains(q, "RAGuard") {
			t.Fatal("topic missing")
		}
	}
}

func TestBenchCollectorReadOnlyDiscoveryAndFiltering(t *testing.T) {
	volume := "pvc-00000000-0000-0000-0000-000000000001"
	directory := "/var/lib/rancher/k3s/storage/" + volume + "_fred-infra_otel-traces"
	calls := []string{}
	command := func(ctx context.Context, name string, args ...string) ([]byte, error) {
		call := name + " " + strings.Join(args, " ")
		calls = append(calls, call)
		switch call {
		case "kubectl --context k3d-fred -n fred-infra get deployment otel-collector -o json":
			return []byte(`{"status":{"readyReplicas":1}}`), nil
		case "kubectl --context k3d-fred -n fred-infra get pvc otel-traces -o json":
			return []byte(`{"spec":{"volumeName":"` + volume + `"}}`), nil
		case "kubectl --context k3d-fred get pv " + volume + " -o json":
			return []byte(`{"spec":{"local":{"path":"` + directory + `"},"nodeAffinity":{"required":{"nodeSelectorTerms":[{"matchExpressions":[{"key":"kubernetes.io/hostname","operator":"In","values":["k3d-fred-agent-0"]}]}]}}}}`), nil
		case "docker exec k3d-fred-agent-0 find " + directory + " -maxdepth 1 -type f -name traces*.jsonl -print":
			return []byte(directory + "/traces.otlp.jsonl\n" + directory + "/traces.otlp-2026-11-16T12-00-00.000.jsonl\n"), nil
		default:
			t.Error("unexpected infrastructure action", call)
			return nil, fmt.Errorf("unexpected command")
		}
	}
	collector, err := discoverBenchCollector(context.Background(), command)
	if err != nil || collector.node != "k3d-fred-agent-0" || len(calls) != 4 {
		t.Fatalf("%+v %v", collector, err)
	}
	raw := `{"resourceSpans":[{"resource":{"attributes":[{"key":"private","value":{"stringValue":"PRIVATE"}}]},"scopeSpans":[{"spans":[{"traceId":"abc","spanId":"1111111111111111","startTimeUnixNano":"100","endTimeUnixNano":"200","name":"PRIVATE","attributes":[{"key":"prompt","value":{"stringValue":"PRIVATE"}},{"key":"fred.category","value":{"stringValue":"runtime","intValue":"PRIVATE"}}]},{"traceId":"other","name":"PRIVATE"}]}]}]}`
	var out bytes.Buffer
	if err := filterBenchTraces([]byte(raw+"\n{\"resourceSpans\":"), map[string]bool{"abc": true}, &out); err != nil {
		t.Fatal(err)
	}
	if strings.Contains(out.String(), "PRIVATE") || strings.Contains(out.String(), "other") || !strings.Contains(out.String(), "runtime") {
		t.Fatal("unrelated trace/content leaked", out.String())
	}
	// Client completion alone is never evidence of server trace coverage.
	matched, complete, _ := benchTraceCoverage([]htmlRun{{Turns: []htmlTurn{{Detail: &htmlTurnDetail{Complete: true}}}}})
	if matched != 0 || complete != 0 {
		t.Fatal("invented server coverage")
	}
}

func TestBenchPrivatePreferencesAndPlainMenu(t *testing.T) {
	t.Setenv("BENCH_STATE_DIR", filepath.Join(t.TempDir(), "state"))
	dir, err := benchStateDirectory()
	if err != nil {
		t.Fatal(err)
	}
	p := benchPreferences{Origin: "http://weaver.localhost:8088", Space: testSpace, Agent: testInstance, LastRun: "run-test"}
	if err := saveBenchPreferences(dir, p); err != nil {
		t.Fatal(err)
	}
	got, err := readBenchPreferences(dir)
	if err != nil || got != p {
		t.Fatal(got, err)
	}
	info, _ := os.Stat(filepath.Join(dir, "preferences.json"))
	if info.Mode().Perm() != 0600 {
		t.Fatal("preferences not private")
	}
	var out bytes.Buffer
	u := &benchUI{ctx: context.Background(), input: make(chan byte, 4), out: &out}
	u.input <- '2'
	u.input <- '\n'
	choice, err := u.choose("Agent", []string{"First", "Benchmark\x1b[31m"}, 0)
	if err != nil || choice != 1 || strings.Contains(out.String(), "\x1b") {
		t.Fatal("plain menu/control stripping", choice, err)
	}
	for _, bad := range []string{"http://example.com", "https://user:secret@example.com", "https://example.com?token=x"} {
		if _, err := secureBenchURL(bad); err == nil {
			t.Fatal("unsafe address", bad)
		}
	}
}

// Invoked only by a local pseudo-terminal check; never connects to Fred.
func TestBenchTerminalHelper(t *testing.T) {
	if os.Getenv("BENCH_TERMINAL_TEST") != "1" {
		return
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	u := newBenchUI(ctx)
	index, err := u.choose("Agent", []string{"First", "Benchmark", "Third"}, 0)
	if err != nil {
		fmt.Println("CANCELLED")
		return
	}
	answer, err := u.ask("Sujet", "")
	if err != nil {
		t.Fatal(err)
	}
	fmt.Printf("SELECTED=%d TOPIC=%s\n", index, answer)
}

func TestBenchLocalKeycloakAliases(t *testing.T) {
	for _, tc := range []struct {
		name, host string
		addresses  []string
		fail, want bool
	}{
		{name: "factory alias", host: "keycloak", addresses: []string{"127.0.0.1"}, want: true},
		{name: "compose alias", host: "app-keycloak", addresses: []string{"127.0.0.1", "::1"}, want: true},
		{name: "remote", host: "keycloak", addresses: []string{"192.0.2.1"}},
		{name: "mixed", host: "keycloak", addresses: []string{"127.0.0.1", "192.0.2.1"}},
		{name: "empty", host: "keycloak"},
		{name: "lookup failure", host: "keycloak", fail: true},
		{name: "unrecognized", host: "other.example", addresses: []string{"127.0.0.1"}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			lookup := func(ctx context.Context, host string) ([]net.IPAddr, error) {
				if host != tc.host {
					t.Fatal("wrong alias lookup")
				}
				if _, ok := ctx.Deadline(); !ok {
					t.Fatal("unbounded DNS lookup")
				}
				if tc.fail {
					return nil, fmt.Errorf("lookup failed")
				}
				var addresses []net.IPAddr
				for _, ip := range tc.addresses {
					addresses = append(addresses, net.IPAddr{IP: net.ParseIP(ip)})
				}
				return addresses, nil
			}
			if got := benchLoopbackAlias(tc.host, lookup); got != tc.want {
				t.Fatalf("allowed=%v want=%v", got, tc.want)
			}
		})
	}
}

func TestBenchLoginConfigurationErrors(t *testing.T) {
	valid := benchPublicAuth{Enabled: true, Realm: "http://localhost/realms/app", ClientID: "app", Provider: "keycloak", UIDClaim: "sub"}
	for _, tc := range []struct {
		name, want string
		change     func(*benchPublicAuth)
	}{
		{"URL", "invalid Keycloak URL", func(a *benchPublicAuth) { a.Realm = "http://remote.example/realms/app" }},
		{"disabled", "authentication is not enabled", func(a *benchPublicAuth) { a.Enabled = false }},
		{"client", "Keycloak client is missing", func(a *benchPublicAuth) { a.ClientID = "" }},
		{"provider", "Keycloak identity provider", func(a *benchPublicAuth) { a.Provider = "oidc" }},
		{"claim", "sub identity claim", func(a *benchPublicAuth) { a.UIDClaim = "email" }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			a := valid
			tc.change(&a)
			// Invalid configuration must be classified before any HTTP or browser call.
			_, err := browserBenchLogin(context.Background(), a, nil, nil, nil)
			if err == nil || !strings.Contains(err.Error(), tc.want) {
				t.Fatalf("%v; want %s", err, tc.want)
			}
		})
	}
}

func TestBenchHelpAndUsageHaveNoSideEffects(t *testing.T) {
	var cases [][]string
	for _, alias := range []string{"-h", "--h", "-help", "--help", "help"} {
		cases = append(cases, []string{alias}, []string{"run", alias}, []string{"report", alias})
	}
	cases = append(cases, []string{"help", "run"}, []string{"help", "report"})
	for _, args := range cases {
		t.Run(strings.Join(args, " "), func(t *testing.T) {
			state := filepath.Join(t.TempDir(), "must-not-be-created")
			cmd := exec.Command(os.Args[0], "-test.run=^TestCLIHelper$")
			cmd.Env = append(os.Environ(), "BENCH_TEST_CLI=1", "BENCH_TEST_ARGS="+strings.Join(args, "\n"), "BENCH_STATE_DIR="+state, "GORACE=atexit_sleep_ms=0")
			var out, stderr bytes.Buffer
			cmd.Stdout = &out
			cmd.Stderr = &stderr
			if err := cmd.Run(); err != nil {
				t.Fatalf("help failed: %v %s", err, stderr.String())
			}
			if stderr.Len() != 0 || !strings.Contains(out.String(), "Usage:") || !strings.Contains(out.String(), "Options:") {
				t.Fatalf("invalid help streams: %s / %s", out.String(), stderr.String())
			}
			if _, err := os.Stat(state); !os.IsNotExist(err) {
				t.Fatal("help created local state")
			}
		})
	}
	for _, args := range [][]string{{"unknown"}, {"help", "unknown"}, {"run", "--unknown"}, {"report", "--unknown"}} {
		t.Run(strings.Join(args, " "), func(t *testing.T) {
			cmd := exec.Command(os.Args[0], "-test.run=^TestCLIHelper$")
			state := filepath.Join(t.TempDir(), "must-not-be-created")
			cmd.Env = append(os.Environ(), "BENCH_TEST_CLI=1", "BENCH_TEST_ARGS="+strings.Join(args, "\n"), "BENCH_STATE_DIR="+state, "GORACE=atexit_sleep_ms=0")
			var out, stderr bytes.Buffer
			cmd.Stdout = &out
			cmd.Stderr = &stderr
			err := cmd.Run()
			if exit, ok := err.(*exec.ExitError); !ok || exit.ExitCode() != 2 || out.Len() != 0 || stderr.Len() == 0 {
				t.Fatalf("expected usage error on stderr, exit 2; got %v, %s / %s", err, out.String(), stderr.String())
			}
			if _, err := os.Stat(state); !os.IsNotExist(err) {
				t.Fatal("invalid command created local state")
			}
		})
	}
}

func TestBenchRunSavesJSONWithoutHTML(t *testing.T) {
	// Isolated Fred fixture only. No desktop opener is available to this test.
	t.Setenv("PATH", t.TempDir())
	for _, failWarmup := range []bool{false, true} {
		t.Run(fmt.Sprintf("warmup_failure=%v", failWarmup), func(t *testing.T) {
			f := newScenarioFixture(t)
			f.failLogin = failWarmup
			cfg := fixtureConfig(f, "weaver", "shared")
			cfg.Mode, cfg.TotalTurns, cfg.WarmupTurns = "performance", 3, 2
			cfg.ConcurrencySteps, cfg.Questions = "1", generalBenchQuestions
			cfg.DeleteSession = false
			rate := 0.0
			cfg.TraceTurns, cfg.TraceSampleRate = true, &rate
			dir := t.TempDir()
			cfg.RawReportPath, cfg.JSONReportPath = filepath.Join(dir, "conversation.jsonl"), filepath.Join(dir, "summary.json")
			var out bytes.Buffer
			u := &benchUI{ctx: context.Background(), out: &out}
			err := executeInteractiveBench(context.Background(), u, cfg, nil, dir)
			if (err != nil) != failWarmup {
				t.Fatalf("unexpected outcome: %v", err)
			}
			if _, err := os.Stat(filepath.Join(dir, "report.html")); !os.IsNotExist(err) {
				t.Fatal("run generated HTML")
			}
			if strings.Contains(out.String(), "Report opened") || strings.Contains(out.String(), "Reopen:") {
				t.Fatal("run advertised HTML")
			}
			warmFile := filepath.Join(dir, "warmup", "conversation.jsonl")
			if _, err := os.Stat(warmFile); err != nil || !strings.Contains(out.String(), warmFile) {
				t.Fatal("warmup artifact missing from output")
			}
			if failWarmup {
				if _, err := os.Stat(cfg.RawReportPath); !os.IsNotExist(err) {
					t.Fatal("measurement started after failed warmup")
				}
				return
			}
			var summary scenarioReport
			data, err := os.ReadFile(cfg.JSONReportPath)
			if err != nil || json.Unmarshal(data, &summary) != nil {
				t.Fatal("missing canonical summary")
			}
			if summary.Steps[0].Success != 3 || f.executions != 5 {
				t.Fatal("warmup leaked into measured KPIs")
			}
			for _, want := range []string{"3/3 successful", "CPU/RAM not measured", cfg.RawReportPath, cfg.JSONReportPath} {
				if !strings.Contains(out.String(), want) {
					t.Fatalf("recap missing %q: %s", want, out.String())
				}
			}
		})
	}
}

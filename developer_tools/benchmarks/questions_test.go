package main

import (
	"encoding/json"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestQuestionsInputValidation(t *testing.T) {
	for _, content := range []string{`[]`, `[""]`, `["  "]`, `[null]`, `[123]`, `{"question":"x"}`, `["x"] trailing`, `[` + strings.Repeat(`"x",`, 100) + `"x"]`} {
		path := filepath.Join(t.TempDir(), "questions.json")
		if err := os.WriteFile(path, []byte(content), 0600); err != nil {
			t.Fatal(err)
		}
		if _, err := scenarioQuestions(config{QuestionsFile: path}); err == nil {
			t.Fatal("invalid questions accepted", content)
		}
	}
	path := filepath.Join(t.TempDir(), "questions.json")
	if err := os.WriteFile(path, []byte(`["Question 1", "Question 2"]`), 0600); err != nil {
		t.Fatal(err)
	}
	for _, option := range []string{"message", "requests-per-client"} {
		if _, err := scenarioQuestions(config{QuestionsFile: path, ExplicitFlags: []string{option}}); err == nil {
			t.Fatal("ambiguous input accepted")
		}
	}
	cfg, err := scenarioQuestions(config{QuestionsFile: path})
	if err != nil || cfg.RequestsPerClient != 2 || cfg.ConcurrencySteps != "1" || !reflect.DeepEqual(cfg.Questions, []string{"Question 1", "Question 2"}) {
		t.Fatalf("%+v %v", cfg, err)
	}
}

// Exercise the real CLI, the agent HTTP protocol and the report together. The
// fixture supplies arbitrary natural-language answers, never a provider oracle.
func TestTenQuestionsBearerTraceAndHTMLReport(t *testing.T) {
	dir := t.TempDir()
	questions := make([]string, 10)
	for i := range questions {
		questions[i] = "PRIVATE_QUESTION " + strconv.Itoa(i+1)
	}
	data, _ := json.Marshal(questions)
	questionFile := filepath.Join(t.TempDir(), "questions.json")
	if err := os.WriteFile(questionFile, data, 0600); err != nil {
		t.Fatal(err)
	}
	var mu sync.Mutex
	var spans []map[string]any
	f := newScenarioFixture(t, func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			start := time.Now()
			next.ServeHTTP(w, r)
			if strings.HasSuffix(r.URL.Path, "/agents/execute/stream") {
				parts := strings.Split(r.Header.Get("traceparent"), "-")
				if len(parts) != 4 {
					t.Error("missing traceparent")
					return
				}
				span := testOTLPSpan(start, newExchangeID()[:16], parts[2], "runtime", 0, time.Since(start))
				span["traceId"] = parts[1]
				mu.Lock()
				spans = append(spans, span)
				mu.Unlock()
			}
		})
	})
	raw := filepath.Join(dir, "conversation.jsonl")
	args := []string{"-scenario=conversation", "-target=weaver", "-protocol=sse", "-fred-origin=" + f.server.URL, "-space-id=" + testSpace, "-agent-instance-id=" + testInstance, "-questions-file=" + questionFile, "-trace-turns", "-delete-session=false", "-raw-report=" + raw}
	cmd := exec.Command(os.Args[0], "-test.run=^TestCLIHelper$")
	cmd.Env = append(os.Environ(), "BENCH_TEST_CLI=1", "AGENTIC_TOKEN="+testJWT("private-user-0"), "BENCH_TEST_ARGS="+strings.Join(args, "\n"))
	if output, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("CLI: %v %s", err, output)
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.executions != 10 || f.logins != 0 || f.historyReads != 1 || f.deletes != 0 {
		t.Fatalf("executions/login/history/delete %d/%d/%d/%d", f.executions, f.logins, f.historyReads, f.deletes)
	}
	for _, messages := range f.messages {
		var sent []string
		for _, rawMessage := range messages {
			var m historyMessage
			if err := json.Unmarshal(rawMessage, &m); err != nil {
				t.Fatal(err)
			}
			if m.Role == "user" {
				sent = append(sent, m.Parts[0].Text)
			}
		}
		if !reflect.DeepEqual(sent, questions) {
			t.Fatal("questions changed or reordered")
		}
	}
	mu.Lock()
	traceFile := writeOTLP(t, spans...)
	mu.Unlock()
	output := filepath.Join(dir, "report.html")
	if err := generateHTMLReport(dir, output, traceFile); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(raw)
	if err != nil {
		t.Fatal(err)
	}
	run, _, err := readHTMLRun(strings.NewReader(string(data)))
	if err != nil || run.Status != "OK" || len(run.Turns) != 10 || run.Steps[0].HistoryVerified != 1 {
		t.Fatalf("report: %+v %v", run, err)
	}
	runs := []htmlRun{*run}
	if err := attachOTLPTraces(runs, traceFile); err != nil {
		t.Fatal(err)
	}
	for _, turn := range runs[0].Turns {
		if len(turn.Detail.Spans) != 1 {
			t.Fatal("missing turn trace")
		}
	}
	html, err := os.ReadFile(output)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(data)+string(html), "PRIVATE") || strings.Contains(string(data)+string(html), testJWT("private-user-0")) {
		t.Fatal("private content exported")
	}
}

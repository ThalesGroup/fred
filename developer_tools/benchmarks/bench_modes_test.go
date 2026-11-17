package main

import (
	"context"
	"encoding/json"
	"math"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
)

func TestBenchModeDefaultsAndLimits(t *testing.T) {
	for _, mode := range []string{"diagnostic", "performance"} {
		o, err := (benchOptions{mode: mode, warmup: -1, sampleRate: -1}).resolved()
		if err != nil {
			t.Fatal(err)
		}
		if mode == "diagnostic" && (o.requests != 10 || o.concurrency != 1 || o.warmup != 0 || o.sampleRate != 1) {
			t.Fatal(o)
		}
		if mode == "performance" && (o.requests != 1000 || o.concurrency != 10 || o.warmup != 20 || o.sampleRate != 0) {
			t.Fatal(o)
		}
	}
	for _, o := range []benchOptions{
		{mode: "unknown"}, {mode: "performance", requests: 50001},
		{mode: "performance", requests: 23, concurrency: 4}, {mode: "performance", warmup: 1001},
		{mode: "performance", sampleRate: math.NaN()}, {mode: "performance", sampleRate: 1.01},
		{mode: "diagnostic", requests: 100},
	} {
		if _, err := o.resolved(); err == nil {
			t.Fatalf("accepted %+v", o)
		}
	}
}

// Real HTTP adapters and the canonical report, backed only by a local fixture.
func TestPerformanceConversationsSamplingAndReport(t *testing.T) {
	for _, rate := range []float64{0, 1} {
		t.Run(map[float64]string{0: "unsampled", 1: "sampled"}[rate], func(t *testing.T) {
			var mu sync.Mutex
			turnHeaders := 0
			f := newScenarioFixture(t, func(next http.Handler) http.Handler {
				return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					flags := "00"
					isTurn := strings.HasSuffix(r.URL.Path, "/prepare-execution") || strings.HasSuffix(r.URL.Path, "/agents/execute/stream")
					if isTurn && rate == 1 {
						flags = "01"
					}
					// The first preflight prepare request runs outside any measured turn.
					if isTurn && r.URL.Query().Get("session_id") == "" && !strings.HasSuffix(r.URL.Path, "/agents/execute/stream") {
						flags = "00"
					}
					parent := r.Header.Get("traceparent")
					if len(parent) != 55 || !strings.HasSuffix(parent, "-"+flags) {
						t.Errorf("%s: traceparent=%q, want %s", r.URL.Path, parent, flags)
					}
					if strings.HasSuffix(r.URL.Path, "/agents/execute/stream") {
						mu.Lock()
						turnHeaders++
						mu.Unlock()
					}
					next.ServeHTTP(w, r)
				})
			})
			cfg := fixtureConfig(f, "weaver", "shared")
			cfg.Mode, cfg.TotalTurns, cfg.ConcurrencySteps = "performance", 23, "2"
			cfg.Questions, cfg.TraceTurns, cfg.TraceSampleRate = generalBenchQuestions, true, &rate
			cfg.RawReportPath = filepath.Join(t.TempDir(), "conversation.jsonl")
			var rows []scenarioTurn
			cfg.ObserveTurn = func(row scenarioTurn) { rows = append(rows, row) }
			report, err := runScenario(context.Background(), cfg)
			if err != nil {
				t.Fatal(err)
			}
			if report.Outcome != "OK" || len(rows) != 23 {
				t.Fatalf("%+v rows=%d", report, len(rows))
			}
			step := report.Steps[0]
			if step.Success != 23 || step.HistoryVerified != 3 || step.All.TotalEOF.Count != 23 || step.First.Turns != 3 || step.Following.Turns != 20 || step.SuccessfulTurnsPerSecond <= 0 {
				t.Fatalf("%+v", step)
			}
			perConversation := map[int]int{}
			for _, row := range rows {
				perConversation[row.ConversationIndex]++
				if (row.TraceID != "") != (rate == 1) {
					t.Fatal("wrong sampled trace export")
				}
			}
			if perConversation[1] != 10 || perConversation[2] != 10 || perConversation[3] != 3 {
				t.Fatal(perConversation)
			}
			f.mu.Lock()
			registrations, deletes := f.registrations, f.deletes
			f.mu.Unlock()
			if registrations != 3 || deletes != 3 || turnHeaders != 23 {
				t.Fatalf("created=%d deleted=%d executed=%d", registrations, deletes, turnHeaders)
			}
			runs, err := readHTMLRuns(filepath.Dir(cfg.RawReportPath))
			if err != nil || len(runs) != 1 || runs[0].Status != "OK" || len(runs[0].Turns) != 23 {
				t.Fatalf("report: %+v %v", runs, err)
			}
			if err := generateHTMLReport(filepath.Dir(cfg.RawReportPath), filepath.Join(filepath.Dir(cfg.RawReportPath), "report.html")); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestPerformanceFailureStopsOnlyAffectedConversation(t *testing.T) {
	f := newScenarioFixture(t)
	f.badStream = true
	cfg := fixtureConfig(f, "weaver", "shared")
	cfg.Mode, cfg.TotalTurns, cfg.ConcurrencySteps = "performance", 23, "2"
	cfg.Questions = generalBenchQuestions
	report, err := runScenario(context.Background(), cfg)
	if err != nil {
		t.Fatal(err)
	}
	s := report.Steps[0]
	if report.Outcome != "DEGRADED" || s.Attempted != 6 || s.Success != 3 || s.Errors != 3 || s.NotStarted != 17 {
		t.Fatalf("%+v", report)
	}
	runs, err := readHTMLRuns(filepath.Dir(cfg.RawReportPath))
	if err != nil || runs[0].Status != "DEGRADED" {
		t.Fatalf("%+v %v", runs, err)
	}
}

func TestWarmupCleanupDeferredAndExcluded(t *testing.T) {
	f := newScenarioFixture(t)
	parent := t.TempDir()
	warm := filepath.Join(parent, "warmup")
	if err := os.Mkdir(warm, 0700); err != nil {
		t.Fatal(err)
	}
	cfg := fixtureConfig(f, "weaver", "shared")
	cfg.Mode, cfg.TotalTurns, cfg.ConcurrencySteps = "performance", 3, "1"
	cfg.Questions = generalBenchQuestions
	cfg.RawReportPath = filepath.Join(warm, "conversation.jsonl")
	var cleanup []func() int
	cfg.DeferCleanup = func(close func() int) { cleanup = append(cleanup, close) }
	report, err := runScenario(context.Background(), cfg)
	if err != nil || report.Steps[0].CleanupDeferred != 1 || f.deletes != 0 {
		t.Fatalf("%+v %v", report, err)
	}
	cfg.RawReportPath, cfg.JSONReportPath, cfg.DeferCleanup = filepath.Join(parent, "conversation.jsonl"), "", nil
	if _, err := runScenario(context.Background(), cfg); err != nil {
		t.Fatal(err)
	}
	if f.deletes != 1 {
		t.Fatal("warmup deleted during measured phase")
	}
	runs, err := readHTMLRuns(parent)
	if err != nil || len(runs) != 1 || len(runs[0].Turns) != 3 {
		t.Fatalf("warmup leaked: %+v %v", runs, err)
	}
	if len(cleanup) != 1 || cleanup[0]() != 0 || f.deletes != 2 {
		t.Fatal("warmup cleanup failed")
	}
}

func TestPerformanceWriterAndStatistics(t *testing.T) {
	path := filepath.Join(t.TempDir(), "records.jsonl")
	canceled := false
	w, err := newScenarioWriter(path, func() { canceled = true }, true)
	if err != nil {
		t.Fatal(err)
	}
	w.write(map[string]int{"value": 42})
	if err := w.close(); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(path)
	var row map[string]int
	if err != nil || json.Unmarshal(data, &row) != nil || row["value"] != 42 || canceled {
		t.Fatal("buffer did not flush")
	}
	w, err = newScenarioWriter(filepath.Join(t.TempDir(), "bounded.jsonl"), func() { canceled = true }, true)
	if err != nil {
		t.Fatal(err)
	}
	w.write(row)
	w.bytes = 120 << 20
	w.write(row)
	if !canceled || w.close() == nil {
		t.Fatal("size limit not enforced")
	}
	preserved, err := os.ReadFile(w.f.Name())
	if err != nil || !strings.Contains(string(preserved), `"value":42`) {
		t.Fatal("size limit discarded previously accepted records")
	}
	values := make([]float64, 100)
	for i := range values {
		values[i] = float64(i + 1)
	}
	m := metric(values)
	if m.Mean != 50.5 || m.P50 != 50 || m.P95 != 95 || m.P99 != 99 || m.Max != 100 {
		t.Fatal(m)
	}
	dir := t.TempDir()
	large, err := os.Create(filepath.Join(dir, "old"))
	if err != nil {
		t.Fatal(err)
	}
	if err := large.Truncate((512 << 20) + 1); err != nil {
		t.Fatal(err)
	}
	large.Close()
	if checkBenchStorage(dir) == nil {
		t.Fatal("retention threshold not enforced")
	}
}

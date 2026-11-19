package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestScenarioTracePropagationAndLegacyOptOut(t *testing.T) {
	for _, target := range []string{"swift", "weaver"} {
		for _, enabled := range []bool{false, true} {
			t.Run(target+map[bool]string{true: "/traced", false: "/legacy"}[enabled], func(t *testing.T) {
				f := newScenarioFixture(t)
				cfg := fixtureConfig(f, target, "per-conversation")
				cfg.TraceTurns = enabled
				var mu sync.Mutex
				executions := map[string]int{}
				preparations := map[string]int{}
				f.server.Config.Handler = http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					header := r.Header.Get("traceparent")
					if r.Header.Get("baggage") != "" {
						t.Error("unexpected baggage")
					}
					mu.Lock()
					if strings.HasSuffix(r.URL.Path, "/agents/execute/stream") {
						executions[header]++
					} else if strings.HasSuffix(r.URL.Path, "/prepare-execution") && header != "" {
						preparations[header]++
					} else if header != "" {
						t.Errorf("trace leaked outside a turn: %s", r.URL.Path)
					}
					mu.Unlock()
					f.serve(w, r)
				})
				report, err := runScenario(context.Background(), cfg)
				if err != nil || report.Outcome != "OK" {
					t.Fatalf("%v %+v", err, report)
				}
				raw, err := os.ReadFile(cfg.RawReportPath)
				if err != nil {
					t.Fatal(err)
				}
				count := 0
				for _, line := range strings.Split(strings.TrimSpace(string(raw)), "\n") {
					var turn scenarioTurn
					if json.Unmarshal([]byte(line), &turn) != nil || turn.Kind != "turn" {
						continue
					}
					count++
					if !enabled {
						if turn.TraceID != "" || turn.SpanID != "" {
							t.Fatal("legacy changed")
						}
						continue
					}
					if !validTraceHex(turn.TraceID, 32) || !validTraceHex(turn.SpanID, 16) {
						t.Fatal("invalid correlation")
					}
					header := "00-" + turn.TraceID + "-" + turn.SpanID + "-01"
					if executions[header] != 1 {
						t.Fatal("turn not joined to exactly one execution", header)
					}
					if target == "weaver" && preparations[header] != 1 {
						t.Fatal("preparation not correlated")
					}
				}
				if count != 9 {
					t.Fatal("missing turns", count)
				}
				if enabled && len(executions) != count {
					t.Fatal("trace reused between turns")
				}
				if !enabled && (len(executions) != 1 || executions[""] != count) {
					t.Fatal("unexpected legacy headers")
				}
			})
		}
	}
}

func TestTurnTraceReachesActualTokenRefresh(t *testing.T) {
	ctx, trace, err := newTurnTrace(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	seen := ""
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seen = r.Header.Get("traceparent")
		_ = json.NewEncoder(w).Encode(map[string]any{"access_token": testJWT("subject"), "refresh_token": "PRIVATE", "expires_in": 300, "token_type": "Bearer"})
	}))
	defer server.Close()
	identity := &benchmarkIdentity{gate: make(chan struct{}, 1), client: server.Client(), endpoint: server.URL, refresh: "PRIVATE", timeout: time.Second}
	_, phase, err := identity.token(ctx)
	if err != nil || phase == nil || seen != "00-"+trace.TraceID+"-"+trace.SpanID+"-01" {
		t.Fatalf("refresh not correlated: %v", err)
	}
	seen = ""
	_, phase, err = identity.token(ctx)
	if err != nil || phase != nil || seen != "" {
		t.Fatal("cached token fabricated an auth call")
	}
}

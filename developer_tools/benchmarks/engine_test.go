package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"
)

func TestLoadConcurrentClientsSequentialTurns(t *testing.T) {
	const clients, turns = 3, 4
	var mu sync.Mutex
	counts := map[string]int{}
	active := map[string]bool{}
	firstTurns := 0
	barrier := make(chan struct{})
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body sseExecuteRequest
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Error(err)
			return
		}
		if body.AgentInstanceID != "assistant" || body.AgentID != "" || body.RuntimeContext["team_id"] != "team" || r.Header.Get("Authorization") != "Bearer secret" {
			t.Error("Swift managed/auth contract changed")
		}
		mu.Lock()
		if body.SessionID == "" || active[body.SessionID] {
			t.Error("missing conversation or overlapping turns")
		}
		active[body.SessionID] = true
		counts[body.SessionID]++
		if counts[body.SessionID] == 1 {
			firstTurns++
			if firstTurns == clients {
				close(barrier)
			}
		}
		mu.Unlock()
		// No client can complete its first turn until all clients have started.
		select {
		case <-barrier:
		case <-r.Context().Done():
			return
		}
		fmt.Fprint(w, "data:{\"kind\":\"assistant_delta\",\"delta\":\"hello\"}\n\ndata:{\"kind\":\"final\"}\n\n")
		mu.Lock()
		active[body.SessionID] = false
		mu.Unlock()
	}))
	defer server.Close()
	cfg := config{Protocol: "sse", URL: server.URL, Token: "secret", AgentInstanceID: "assistant", SSETeamID: "team", Clients: clients, RequestsPerClient: turns, CreateSession: true, Timeout: 5 * time.Second}
	adapter := newSwiftAdapter(cfg)
	defer adapter.Close()
	results := runLoad(context.Background(), loadPlan{Clients: clients, Turns: turns, Timeout: cfg.Timeout}, adapter.Open)
	if len(results) != clients*turns {
		t.Fatalf("got %d results", len(results))
	}
	last := map[int]int{}
	identities := map[int]string{}
	campaign := results[0].Measurement.CampaignID
	for _, res := range results {
		m := res.Measurement
		if res.Err != nil || m.Outcome != "success" || m.CampaignID != campaign || m.Turn != last[m.ClientID]+1 {
			t.Fatalf("bad result/order: %+v", res)
		}
		if last[m.ClientID] > 0 && identities[m.ClientID] != m.ConversationID {
			t.Fatal("conversation changed")
		}
		last[m.ClientID] = m.Turn
		identities[m.ClientID] = m.ConversationID
	}
	unique := map[string]bool{}
	for _, id := range identities {
		unique[id] = true
	}
	if len(unique) != clients || len(counts) != clients {
		t.Fatal("client isolation failed")
	}
	for _, count := range counts {
		if count != turns {
			t.Fatal("missing turns")
		}
	}
}

type fakeConversation struct {
	id     string
	calls  int
	fail   bool
	closed bool
}

func (c *fakeConversation) ID() string { return c.id }
func (c *fakeConversation) Close()     { c.closed = true }
func (c *fakeConversation) Execute(ctx context.Context) result {
	c.calls++
	now := time.Now()
	r := result{Measurement: turnMeasurement{StartedAt: now, FinalAt: &now}}
	if c.fail {
		r.Err = benchmarkError("execution_error")
	}
	return r
}

func TestLoadFailureIsolationAndTotalMode(t *testing.T) {
	first := &fakeConversation{id: "one", fail: true}
	second := &fakeConversation{id: "two"}
	results := runLoad(context.Background(), loadPlan{Clients: 2, Turns: 3, Timeout: time.Second}, func(ctx context.Context, client int) (conversation, error) {
		if client == 0 {
			return first, nil
		}
		return second, nil
	})
	if len(results) != 4 || first.calls != 1 || second.calls != 3 || !first.closed || !second.closed {
		t.Fatalf("failure contaminated another client: %+v %+v", first, second)
	}
	var mu sync.Mutex
	var conversations []*fakeConversation
	results = runLoad(context.Background(), loadPlan{Clients: 2, Requests: 7, Timeout: time.Second}, func(ctx context.Context, client int) (conversation, error) {
		c := &fakeConversation{}
		mu.Lock()
		conversations = append(conversations, c)
		mu.Unlock()
		return c, nil
	})
	if len(results) != 7 || len(conversations) != 7 {
		t.Fatal("legacy total request count changed")
	}
	for _, c := range conversations {
		if c.calls != 1 || !c.closed {
			t.Fatal("total mode must open/close per request")
		}
	}
}

func TestLoadCanceledRampAndSetupFailure(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	results := runLoad(ctx, loadPlan{Clients: 2, Turns: 3, Ramp: time.Hour, Timeout: time.Second}, func(ctx context.Context, client int) (conversation, error) {
		t.Error("canceled ramp opened conversation")
		return nil, ctx.Err()
	})
	if len(results) != 0 {
		t.Fatal("canceled unsent turns must not be fabricated")
	}
	results = runLoad(context.Background(), loadPlan{Clients: 1, Turns: 3, Timeout: time.Second}, func(context.Context, int) (conversation, error) { return nil, fmt.Errorf("secret prompt URL") })
	if len(results) != 1 || results[0].Measurement.Error != "transport_error" || results[0].Measurement.FinalAt != nil {
		t.Fatalf("setup failure: %+v", results)
	}
}

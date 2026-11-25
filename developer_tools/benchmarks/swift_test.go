package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"nhooyr.io/websocket"
)

func TestSwiftWebSocketCompatibility(t *testing.T) {
	for _, mode := range []string{"persistent", "prepared", "total"} {
		t.Run(mode, func(t *testing.T) {
			var creates, deletes, connections, asks atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Header.Get("Authorization") != "Bearer secret" {
					t.Error("missing authentication")
				}
				if r.Method == http.MethodPost {
					id := creates.Add(1)
					fmt.Fprintf(w, `{"id":"session-%d"}`, id)
					return
				}
				if r.Method == http.MethodDelete {
					deletes.Add(1)
					return
				}
				conn, err := websocket.Accept(w, r, nil)
				if err != nil {
					t.Error(err)
					return
				}
				connections.Add(1)
				defer conn.Close(websocket.StatusNormalClosure, "done")
				for {
					_, data, err := conn.Read(r.Context())
					if err != nil {
						return
					}
					var ask askPayload
					if err := json.Unmarshal(data, &ask); err != nil {
						t.Error(err)
						return
					}
					if ask.Type != "ask" || ask.SessionID == "" || ask.AgentID != "existing-agent" || ask.RuntimeContext.SearchPolicy != "hybrid" || ask.RuntimeContext.SelectedDocumentLibrariesIDs[0] != "library" || ask.ClientExchangeID == "" {
						t.Errorf("invalid ask: %+v", ask)
					}
					asks.Add(1)
					final := `{"type":"final","content":"hello"}`
					if mode == "total" {
						final = `{"type":"final","content":{"structured":"answer"}}`
					}
					for _, event := range []string{`{"type":"stream","content":"hello"}`, final} {
						if err := conn.Write(r.Context(), websocket.MessageText, []byte(event)); err != nil {
							return
						}
					}
				}
			}))
			defer server.Close()
			cfg := config{Protocol: "ws", URL: "ws" + strings.TrimPrefix(server.URL, "http"), SessionURL: server.URL + "/sessions", Token: "secret", AgentID: "existing-agent", AgentUUID: "existing-agent", CreateSession: true, DeleteSession: true, RequestsPerClient: 3, Clients: 2, Timeout: 5 * time.Second, SearchPolicy: "hybrid", DocumentLibraryIDs: []string{"library"}}
			if mode == "prepared" {
				cfg.PrepareSessions = true
			}
			if mode == "total" {
				cfg.RequestsPerClient = 0
				cfg.Requests = 6
			}
			a := newSwiftAdapter(cfg)
			defer a.Close()
			if err := a.Prepare(context.Background()); err != nil {
				t.Fatal(err)
			}
			results := runLoad(context.Background(), loadPlan{Clients: 2, Turns: cfg.RequestsPerClient, Requests: cfg.Requests, Timeout: cfg.Timeout}, a.Open)
			a.Close()
			if len(results) != 6 || asks.Load() != 6 {
				t.Fatalf("results=%d asks=%d", len(results), asks.Load())
			}
			want := int32(2)
			if mode == "total" {
				want = 6
			}
			if creates.Load() != want || deletes.Load() != want || connections.Load() != want {
				t.Fatalf("lifecycle counts: create %d delete %d connections %d, want %d", creates.Load(), deletes.Load(), connections.Load(), want)
			}
			for _, res := range results {
				if res.Err != nil || res.Measurement.FinalAt == nil || res.Measurement.FirstTextAt == nil || res.Measurement.StreamClosedAt != nil {
					t.Fatalf("unexpected WS observation: %+v", res)
				}
			}
		})
	}
}

func TestSwiftSSEQueryAuthentication(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Query().Get("token") != "secret" || r.Header.Get("Authorization") != "" {
			t.Error("query auth changed")
		}
		var body sseExecuteRequest
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Error(err)
		}
		if body.AgentID != "direct" || body.SessionID != "supplied" || body.RuntimeContext["user_id"] != "user" {
			t.Error("direct Swift payload changed")
		}
		fmt.Fprint(w, "data:{\"kind\":\"final\"}\n\n")
	}))
	defer server.Close()
	res := runSSEWithSession(config{URL: server.URL, Token: "secret", TokenInQuery: true, AgentID: "direct", SSEUserID: "user", Timeout: time.Second}, "supplied")
	if res.Err != nil {
		t.Fatal(res.Err)
	}
}

func TestSwiftPreparationCancellationAndCleanup(t *testing.T) {
	var creates, deletes atomic.Int32
	active := make(chan struct{}, 2)
	canceled := make(chan struct{}, 2)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodDelete {
			if r.URL.Path != "/sessions/created" {
				t.Errorf("unexpected cleanup: %s", r.URL.Path)
			}
			deletes.Add(1)
			return
		}
		if _, err := io.Copy(io.Discard, r.Body); err != nil {
			t.Error(err)
			return
		}
		if creates.Add(1) == 1 {
			fmt.Fprint(w, `{"id":"created"}`)
			return
		}
		active <- struct{}{}
		<-r.Context().Done()
		canceled <- struct{}{}
	}))
	defer server.Close()
	cfg := config{Protocol: "ws", SessionURL: server.URL + "/sessions", Clients: 10, RequestsPerClient: 1,
		CreateSession: true, PrepareSessions: true, DeleteSession: true, PrepareConcurrency: 2, Timeout: 5 * time.Second}
	a := newSwiftAdapter(cfg)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan error, 1)
	go func() { done <- a.Prepare(ctx) }()
	// Both workers are in HTTP after the first ID has already been collected.
	for i := 0; i < 2; i++ {
		select {
		case <-active:
		case <-time.After(5 * time.Second):
			t.Fatal("preparation did not reach barrier")
		}
	}
	cancel()
	select {
	case err := <-done:
		if !errors.Is(err, context.Canceled) {
			t.Fatalf("preparation error: %v", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("preparation ignored cancellation")
	}
	for i := 0; i < 2; i++ {
		select {
		case <-canceled:
		case <-time.After(5 * time.Second):
			t.Fatal("active HTTP request was not canceled")
		}
	}
	if creates.Load() != 3 {
		t.Fatalf("queued sessions were created: %d", creates.Load())
	}
	a.Close()
	if deletes.Load() != 1 {
		t.Fatalf("known session was not cleaned after cancellation: %d", deletes.Load())
	}
	// A canceled preparation must not dispatch even its first request.
	if err := a.Prepare(ctx); !errors.Is(err, context.Canceled) {
		t.Fatalf("pre-canceled preparation: %v", err)
	}
	a.Close()
	if creates.Load() != 3 || deletes.Load() != 1 {
		t.Fatal("canceled preparation dispatched work")
	}
}

func TestSwiftLegacyManagedSSEDoesNotRegister(t *testing.T) {
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		if r.URL.Path != "/agents/execute/stream" {
			t.Errorf("unexpected legacy HTTP call: %s", r.URL.Path)
		}
		var body sseExecuteRequest
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Error(err)
		}
		if body.AgentInstanceID != "managed" || len(body.SessionID) != 32 {
			t.Error("legacy managed session changed")
		}
		w.Header().Set("Content-Type", "text/event-stream")
		fmt.Fprint(w, "data: {\"kind\":\"final\"}\n\n")
	}))
	defer server.Close()
	a := newSwiftAdapter(config{Protocol: "sse", URL: server.URL + "/agents/execute/stream", AgentInstanceID: "managed", RequestsPerClient: 1, CreateSession: true, DeleteSession: true, Timeout: time.Second})
	defer a.Close()
	results := runLoad(context.Background(), loadPlan{Clients: 1, Turns: 1, Timeout: time.Second}, a.Open)
	if len(results) != 1 || results[0].Err != nil || calls.Load() != 1 {
		t.Fatalf("legacy lifecycle changed: calls=%d results=%+v", calls.Load(), results)
	}
}

package main

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestSSEStreamOutcomes(t *testing.T) {
	tests := []struct {
		name, stream, wantError string
		text, final             bool
	}{
		{"warning and technical events", "data:{\"kind\":\"status\",\"status\":\"running\"}\n\ndata: {\"kind\":\"node_error\",\"error\":\"warning\"}\n\ndata:{\"kind\":\"final\"}\n\n", "", false, true},
		{"text delta", "data:{\"kind\":\"thought_delta\",\"delta\":\"private\"}\n\ndata:{\"kind\":\"assistant_delta\",\"delta\":\"hello\"}\n\ndata:{\"kind\":\"final\"}\n\n", "", true, true},
		{"empty delta", "data:{\"kind\":\"assistant_delta\",\"delta\":\"\"}\n\ndata:{\"kind\":\"final\"}\n\n", "", false, true},
		{"final text", "data:{\"kind\":\"final\",\"content\":\"hello\"}\n\n", "", true, true},
		{"SSE framing", ": heartbeat\r\nevent: message\r\nid: 1\r\ndata: {\"kind\":\r\ndata: \"final\"}\r\n\r\n", "", false, true},
		{"terminal", "data:{\"kind\":\"execution_error\",\"message\":\"private\"}\n\n", "execution_error", false, false},
		{"bare error", "data:{\"error\":\"private\"}\n\n", "execution_error", false, false},
		{"terminal before final", "data:{\"kind\":\"execution_error\"}\n\ndata:{\"kind\":\"final\"}\n\n", "execution_error", false, true},
		{"terminal after final", "data:{\"kind\":\"final\"}\n\ndata:{\"kind\":\"execution_error\"}\n\n", "execution_error", false, true},
		{"interrupted", "data:{\"kind\":\"execution_interrupted\"}\n\n", "execution_interrupted", false, false},
		{"missing final", "data:{\"kind\":\"status\"}\n\n", "incomplete_stream", false, false},
		{"empty", "", "incomplete_stream", false, false},
		{"unterminated final", "data:{\"kind\":\"final\"}\n", "incomplete_stream", false, false},
		{"truncated after final", "data:{\"kind\":\"final\"}\n\ndata:{", "incomplete_stream", false, true},
		{"malformed", "data:broken\n\ndata:{\"kind\":\"final\"}\n\n", "invalid_event", false, true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { fmt.Fprint(w, tt.stream) }))
			defer server.Close()
			res := runSSEWithSession(config{URL: server.URL, Timeout: 5 * time.Second}, "session")
			gotError := ""
			if res.Err != nil {
				gotError = classifyError(res.Err)
			}
			if gotError != tt.wantError {
				t.Fatalf("error = %q, want %q", gotError, tt.wantError)
			}
			m := res.Measurement
			if (m.FirstTextAt != nil) != tt.text || (m.FinalAt != nil) != tt.final {
				t.Fatalf("unexpected observations: %+v", m)
			}
			if m.StreamClosedAt == nil {
				t.Fatal("clean EOF not measured")
			}
			if m.FinalAt != nil && (m.FinalAt.Before(m.StartedAt) || m.StreamClosedAt.Before(*m.FinalAt) || res.Duration != m.FinalAt.Sub(m.StartedAt)) {
				t.Fatal("final/close/legacy latency order")
			}
		})
	}
}

func TestSSEHTTPFailureAndBrokenBody(t *testing.T) {
	for _, status := range []int{http.StatusUnauthorized, http.StatusTooManyRequests, http.StatusInternalServerError, http.StatusTemporaryRedirect} {
		t.Run(fmt.Sprint(status), func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Location", "/never")
				w.WriteHeader(status)
				fmt.Fprint(w, "private token prompt")
			}))
			defer server.Close()
			res := runSSEWithSession(config{URL: server.URL, Timeout: time.Second}, "")
			if classifyError(res.Err) != "http_status" || res.Measurement.FinalAt != nil || res.Measurement.StreamClosedAt != nil {
				t.Fatalf("unexpected result: %+v", res)
			}
		})
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", "1000")
		fmt.Fprint(w, "data:{\"kind\":\"final\"}\n\n")
	}))
	defer server.Close()
	res := runSSEWithSession(config{URL: server.URL, Timeout: time.Second}, "")
	if res.Err == nil || res.Measurement.FinalAt == nil || res.Measurement.StreamClosedAt != nil {
		t.Fatalf("broken HTTP body accepted: %+v", res)
	}
}

// A deterministic deadline double exercises cancellation during body reading;
// the separate expired-deadline test uses a real context deadline before HTTP.
type deadlineOnCancel struct{ context.Context }

func (c deadlineOnCancel) Err() error {
	if c.Context.Err() != nil {
		return context.DeadlineExceeded
	}
	return nil
}

func TestSSECancelOrTimeoutDuringStream(t *testing.T) {
	for _, afterFinal := range []bool{false, true} {
		for _, reason := range []string{"canceled", "timeout"} {
			t.Run(fmt.Sprintf("%s/final=%t", reason, afterFinal), func(t *testing.T) {
				server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					event := `{"kind":"status","status":"running"}`
					if afterFinal {
						event = `{"kind":"final"}`
					}
					fmt.Fprintf(w, "data:%s\n\n", event)
					w.(http.Flusher).Flush()
					<-r.Context().Done()
				}))
				defer server.Close()
				base, cancel := context.WithCancel(context.Background())
				defer cancel()
				var ctx context.Context = base
				if reason == "timeout" {
					ctx = deadlineOnCancel{base}
				}
				req, _ := http.NewRequestWithContext(ctx, "POST", server.URL, nil)
				client := sseHTTPClient(config{})
				defer client.CloseIdleConnections()
				res := executeSSE(client, req, time.Now(), func(data []byte) (streamEvent, error) {
					event, err := decodeRuntimeEvent(data)
					cancel()
					return event, err
				})
				if classifyError(res.Err) != reason || (res.Measurement.FinalAt != nil) != afterFinal || res.Measurement.StreamClosedAt != nil || res.Measurement.FirstTextAt != nil {
					t.Fatalf("unexpected interrupted stream result: %+v", res)
				}
			})
		}
	}
}

func TestSSETimeout(t *testing.T) {
	// Already expired deadlines avoid fragile assertions on wall-clock delays.
	ctx, cancel := context.WithDeadline(context.Background(), time.Unix(1, 0))
	defer cancel()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Error("expired request reached server") }))
	defer server.Close()
	req, _ := http.NewRequestWithContext(ctx, "POST", server.URL, nil)
	res := executeSSE(server.Client(), req, time.Now(), decodeRuntimeEvent)
	if classifyError(res.Err) != "timeout" || res.Measurement.FirstTextAt != nil || res.Measurement.FinalAt != nil || res.Measurement.StreamClosedAt != nil {
		t.Fatalf("unexpected timeout result: %+v", res)
	}
}

func TestSSEEventSizeBound(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		for i := 0; i < 3; i++ {
			fmt.Fprintln(w, "data:"+strings.Repeat("x", sseMaxLineBytes/2))
		}
	}))
	defer server.Close()
	res := runSSEWithSession(config{URL: server.URL, Timeout: 5 * time.Second}, "")
	if res.Err == nil || res.Measurement.StreamClosedAt != nil {
		t.Fatal("unbounded multi-line event")
	}
}

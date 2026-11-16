package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"net/http"
	"strings"
)

type turnTrace struct{ TraceID, SpanID string }
type turnTraceKey struct{}

// Correlation only: existing client measurements remain the source of timing.
// No SDK/export queue competes with the measured load or captures request data.
func newTurnTrace(ctx context.Context) (context.Context, turnTrace, error) {
	var ids [24]byte
	if _, err := rand.Read(ids[:]); err != nil {
		return ctx, turnTrace{}, benchmarkError("trace_id_unavailable")
	}
	t := turnTrace{hex.EncodeToString(ids[:16]), hex.EncodeToString(ids[16:])}
	if !validTraceHex(t.TraceID, 32) || !validTraceHex(t.SpanID, 16) {
		return ctx, turnTrace{}, benchmarkError("trace_id_unavailable")
	}
	return context.WithValue(ctx, turnTraceKey{}, t), t, nil
}

func injectTurnTrace(req *http.Request) {
	if t, ok := req.Context().Value(turnTraceKey{}).(turnTrace); ok {
		req.Header.Set("traceparent", "00-"+t.TraceID+"-"+t.SpanID+"-01")
	}
}

func validTraceHex(value string, size int) bool {
	return len(value) == size && strings.Trim(value, "0123456789abcdefABCDEF") == "" && strings.Trim(value, "0") != ""
}

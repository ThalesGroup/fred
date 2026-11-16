package main

import (
	"bytes"
	"encoding/json"
	"html/template"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

const testTraceID = "0123456789abcdef0123456789abcdef"
const testRootID = "1111111111111111"

func traceReportFixture(t *testing.T) []htmlRun {
	t.Helper()
	data := rewriteHTMLFixture(t, func(row map[string]any) {
		if row["kind"] == "turn" && row["turn"] == float64(1) {
			row["trace_id"] = testTraceID
			row["span_id"] = testRootID
		}
	})
	run, _, err := readHTMLRun(strings.NewReader(data))
	if err != nil {
		t.Fatal(err)
	}
	return []htmlRun{*run}
}
func testOTLPSpan(start time.Time, id, parent, category string, from, to time.Duration) map[string]any {
	return map[string]any{"traceId": strings.ToUpper(testTraceID), "spanId": id, "parentSpanId": parent, "startTimeUnixNano": strconv.FormatInt(start.Add(from).UnixNano(), 10), "endTimeUnixNano": start.Add(to).UnixNano(), "kind": 3, "name": "PRIVATE_SPAN_NAME", "attributes": []any{map[string]any{"key": "fred.category", "value": map[string]any{"stringValue": category}}, map[string]any{"key": "peer.service", "value": map[string]any{"stringValue": "llm"}}, map[string]any{"key": "prompt", "value": map[string]any{"stringValue": "PRIVATE_PROMPT"}}}}
}
func writeOTLP(t *testing.T, spans ...map[string]any) string {
	t.Helper()
	batch := map[string]any{"resourceSpans": []any{map[string]any{"resource": map[string]any{"attributes": []any{map[string]any{"key": "service.name", "value": map[string]any{"stringValue": "fred-agents"}}, map[string]any{"key": "user.id", "value": map[string]any{"stringValue": "PRIVATE_USER"}}}}, "scopeSpans": []any{map[string]any{"spans": spans}}}}}
	data, err := json.Marshal(batch)
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "traces.otlp.jsonl")
	if err := os.WriteFile(path, append(data, '\n'), 0600); err != nil {
		t.Fatal(err)
	}
	return path
}
func TestOTLPExactJoinUnionPrivacyAndBounds(t *testing.T) {
	runs := traceReportFixture(t)
	d := runs[0].Turns[0].Detail
	start := d.start
	spans := []map[string]any{
		testOTLPSpan(start, "2222222222222222", testRootID, "runtime", 0, time.Second),
		testOTLPSpan(start, "3333333333333333", "2222222222222222", "llm", 100*time.Millisecond, 600*time.Millisecond),
		testOTLPSpan(start, "4444444444444444", "2222222222222222", "llm", 400*time.Millisecond, 800*time.Millisecond),
		testOTLPSpan(start, "5555555555555555", "9999999999999999", "mcp", -time.Second, 200*time.Millisecond),
		testOTLPSpan(start, "6666666666666666", testRootID, "PRIVATE_CATEGORY", 0, 100*time.Millisecond),
	}
	spans = append(spans, spans[1]) // transport retries are not extra work
	foreign := testOTLPSpan(start, "7777777777777777", testRootID, "llm", 0, time.Second)
	foreign["traceId"] = "ffffffffffffffffffffffffffffffff"
	spans = append(spans, foreign)
	path := writeOTLP(t, spans...)
	if err := attachOTLPTraces(runs, path); err != nil {
		t.Fatal(err)
	}
	if len(d.Spans) != 5 || d.Components["llm"] != 700 || d.Components["mcp"] != 200 || d.Components["runtime"] != 1000 {
		t.Fatalf("wrong union or join: %+v", d)
	}
	if len(runs[0].Turns[1].Detail.Spans) != 0 {
		t.Fatal("inferred time-based correlation")
	}
	if len(d.Warnings) < 3 || !strings.Contains(runs[0].TraceImport, "1 sans tour correspondant") {
		t.Fatal("missing incomplete coverage warnings")
	}
	if d.Unattributed == nil || *d.Unattributed != *d.Duration-1000 {
		t.Fatal("unattributed time double-counted")
	}
	var html bytes.Buffer
	if err := template.Must(template.New("report").Parse(reportHTML)).Execute(&html, runs); err != nil {
		t.Fatal(err)
	}
	if strings.Contains(html.String(), "PRIVATE_") {
		t.Fatal("private OTLP data leaked")
	}
	if got := unionIntervals([]htmlInterval{{Start: 0, End: 10}, {Start: 2, End: 3}, {Start: 4, End: 8}, {Start: 10, End: 12}, {Start: 20, End: 25}}); got != 17 {
		t.Fatal("incorrect nested union", got)
	}
}
func TestOTLPInvalidDuplicateCyclesAndUnknownCategory(t *testing.T) {
	for _, mode := range []string{"conflict", "invalid", "cycle", "outside", "unknown", "duplicate_trace"} {
		t.Run(mode, func(t *testing.T) {
			runs := traceReportFixture(t)
			d := runs[0].Turns[0].Detail
			a := testOTLPSpan(d.start, "2222222222222222", testRootID, "llm", 0, time.Second)
			b := testOTLPSpan(d.start, "3333333333333333", "2222222222222222", "mcp", 0, time.Second)
			switch mode {
			case "conflict":
				b["spanId"] = a["spanId"]
			case "invalid":
				a["endTimeUnixNano"] = "0"
			case "cycle":
				a["parentSpanId"] = b["spanId"]
			case "outside":
				a["startTimeUnixNano"] = d.start.Add(time.Hour).UnixNano()
				a["endTimeUnixNano"] = d.start.Add(2 * time.Hour).UnixNano()
			case "unknown":
				a["attributes"] = []any{}
			case "duplicate_trace":
				runs[0].Turns[1].Detail.TraceID = testTraceID
			}
			err := attachOTLPTraces(runs, writeOTLP(t, a, b))
			if mode == "conflict" || mode == "duplicate_trace" {
				if err == nil {
					t.Fatal("ambiguous evidence accepted")
				}
				return
			}
			if err != nil {
				t.Fatal(err)
			}
			if len(d.Warnings) == 0 {
				t.Fatal("missing warning")
			}
			if mode == "outside" || mode == "unknown" {
				if _, ok := d.Components["llm"]; ok {
					t.Fatal("fabricated LLM zero")
				}
			}
		})
	}
}
func TestOTLPLegacyMissingAndAutomaticSidecar(t *testing.T) {
	dir := t.TempDir()
	raw := filepath.Join(dir, "scenario.jsonl")
	if err := os.WriteFile(raw, []byte(htmlFixture(t)), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "traces.otlp.jsonl"), []byte(`{"resourceSpans":[]}`), 0600); err != nil {
		t.Fatal(err)
	}
	if err := generateHTMLReport(dir, filepath.Join(dir, "report.html")); err != nil {
		t.Fatal(err)
	}
	runs, err := readHTMLRuns(dir)
	if err != nil {
		t.Fatal(err)
	}
	for _, turn := range runs[0].Turns {
		if turn.Detail.TraceID != "" || len(turn.Detail.Components) != 0 || len(turn.Detail.Spans) != 0 {
			t.Fatal("legacy traces fabricated")
		}
	}
	if err := attachOTLPTraces(runs, filepath.Join(dir, "missing")); err == nil {
		t.Fatal("explicit missing traces accepted")
	}
	if err := os.WriteFile(filepath.Join(dir, "bad.json"), []byte(`{"data":[]}`), 0600); err != nil {
		t.Fatal(err)
	}
	if err := attachOTLPTraces(runs, filepath.Join(dir, "bad.json")); err == nil {
		t.Fatal("non OTLP payload accepted")
	}
}

func TestOTLPOperationsStatusesFirstChunkAndParentWindow(t *testing.T) {
	runs := traceReportFixture(t)
	d := runs[0].Turns[0].Detail
	parent := testOTLPSpan(d.start, "2222222222222222", testRootID, "runtime", 100*time.Millisecond, 500*time.Millisecond)
	child := testOTLPSpan(d.start, "3333333333333333", "2222222222222222", "llm", 0, time.Second)
	child["name"] = "v2.react.model"
	child["status"] = map[string]any{"code": 2, "message": "PRIVATE_ERROR"}
	child["attributes"] = append(child["attributes"].([]any), map[string]any{"key": "first_chunk_ms", "value": map[string]any{"doubleValue": 12.5}})
	if err := attachOTLPTraces(runs, writeOTLP(t, parent, child, child)); err != nil {
		t.Fatal(err)
	}
	if d.Spans[0].Operation != "v2.react.model" || d.Spans[0].Status != 2 || d.Spans[0].FirstChunk == nil || *d.Spans[0].FirstChunk != 12.5 || d.Spans[1].Operation != "" || d.Spans[1].Status != 0 || d.Spans[1].FirstChunk != nil {
		t.Fatalf("unsafe or missing operation/status/first chunk: %+v", d.Spans)
	}
	if !strings.Contains(strings.Join(d.Warnings, " "), "horloges décalées ou travail asynchrone") || d.Components["llm"] != 1000 {
		t.Fatalf("parent window warning must retain measured duration: %+v", d)
	}
	for _, value := range []any{map[string]any{"stringValue": "12.5"}, map[string]any{"doubleValue": -1}, map[string]any{"doubleValue": "NaN"}, map[string]any{"doubleValue": "Infinity"}, map[string]any{"intValue": "1001"}, map[string]any{"intValue": "1", "doubleValue": 1}} {
		runs := traceReportFixture(t)
		child["attributes"] = []any{map[string]any{"key": "fred.category", "value": map[string]any{"stringValue": "llm"}}, map[string]any{"key": "first_chunk_ms", "value": value}}
		if err := attachOTLPTraces(runs, writeOTLP(t, child)); err != nil {
			t.Fatal(err)
		}
		if runs[0].Turns[0].Detail.Spans[0].FirstChunk != nil {
			t.Fatalf("invalid first chunk retained: %v", value)
		}
	}
}

func TestHTMLTraceJavaScriptInteractions(t *testing.T) {
	node, err := exec.LookPath("node")
	if err != nil {
		t.Skip("node unavailable")
	}
	runs := traceReportFixture(t)
	d := runs[0].Turns[0].Detail
	span := testOTLPSpan(d.start, "2222222222222222", testRootID, "llm", 0, time.Second)
	span["name"] = "v2.react.model"
	span["attributes"] = append(span["attributes"].([]any), map[string]any{"key": "first_chunk_ms", "value": map[string]any{"intValue": "0"}})
	if err := attachOTLPTraces(runs, writeOTLP(t, span)); err != nil {
		t.Fatal(err)
	}
	second, _, err := readHTMLRun(strings.NewReader(htmlFixture(t)))
	if err != nil {
		t.Fatal(err)
	}
	second.Target = "weaver"
	second.Label = "Weaver"
	runs[0].Label = "Swift"
	runs = append(runs, *second)
	var rendered bytes.Buffer
	if err := template.Must(template.New("test").Parse(reportHTML)).Execute(&rendered, runs); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(t.TempDir(), "report.html")
	if err := os.WriteFile(path, rendered.Bytes(), 0600); err != nil {
		t.Fatal(err)
	}
	output, err := exec.Command(node, "report_ui_test.cjs", path).CombinedOutput()
	if err != nil {
		t.Fatalf("DOM interactions: %v\n%s", err, output)
	}
}

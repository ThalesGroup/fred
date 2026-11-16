package main

import (
	"bytes"
	"encoding/json"
	"html/template"
	"math"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

func htmlFixture(t *testing.T) string {
	t.Helper()
	data, err := os.ReadFile("testdata/scenario.jsonl")
	if err != nil {
		t.Fatal(err)
	}
	return string(data)
}
func rewriteHTMLFixture(t *testing.T, change func(map[string]any)) string {
	t.Helper()
	var out strings.Builder
	for _, line := range strings.Split(strings.TrimSpace(htmlFixture(t)), "\n") {
		var value map[string]any
		if err := json.Unmarshal([]byte(line), &value); err != nil {
			t.Fatal(err)
		}
		change(value)
		encoded, err := json.Marshal(value)
		if err != nil {
			t.Fatal(err)
		}
		out.Write(encoded)
		out.WriteByte('\n')
	}
	return out.String()
}
func TestHTMLCanonicalScenarioAndMetrics(t *testing.T) {
	run, _, err := readHTMLRun(strings.NewReader(htmlFixture(t)))
	if err != nil {
		t.Fatal(err)
	}
	if run.Status != "OK" || len(run.Turns) != 10 || run.Steps[0].HistoryVerified != 1 || run.Steps[0].Duration == nil || *run.Steps[0].Duration != 11808.926346 {
		t.Fatalf("unexpected canonical result: %+v", run)
	}
	if run.Turns[0].Metrics["preparation"] != nil || run.Turns[0].Metrics["execution_first_text"] == nil || math.Abs(*run.Turns[0].Metrics["execution_first_text"]-1175.896005) > 0.01 {
		t.Fatalf("wrong metric projection: %+v", run.Turns[0])
	}
}
func TestHTMLInterruptedAndMissingObservations(t *testing.T) {
	data := htmlFixture(t)
	cut := strings.LastIndex(data, `{"kind":"summary"`)
	if cut < 0 {
		t.Fatal("fixture summary missing")
	}
	for _, tail := range []string{"", `{"kind":`} {
		run, _, err := readHTMLRun(strings.NewReader(data[:cut] + tail))
		if err != nil || run.Status != "incomplete" || len(run.Turns) != 10 || run.Profile != "absent" {
			t.Fatalf("partial report lost evidence: %+v %v", run, err)
		}
	}
	data = rewriteHTMLFixture(t, func(v map[string]any) {
		if v["kind"] == "turn" {
			delete(v, "first_text_at")
			delete(v, "execution_started_at")
		}
	})
	run, _, err := readHTMLRun(strings.NewReader(data))
	if err != nil {
		t.Fatal(err)
	}
	for _, row := range run.Turns {
		if row.Metrics["execution_first_text"] != nil || row.Metrics["execution_final"] != nil {
			t.Fatal("fabricated observation")
		}
	}
}
func TestHTMLRejectsMismatchedCampaignAndUnsupportedSchema(t *testing.T) {
	for _, kind := range []string{"turn", "summary", "run"} {
		data := rewriteHTMLFixture(t, func(v map[string]any) {
			if v["kind"] == kind {
				if kind == "run" {
					v["schema_version"] = "v0"
				} else {
					v["campaign_id"] = "another"
				}
			}
		})
		if _, _, err := readHTMLRun(strings.NewReader(data)); err == nil {
			t.Fatalf("accepted mismatched %s", kind)
		}
	}
}
func TestHTMLNeverTrustsSummaryWithoutEvidence(t *testing.T) {
	for _, remove := range []string{"turn", "history"} {
		lines := strings.Split(strings.TrimSpace(htmlFixture(t)), "\n")
		for i, line := range lines {
			if strings.Contains(line, `"kind":"`+remove+`"`) {
				lines = append(lines[:i], lines[i+1:]...)
				break
			}
		}
		run, _, err := readHTMLRun(strings.NewReader(strings.Join(lines, "\n")))
		if err != nil || run.Status != "incomplete" {
			t.Fatalf("trusted incomplete %s: %+v %v", remove, run, err)
		}
	}
	data := rewriteHTMLFixture(t, func(v map[string]any) {
		if v["kind"] == "step" {
			v["load_elapsed_ms"] = 42
		}
	})
	run, _, err := readHTMLRun(strings.NewReader(data))
	if err != nil || run.Status != "incomplete" {
		t.Fatalf("trusted inconsistent step: %+v %v", run, err)
	}
}
func TestHTMLPrivacyAndEscaping(t *testing.T) {
	const secret = `</script><script>alert("PRIVATE")</script>`
	data := rewriteHTMLFixture(t, func(v map[string]any) {
		v["unknown_secret"] = secret
		if _, ok := v["campaign_id"]; ok {
			v["campaign_id"] = secret
		}
		v["identity_id"] = secret
		v["conversation_id"] = secret
		if v["kind"] == "turn" {
			v["error"] = secret
		}
	})
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "scenario.jsonl"), []byte(data), 0600); err != nil {
		t.Fatal(err)
	}
	// Private JSON captures and preparation logs must never enter the parser.
	_ = os.WriteFile(filepath.Join(dir, "credentials.json"), []byte(secret), 0600)
	_ = os.WriteFile(filepath.Join(dir, "swift-prepare.jsonl"), []byte(`{"kind":"auth","unknown_secret":"PRIVATE"}`+"\n"+`{"kind":"preparation_summary","schema_version":"fred.bench.preparation.v1"}`+"\n"), 0600)
	out := filepath.Join(dir, "report.html")
	if err := generateHTMLReport(dir, out); err != nil {
		t.Fatal(err)
	}
	html, err := os.ReadFile(out)
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Contains(html, []byte("PRIVATE")) || bytes.Contains(html, []byte("unknown_secret")) {
		t.Fatal("private input leaked")
	}
	if err := generateHTMLReport(dir, out); err == nil {
		t.Fatal("overwrote existing report")
	}
	var rendered bytes.Buffer
	err = template.Must(template.New("test").Parse(reportHTML)).Execute(&rendered, []htmlRun{{Label: secret}})
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(rendered.String(), secret) || !strings.Contains(rendered.String(), `\u003c/script\u003e`) {
		t.Fatal("script context was not escaped")
	}
}
func TestHTMLOfflineDispatchAndInputPreservation(t *testing.T) {
	dir := t.TempDir()
	data := htmlFixture(t)
	input := filepath.Join(dir, "scenario.jsonl")
	if err := os.WriteFile(input, []byte(data), 0600); err != nil {
		t.Fatal(err)
	}
	cmd := exec.Command(os.Args[0], "-test.run=^TestCLIHelper$")
	cmd.Env = append(os.Environ(), "BENCH_TEST_CLI=1", "BENCH_TEST_ARGS=report\n-input\n"+dir, "AGENTIC_TOKEN=not-used")
	output, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("offline CLI: %v %s", err, output)
	}
	if _, err := os.Stat(filepath.Join(dir, "report.html")); err != nil {
		t.Fatal(err)
	}
	after, _ := os.ReadFile(input)
	if string(after) != data {
		t.Fatal("source changed")
	}
}
func TestHTMLBoundedInputsAndDuplicateRuns(t *testing.T) {
	dir := t.TempDir()
	data := []byte(htmlFixture(t))
	_ = os.WriteFile(filepath.Join(dir, "one.jsonl"), data, 0600)
	_ = os.WriteFile(filepath.Join(dir, "two.jsonl"), data, 0600)
	if _, err := readHTMLRuns(dir); err == nil {
		t.Fatal("duplicate campaign accepted")
	}
	_ = os.Remove(filepath.Join(dir, "two.jsonl"))
	_ = os.Symlink(filepath.Join(dir, "one.jsonl"), filepath.Join(dir, "link.jsonl"))
	if _, err := readHTMLRuns(dir); err == nil {
		t.Fatal("symlink input accepted")
	}
}

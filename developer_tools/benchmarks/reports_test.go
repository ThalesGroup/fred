package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestRawExportPrivacyAndAbsentObservations(t *testing.T) {
	const token, prompt = "secret-bearer", "private complete prompt"
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintf(w, "data:{\"kind\":\"execution_error\",\"message\":%q}\n\n", token+" "+prompt)
	}))
	defer server.Close()
	cfg := config{Protocol: "sse", URL: server.URL + "?token=" + token, Token: token, Message: prompt, SessionID: prompt, RequestsPerClient: 2, Timeout: time.Second}
	a := newSwiftAdapter(cfg)
	defer a.Close()
	results := runLoad(context.Background(), loadPlan{Clients: 1, Turns: 2, Timeout: time.Second}, a.Open)
	path := t.TempDir() + "/nested/turns.jsonl"
	if err := writeRawReport(path, cfg, results); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	for _, secret := range []string{token, prompt, server.URL} {
		if strings.Contains(string(raw), secret) {
			t.Fatalf("raw export leaks %q", secret)
		}
	}
	var row map[string]any
	if err := json.Unmarshal(raw, &row); err != nil {
		t.Fatal(err)
	}
	for _, key := range []string{"first_text_at", "final_at"} {
		if _, ok := row[key]; ok {
			t.Fatalf("absent %s fabricated", key)
		}
	}
	for _, key := range []string{"schema_version", "campaign_id", "client_id", "conversation_id", "turn", "started_at", "stream_closed_at", "outcome", "error"} {
		if _, ok := row[key]; !ok {
			t.Fatalf("missing %s", key)
		}
	}
	if row["target"] != "swift" || row["preparation_mode"] != "not_performed" || row["preparation"] != nil || row["execution_started_at"] != nil || row["schema_version"] != "fred.bench.turn.v1" || row["error"] != "execution_error" || row["outcome"] != "error" {
		t.Fatalf("unexpected schema: %s", raw)
	}
	info, _ := os.Stat(path)
	if info.Mode().Perm() != 0o600 {
		t.Fatal("raw export must be private")
	}
	if err := writeRawReport(path, cfg, results); err == nil {
		t.Fatal("raw export overwrote existing evidence")
	}
}

func TestReportURLsAndErrorsAreRedacted(t *testing.T) {
	cfg := config{Protocol: "sse", URL: "http://user:password@example.invalid/path?token=query-secret#fragment-secret", Token: "bearer-secret", Message: "private prompt"}
	output := captureStdout(t, func() {
		printConfigRecap(cfg, true, 1, 1)
		printSummary(cfg, 1, nil, 1, []string{cfg.Token + " " + cfg.Message}, time.Second, 0)
	})
	report, err := json.Marshal(buildJSONReport(cfg, 1, nil, 1, []string{cfg.Token + " " + cfg.Message}, time.Second))
	if err != nil {
		t.Fatal(err)
	}
	for _, secret := range []string{"password", "query-secret", "fragment-secret", cfg.Token, cfg.Message} {
		if strings.Contains(output, secret) || strings.Contains(string(report), secret) {
			t.Fatalf("report leaks %q", secret)
		}
	}
}

func TestSummaryRejectsRawFileAliases(t *testing.T) {
	for _, alias := range []string{"directory_symlink", "file_symlink", "hard_link"} {
		t.Run(alias, func(t *testing.T) {
			dir := t.TempDir()
			rawPath := filepath.Join(dir, "results", "run.jsonl")
			if err := writeRawReport(rawPath, config{Protocol: "sse"}, []result{{Measurement: turnMeasurement{SchemaVersion: "fred.bench.turn.v1"}}}); err != nil {
				t.Fatal(err)
			}
			before, err := os.ReadFile(rawPath)
			if err != nil {
				t.Fatal(err)
			}
			summaryPath := filepath.Join(dir, "summary.json")
			switch alias {
			case "directory_symlink":
				if err := os.Symlink(filepath.Dir(rawPath), filepath.Join(dir, "latest")); err != nil {
					t.Fatal(err)
				}
				summaryPath = filepath.Join(dir, "latest", "run.jsonl")
			case "file_symlink":
				if err := os.Symlink(rawPath, summaryPath); err != nil {
					t.Fatal(err)
				}
			case "hard_link":
				if err := os.Link(rawPath, summaryPath); err != nil {
					t.Fatal(err)
				}
			}
			if err := writeJSONReport(summaryPath, benchmarkJSONReport{SchemaVersion: "v1"}, rawPath); err == nil || !strings.Contains(err.Error(), "same file") {
				t.Fatalf("alias not rejected: %v", err)
			}
			after, err := os.ReadFile(rawPath)
			if err != nil {
				t.Fatal(err)
			}
			if !bytes.Equal(before, after) {
				t.Fatal("raw measurements were changed")
			}
			// A distinct, existing summary can still be replaced without touching raw.
			distinct := filepath.Join(dir, "distinct.json")
			if err := os.WriteFile(distinct, bytes.Repeat([]byte("x"), 4096), 0o600); err != nil {
				t.Fatal(err)
			}
			if err := writeJSONReport(distinct, benchmarkJSONReport{SchemaVersion: "v1"}, rawPath); err != nil {
				t.Fatal(err)
			}
			data, err := os.ReadFile(distinct)
			if err != nil || !json.Valid(data) {
				t.Fatalf("summary replacement failed: %v", err)
			}
		})
	}
}

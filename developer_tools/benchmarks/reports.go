package main

import (
	"encoding/json"
	"fmt"
	"math"
	"net/url"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

const (
	colorReset  = "\033[0m"
	colorBold   = "\033[1m"
	colorDim    = "\033[2m"
	colorRed    = "\033[31m"
	colorGreen  = "\033[32m"
	colorYellow = "\033[33m"
	colorCyan   = "\033[36m"
)

type benchmarkLatencyReport struct {
	Min int64 `json:"min_ms"`
	Avg int64 `json:"avg_ms"`
	P50 int64 `json:"p50_ms"`
	P95 int64 `json:"p95_ms"`
	P99 int64 `json:"p99_ms"`
	Max int64 `json:"max_ms"`
}

type benchmarkJSONReport struct {
	SchemaVersion     string                  `json:"schema_version"`
	GeneratedAt       string                  `json:"generated_at"`
	Outcome           string                  `json:"outcome"`
	Protocol          string                  `json:"protocol"`
	Target            string                  `json:"target"`
	SSEMode           string                  `json:"sse_mode,omitempty"`
	AgentID           string                  `json:"agent_id,omitempty"`
	AgentInstanceID   string                  `json:"agent_instance_id,omitempty"`
	SpaceID           string                  `json:"space_id,omitempty"`
	CleanupErrors     int                     `json:"cleanup_errors,omitempty"`
	TeamID            string                  `json:"team_id,omitempty"`
	Clients           int                     `json:"clients"`
	RequestsPerClient int                     `json:"requests_per_client,omitempty"`
	TotalRequests     int                     `json:"total_requests"`
	Success           int                     `json:"success"`
	Errors            int                     `json:"errors"`
	ElapsedMS         int64                   `json:"elapsed_ms"`
	RequestsPerSecond float64                 `json:"requests_per_second"`
	Latency           *benchmarkLatencyReport `json:"latency,omitempty"`
	ErrorSamples      []string                `json:"error_samples,omitempty"`
}

// printConfigRecap exists to keep load-test runs self-describing.
func printConfigRecap(cfg config, perClientMode bool, totalRequests int, effectiveClients int) {
	style := makeStyler(shouldColor())
	mode := "total-requests"
	if perClientMode {
		mode = "per-client"
	}
	sessionPlan := "backend-managed"
	if cfg.Target == "weaver" && cfg.SessionID == "" {
		sessionPlan = "register one conversation per client"
	}
	if cfg.SessionID != "" {
		sessionPlan = "reuse provided session"
	} else if cfg.CreateSession && cfg.PrepareSessions && perClientMode {
		sessionPlan = "prepare sessions per client"
	} else if cfg.CreateSession && cfg.Target != "weaver" {
		sessionPlan = "create per request"
	}

	fmt.Printf("\n%s\n", style("BENCH CONFIG", colorBold, colorCyan))
	fmt.Printf("%s %s\n", style("Protocol:", colorDim), cfg.Protocol)
	fmt.Printf("%s %s\n", style("Target:", colorDim), reportTargetURL(cfg))
	if cfg.Target == "weaver" {
		fmt.Printf("Space ID: %s\nPreparation: per turn; history: after EOF\n", cfg.SpaceID)
	}
	if cfg.Protocol == "sse" {
		if cfg.AgentInstanceID != "" {
			fmt.Printf("%s %s\n", style("SSE mode:", colorDim), "managed")
			fmt.Printf("%s %s\n", style("Agent instance ID:", colorDim), cfg.AgentInstanceID)
		} else {
			fmt.Printf("%s %s\n", style("SSE mode:", colorDim), "direct")
			fmt.Printf("%s %s\n", style("Agent ID:", colorDim), cfg.AgentID)
		}
		if cfg.SSETeamID != "" {
			fmt.Printf("%s %s\n", style("Team ID:", colorDim), cfg.SSETeamID)
		}
	} else {
		fmt.Printf("%s %s\n", style("Agent ID:", colorDim), cfg.AgentID)
	}
	if cfg.AgentUUID != "" {
		fmt.Printf("%s %s\n", style("Agent source:", colorDim), "provided UUID")
	}
	if cfg.AgentUUID == "" && cfg.EnsureV2DefinitionRef != "" {
		fmt.Printf("%s %s\n", style("Ensure v2 definition:", colorDim), cfg.EnsureV2DefinitionRef)
	}
	if cfg.AgentUUID == "" && cfg.EnsureV2ProfileID != "" {
		fmt.Printf("%s %s\n", style("Ensure v2 profile:", colorDim), cfg.EnsureV2ProfileID)
	}
	if len(cfg.DocumentLibraryIDs) > 0 {
		fmt.Printf("%s %s\n", style("Document libraries:", colorDim), strings.Join(cfg.DocumentLibraryIDs, ","))
	}
	if len(cfg.DocumentUIDs) > 0 {
		fmt.Printf("%s %s\n", style("Document UIDs:", colorDim), strings.Join(cfg.DocumentUIDs, ","))
	}
	if cfg.SearchPolicy != "" {
		fmt.Printf("%s %s\n", style("Search policy:", colorDim), cfg.SearchPolicy)
	}
	if cfg.SearchRagScope != "" {
		fmt.Printf("%s %s\n", style("RAG scope:", colorDim), cfg.SearchRagScope)
	}
	fmt.Printf("%s %s\n", style("Mode:", colorDim), mode)
	fmt.Printf("%s %d\n", style("Clients:", colorDim), effectiveClients)
	fmt.Printf("%s %d\n", style("Total requests:", colorDim), totalRequests)
	if perClientMode {
		fmt.Printf("%s %d\n", style("Requests per client:", colorDim), cfg.RequestsPerClient)
	}
	fmt.Printf("%s %s\n", style("Session plan:", colorDim), sessionPlan)
	fmt.Printf("%s %t\n", style("Create session:", colorDim), cfg.CreateSession)
	fmt.Printf("%s %t\n", style("Prepare sessions:", colorDim), cfg.PrepareSessions)
	fmt.Printf("%s %d\n", style("Prepare concurrency:", colorDim), cfg.PrepareConcurrency)
	fmt.Printf("%s %t\n", style("Delete sessions:", colorDim), cfg.DeleteSession)
	fmt.Printf("%s %s\n", style("Session title:", colorDim), cfg.SessionTitle)
	if cfg.SessionURL != "" {
		fmt.Printf("%s %s\n", style("Session URL override:", colorDim), reportURL(cfg, cfg.SessionURL))
	}
	fmt.Printf("%s %s\n", style("Timeout:", colorDim), cfg.Timeout)
	fmt.Printf("%s %d\n", style("Read limit bytes:", colorDim), cfg.ReadLimitBytes)
	if cfg.TokenInQuery {
		fmt.Printf("%s %s\n", style("Auth:", colorDim), "query")
	} else {
		fmt.Printf("%s %s\n", style("Auth:", colorDim), "header")
	}
	fmt.Printf("%s %t\n", style("Insecure TLS:", colorDim), cfg.InsecureTLS)
}

func shouldColor() bool {
	if os.Getenv("NO_COLOR") != "" || os.Getenv("TERM") == "dumb" {
		return false
	}
	info, err := os.Stdout.Stat()
	if err != nil {
		return false
	}
	return (info.Mode() & os.ModeCharDevice) != 0
}

func makeStyler(enabled bool) func(string, ...string) string {
	return func(s string, codes ...string) string {
		if !enabled || len(codes) == 0 {
			return s
		}
		return strings.Join(codes, "") + s + colorReset
	}
}

func buildJSONReport(cfg config, total int, durations []time.Duration, errorCount int, errorSamples []string, elapsed time.Duration) benchmarkJSONReport {
	redactedErrorSamples := make([]string, 0, len(errorSamples))
	for _, sample := range errorSamples {
		redactedErrorSamples = append(redactedErrorSamples, redactReportText(cfg, sample))
	}
	report := benchmarkJSONReport{
		SchemaVersion:     "v1",
		GeneratedAt:       time.Now().UTC().Format(time.RFC3339Nano),
		Outcome:           "OK",
		Protocol:          cfg.Protocol,
		Target:            reportTargetURL(cfg),
		Clients:           cfg.Clients,
		RequestsPerClient: cfg.RequestsPerClient,
		TotalRequests:     total,
		Success:           len(durations),
		Errors:            errorCount,
		ElapsedMS:         elapsed.Milliseconds(),
		ErrorSamples:      redactedErrorSamples,
	}
	if elapsed > 0 {
		report.RequestsPerSecond = float64(report.Success) / elapsed.Seconds()
	}
	if errorCount > 0 || len(durations)+errorCount < total {
		report.Outcome = "DEGRADED"
	}
	if report.Success == 0 {
		report.Outcome = "FAILED"
	}
	if cfg.Target == "weaver" {
		report.SpaceID = cfg.SpaceID
	}
	if cfg.Protocol == "sse" {
		report.TeamID = cfg.SSETeamID
		if cfg.AgentInstanceID != "" {
			report.SSEMode = "managed"
			report.AgentInstanceID = cfg.AgentInstanceID
		} else {
			report.SSEMode = "direct"
			report.AgentID = cfg.AgentID
		}
	} else {
		report.AgentID = cfg.AgentID
	}
	if len(durations) > 0 {
		stats := summarize(durations)
		report.Latency = &benchmarkLatencyReport{
			Min: stats.Min.Milliseconds(),
			Avg: stats.Avg.Milliseconds(),
			P50: stats.P50.Milliseconds(),
			P95: stats.P95.Milliseconds(),
			P99: stats.P99.Milliseconds(),
			Max: stats.Max.Milliseconds(),
		}
	}
	return report
}

func redactReportText(cfg config, value string) string {
	for _, sensitiveValue := range []string{cfg.Token, cfg.Message} {
		if sensitiveValue != "" {
			for _, encoded := range []string{sensitiveValue, url.QueryEscape(sensitiveValue), url.PathEscape(sensitiveValue)} {
				value = strings.ReplaceAll(value, encoded, "[REDACTED]")
			}
		}
	}
	return value
}

func writeJSONReport(path string, report benchmarkJSONReport, rawPath string) error {
	payload, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	payload = append(payload, '\n')
	// Open without truncation: compare the opened file, not lexical paths.
	// This also protects aliases through symlinked directories and hard links.
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE, 0o644)
	if err != nil {
		return err
	}
	defer file.Close()
	if rawPath != "" {
		rawInfo, err := os.Stat(rawPath)
		if err != nil && !os.IsNotExist(err) {
			return err
		}
		if err == nil {
			summaryInfo, err := file.Stat()
			if err != nil {
				return err
			}
			if os.SameFile(rawInfo, summaryInfo) {
				return fmt.Errorf("raw-report and json-report refer to the same file")
			}
		}
	}
	if err := file.Truncate(0); err != nil {
		return err
	}
	if _, err := file.Write(payload); err != nil {
		return err
	}
	return file.Close()
}

func printSummary(cfg config, total int, durations []time.Duration, errorCount int, errorSamples []string, elapsed time.Duration, cleanupErrors int) benchmarkJSONReport {
	report := buildJSONReport(cfg, total, durations, errorCount, errorSamples, elapsed)
	report.CleanupErrors = cleanupErrors
	if cleanupErrors > 0 && report.Outcome == "OK" {
		report.Outcome = "DEGRADED"
	}
	success := report.Success
	style := makeStyler(shouldColor())
	outcomeColor := colorGreen
	if report.Outcome == "DEGRADED" {
		outcomeColor = colorYellow
	}
	if report.Outcome == "FAILED" {
		outcomeColor = colorRed
	}
	successPct := 0.0
	if total > 0 {
		successPct = (float64(success) / float64(total)) * 100
	}

	fmt.Printf("\n%s\n", style("BENCH SUMMARY", colorBold, colorCyan))
	fmt.Printf("%s %s\n", style("Outcome:", colorDim), style(report.Outcome, colorBold, outcomeColor))
	fmt.Printf("%s %s\n", style("Target:", colorDim), reportTargetURL(cfg))
	if cfg.Target == "weaver" {
		fmt.Printf("Space ID: %s\nPreparation: per turn; history: after EOF\n", cfg.SpaceID)
	}
	if cfg.Protocol == "sse" {
		if cfg.AgentInstanceID != "" {
			fmt.Printf("%s %s\n", style("SSE mode:", colorDim), "managed")
			fmt.Printf("%s %s\n", style("Agent instance ID:", colorDim), cfg.AgentInstanceID)
		} else {
			fmt.Printf("%s %s\n", style("SSE mode:", colorDim), "direct")
			fmt.Printf("%s %s\n", style("Agent ID:", colorDim), cfg.AgentID)
		}
		if cfg.SSETeamID != "" {
			fmt.Printf("%s %s\n", style("Team ID:", colorDim), cfg.SSETeamID)
		}
	} else {
		fmt.Printf("%s %s\n", style("Agent ID:", colorDim), cfg.AgentID)
	}
	if report.CleanupErrors > 0 {
		fmt.Printf("Cleanup errors: %d\n", report.CleanupErrors)
	}
	fmt.Printf("%s %d\n", style("Total requests:", colorDim), total)
	fmt.Printf("%s %d\n", style("Concurrent clients:", colorDim), cfg.Clients)
	if cfg.RequestsPerClient > 0 {
		fmt.Printf("%s %d\n", style("Requests per client:", colorDim), cfg.RequestsPerClient)
	}
	fmt.Printf("%s %s\n", style("Success:", colorDim), style(fmt.Sprintf("%d (%.2f%%)", success, successPct), colorGreen))
	if errorCount > 0 {
		fmt.Printf("%s %s\n", style("Errors:", colorDim), style(fmt.Sprintf("%d", errorCount), colorRed))
	} else {
		fmt.Printf("%s %d\n", style("Errors:", colorDim), errorCount)
	}
	fmt.Printf("%s %s\n", style("Elapsed:", colorDim), elapsed.Round(time.Millisecond))
	if success > 0 {
		fmt.Printf("%s %.2f\n", style("Requests/sec:", colorDim), float64(success)/elapsed.Seconds())
		stats := summarize(durations)
		fmt.Printf("%s %s\n",
			style("Latency ms (min/avg/p50/p95/p99/max):", colorDim),
			style(fmt.Sprintf("%d/%d/%d/%d/%d/%d",
				stats.Min.Milliseconds(),
				stats.Avg.Milliseconds(),
				stats.P50.Milliseconds(),
				stats.P95.Milliseconds(),
				stats.P99.Milliseconds(),
				stats.Max.Milliseconds(),
			), colorBold, colorCyan),
		)
	}
	if len(errorSamples) > 0 {
		fmt.Printf("\n%s\n", style("Sample errors:", colorBold, colorRed))
		for _, sample := range report.ErrorSamples {
			fmt.Printf("%s %s\n", style("-", colorRed), sample)
		}
	}
	return report
}

type latencyStats struct {
	Min time.Duration
	Max time.Duration
	Avg time.Duration
	P50 time.Duration
	P95 time.Duration
	P99 time.Duration
}

func summarize(durations []time.Duration) latencyStats {
	sort.Slice(durations, func(i, j int) bool { return durations[i] < durations[j] })
	total := time.Duration(0)
	for _, d := range durations {
		total += d
	}
	return latencyStats{
		Min: durations[0],
		Max: durations[len(durations)-1],
		Avg: total / time.Duration(len(durations)),
		P50: percentile(durations, 0.50),
		P95: percentile(durations, 0.95),
		P99: percentile(durations, 0.99),
	}
}

func percentile(sorted []time.Duration, p float64) time.Duration {
	if len(sorted) == 0 {
		return 0
	}
	if p <= 0 {
		return sorted[0]
	}
	if p >= 1 {
		return sorted[len(sorted)-1]
	}
	pos := int(math.Ceil(p*float64(len(sorted)))) - 1
	if pos < 0 {
		pos = 0
	}
	if pos >= len(sorted) {
		pos = len(sorted) - 1
	}
	return sorted[pos]
}

// writeRawReport exports only an allowlisted measurement schema. No config,
// payload, upstream error string, URL or backend conversation ID is serialized.
func writeRawReport(path string, cfg config, results []result) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return err
	}
	encoder := json.NewEncoder(file)
	for _, res := range results {
		target, preparationMode := "swift", "not_performed"
		if cfg.Target == "weaver" {
			target, preparationMode = "weaver", "per_turn"
			res.Measurement.SchemaVersion = "fred.bench.turn.v2"
		}
		row := struct {
			turnMeasurement
			Target          string `json:"target"`
			Protocol        string `json:"protocol"`
			PreparationMode string `json:"preparation_mode"`
		}{res.Measurement, target, cfg.Protocol, preparationMode}
		if err := encoder.Encode(row); err != nil {
			_ = file.Close()
			return err
		}
	}
	return file.Close()
}

func reportURL(cfg config, raw string) string {
	parsed, err := url.Parse(raw)
	if err != nil {
		return "[invalid URL]"
	}
	parsed.User, parsed.RawQuery, parsed.Fragment = nil, "", ""
	parsed.ForceQuery = false
	return redactReportText(cfg, parsed.String())
}

func reportTargetURL(cfg config) string {
	if cfg.Target == "weaver" {
		return reportURL(cfg, cfg.FredOrigin)
	}
	return reportURL(cfg, cfg.URL)
}

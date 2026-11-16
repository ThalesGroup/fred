package main

import (
	"bufio"
	"bytes"
	_ "embed"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"html/template"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"
)

//go:embed report.html.tmpl
var reportHTML string

const reportMaxBytes = 128 << 20
const reportMaxTurns = 100000

type reportRunHeader struct {
	Kind     string `json:"kind"`
	Schema   string `json:"schema_version"`
	Campaign string `json:"campaign_id"`
	Target   string `json:"target"`
	Identity string `json:"identity_mode"`
	Steps    []int  `json:"concurrency_steps"`
	Turns    int    `json:"turns"`
}

// Only this allowlisted projection reaches HTML. In particular, never export
// identities, conversation IDs, paths, prompts, unknown fields or raw errors.
type htmlTurn struct {
	Step      int                 `json:"step"`
	Client    int                 `json:"client"`
	Turn      int                 `json:"turn"`
	First     bool                `json:"first"`
	Outcome   string              `json:"outcome"`
	Integrity string              `json:"integrity"`
	Error     string              `json:"error"`
	Metrics   map[string]*float64 `json:"metrics"`
}
type htmlStep struct {
	Step               int      `json:"step"`
	Concurrency        int      `json:"concurrency"`
	Planned            int      `json:"planned"`
	Duration           *float64 `json:"duration"`
	HistoryVerified    int      `json:"historyVerified"`
	HistoryErrors      int      `json:"historyErrors"`
	HistoryUnsupported int      `json:"historyUnsupported"`
	CleanupErrors      int      `json:"cleanupErrors"`
}
type htmlRun struct {
	Campaign   string     `json:"campaign"`
	Label      string     `json:"label"`
	Target     string     `json:"target"`
	Identity   string     `json:"identity"`
	Profile    string     `json:"profile"`
	Status     string     `json:"status"`
	Warning    string     `json:"warning"`
	Error      string     `json:"error"`
	AuthErrors int        `json:"authErrors"`
	Steps      []htmlStep `json:"steps"`
	Turns      []htmlTurn `json:"turns"`
}

func runHTMLReportCLI(args []string) int {
	fs := flag.NewFlagSet("report", flag.ContinueOnError)
	input := fs.String("input", "", "Directory containing scenario JSONL results")
	output := fs.String("output", "", "New HTML file (default: <input>/report.html; never overwritten)")
	if err := fs.Parse(args); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return 0
		}
		return 2
	}
	if *input == "" || fs.NArg() != 0 {
		fmt.Fprintln(os.Stderr, "report: -input directory is required")
		return 2
	}
	if *output == "" {
		*output = filepath.Join(*input, "report.html")
	}
	if err := generateHTMLReport(*input, *output); err != nil {
		fmt.Fprintln(os.Stderr, "report:", err)
		return 2
	}
	fmt.Println("Rapport HTML créé :", *output)
	return 0
}

func generateHTMLReport(input, output string) error {
	runs, err := readHTMLRuns(input)
	if err != nil {
		return err
	}
	var rendered bytes.Buffer
	// html/template serializes the typed value in JavaScript context using
	// encoding/json's HTML escaping. No template.JS or raw JSON insertion.
	if err := template.Must(template.New("report").Parse(reportHTML)).Execute(&rendered, runs); err != nil {
		return errors.New("cannot render report")
	}
	if strings.ToLower(filepath.Ext(output)) != ".html" {
		return errors.New("output must be a new .html file")
	}
	f, err := os.OpenFile(output, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return errors.New("output unavailable or already exists; choose a new .html path")
	}
	_, writeErr := f.Write(rendered.Bytes())
	closeErr := f.Close()
	if writeErr != nil || closeErr != nil {
		return errors.New("cannot write complete report")
	}
	return nil
}

func readHTMLRuns(dir string) ([]htmlRun, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, errors.New("input directory unavailable")
	}
	var runs []htmlRun
	seen := map[string]bool{}
	var bytesRead int64
	totalTurns := 0
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".jsonl" {
			continue
		}
		info, err := entry.Info()
		if err != nil || !info.Mode().IsRegular() {
			return nil, errors.New("JSONL inputs must be regular files, not links")
		}
		bytesRead += info.Size()
		if bytesRead > reportMaxBytes {
			return nil, errors.New("input exceeds 128 MiB")
		}
		f, err := os.Open(filepath.Join(dir, entry.Name()))
		if err != nil {
			return nil, errors.New("cannot open JSONL input")
		}
		run, campaign, err := readHTMLRun(f)
		_ = f.Close()
		if err != nil {
			return nil, fmt.Errorf("JSONL input %d: %w", len(runs)+1, err)
		}
		if run == nil {
			continue
		}
		if seen[campaign] {
			return nil, errors.New("duplicate campaign; keep one canonical JSONL per run")
		}
		seen[campaign] = true
		totalTurns += len(run.Turns)
		if len(runs) >= 64 || totalTurns > reportMaxTurns {
			return nil, errors.New("report limit: 64 runs and 100000 turns")
		}
		run.Label = fmt.Sprintf("%s · exécution %d", strings.ToUpper(run.Target[:1])+run.Target[1:], len(runs)+1)
		runs = append(runs, *run)
	}
	if len(runs) == 0 {
		return nil, errors.New("no supported fred.bench.scenario.v1 JSONL run found (legacy reports unsupported)")
	}
	return runs, nil
}

func readHTMLRun(input io.Reader) (*htmlRun, string, error) {
	scanner := bufio.NewScanner(io.LimitReader(input, reportMaxBytes+1))
	scanner.Buffer(make([]byte, 4096), 2<<20)
	if !scanner.Scan() {
		return nil, "", errors.New("empty or unreadable JSONL input")
	}
	var header reportRunHeader
	if json.Unmarshal(scanner.Bytes(), &header) != nil {
		return nil, "", errors.New("invalid JSONL header")
	}
	if header.Kind != "run" {
		// Preparation filenames are operator chosen. Recognize the terminal schema,
		// not a naming convention; inspect only record kinds, never private payloads.
		kind, schema := header.Kind, header.Schema
		for {
			if kind == "preparation_summary" && schema == "fred.bench.preparation.v1" {
				if scanner.Scan() || scanner.Err() != nil {
					return nil, "", errors.New("invalid preparation ending")
				}
				return nil, "", nil
			}
			if kind != "auth" && kind != "onboarding" {
				return nil, "", errors.New("unsupported JSONL: expected scenario run or identity preparation")
			}
			if !scanner.Scan() {
				return nil, "", errors.New("incomplete identity preparation JSONL")
			}
			var record reportRunHeader
			if json.Unmarshal(scanner.Bytes(), &record) != nil {
				return nil, "", errors.New("invalid identity preparation JSONL")
			}
			kind, schema = record.Kind, record.Schema
		}
	}
	if header.Schema != "fred.bench.scenario.v1" {
		return nil, "", errors.New("unsupported scenario schema")
	}
	if header.Campaign == "" || (header.Target != "swift" && header.Target != "weaver") || (header.Identity != "shared" && header.Identity != "per-conversation") || header.Turns < 1 || header.Turns > 100 || len(header.Steps) == 0 || len(header.Steps) > 32 {
		return nil, "", errors.New("invalid scenario header")
	}
	campaign := "non renseignée"
	if len(header.Campaign) == 32 && strings.Trim(header.Campaign, "0123456789abcdef") == "" {
		campaign = header.Campaign
	}
	run := &htmlRun{Campaign: campaign, Target: header.Target, Identity: header.Identity, Profile: "absent", Status: "incomplete", Turns: []htmlTurn{}}
	for i, n := range header.Steps {
		if n < 1 || n > 10000 {
			return nil, "", errors.New("invalid concurrency level")
		}
		run.Steps = append(run.Steps, htmlStep{Step: i + 1, Concurrency: n, Planned: n * header.Turns})
	}
	var summary *scenarioReport
	seenTurns := map[[3]int]bool{}
	seenSteps := map[int]stepReport{}
	historyCounts := make(map[int][3]int)
	historySeen := map[string]bool{}
	broken := false
	for scanner.Scan() {
		var envelope struct {
			Kind string `json:"kind"`
		}
		data := scanner.Bytes()
		if json.Unmarshal(data, &envelope) != nil {
			broken = true
			break
		}
		if summary != nil {
			return nil, "", errors.New("records after terminal summary")
		}
		switch envelope.Kind {
		case "auth", "preflight", "terms", "onboarding":
			// No private identifiers or free text from these records is exported.
		case "history":
			var h historyRecord
			if json.Unmarshal(data, &h) != nil || h.Step < 1 || h.Step > len(run.Steps) || h.ConversationID == "" {
				return nil, "", errors.New("invalid history record")
			}
			key := fmt.Sprintf("%d:%s", h.Step, h.ConversationID)
			if historySeen[key] {
				return nil, "", errors.New("duplicate history record")
			}
			historySeen[key] = true
			counts := historyCounts[h.Step]
			switch h.Status {
			case "verified":
				counts[0]++
			case "failed":
				counts[1]++
			case "unsupported":
				counts[2]++
			case "not_verified":
			default:
				return nil, "", errors.New("invalid history status")
			}
			historyCounts[h.Step] = counts
		case "turn":
			var row scenarioTurn
			if json.Unmarshal(data, &row) != nil {
				return nil, "", errors.New("invalid turn record")
			}
			if row.SchemaVersion != "fred.bench.scenario.turn.v1" || row.CampaignID != header.Campaign || row.Target != header.Target {
				return nil, "", errors.New("turn schema or campaign mismatch")
			}
			if row.Step < 1 || row.Step > len(run.Steps) || row.Concurrency != run.Steps[row.Step-1].Concurrency || row.ClientID < 1 || row.ClientID > row.Concurrency || row.Turn < 1 || row.Turn > header.Turns || row.FirstTurn != (row.Turn == 1) {
				return nil, "", errors.New("turn outside declared plan")
			}
			key := [3]int{row.Step, row.ClientID, row.Turn}
			if seenTurns[key] {
				return nil, "", errors.New("duplicate turn")
			}
			seenTurns[key] = true
			if len(run.Turns) >= reportMaxTurns {
				return nil, "", errors.New("too many turns")
			}
			if row.Outcome == "timeout" || row.Outcome == "canceled" {
				row.Outcome = "error"
			}
			if row.Outcome != "success" && row.Outcome != "error" {
				return nil, "", errors.New("missing or invalid turn outcome")
			}
			integrity := "not_observed"
			if row.Integrity == "passed" || row.Integrity == "failed" {
				integrity = row.Integrity
			}
			run.Turns = append(run.Turns, htmlTurn{row.Step, row.ClientID, row.Turn, row.FirstTurn, row.Outcome, integrity, reportError(row.Error, row.PerformanceError, row.IntegrityError), reportMetrics(row)})
		case "step":
			var step stepReport
			if json.Unmarshal(data, &step) != nil || step.Step < 1 || step.Step > len(run.Steps) || seenSteps[step.Step].Step != 0 {
				return nil, "", errors.New("invalid or duplicate step")
			}
			seenSteps[step.Step] = step
			if err := applyHTMLStep(run, step); err != nil {
				return nil, "", err
			}
		case "summary":
			summary = &scenarioReport{}
			if json.Unmarshal(data, summary) != nil || summary.SchemaVersion != header.Schema || summary.CampaignID != header.Campaign || summary.Target != header.Target || summary.IdentityMode != header.Identity || len(summary.Steps) != len(run.Steps) {
				return nil, "", errors.New("summary schema, campaign or plan mismatch")
			}
		default:
			return nil, "", errors.New("unsupported scenario record")
		}
	}
	if scanner.Err() != nil {
		return nil, "", errors.New("cannot read JSONL (maximum record size 2 MiB)")
	}
	if broken {
		run.Warning = "Lecture interrompue sur une ligne JSON invalide ; seuls les tours précédents sont affichés."
	}
	if summary == nil {
		observedHTMLHistory(run, historyCounts)
		run.Warning += " Résumé final absent : campagne interrompue ou incomplète."
		return run, header.Campaign, nil
	}
	if summary.MockProfile == "reference" || summary.MockProfile == "streaming" {
		run.Profile = summary.MockProfile
	}
	run.Error = reportError(summary.Error)
	run.AuthErrors = summary.AuthErrors
	if summary.AuthErrors < 0 {
		return nil, "", errors.New("invalid authentication count")
	}
	valid := !broken
	for i, step := range summary.Steps {
		if step.Step != i+1 {
			return nil, "", errors.New("summary step order mismatch")
		}
		if recorded, exists := seenSteps[step.Step]; exists && recorded != step {
			valid = false
		}
		if err := applyHTMLStep(run, step); err != nil {
			return nil, "", err
		}
		counts := historyCounts[step.Step]
		if counts != [3]int{step.HistoryVerified, step.HistoryErrors, step.HistoryUnsupported} {
			valid = false
		}
		attempted, success := 0, 0
		for _, turn := range run.Turns {
			if turn.Step == step.Step {
				attempted++
				if turn.Outcome == "success" {
					success++
				}
			}
		}
		if step.Attempted != attempted || step.Success != success || step.Errors != attempted-success || step.NotStarted != step.Planned-attempted {
			valid = false
		}
	}
	switch summary.Outcome {
	case "OK", "DEGRADED", "FAILED":
		run.Status = summary.Outcome
	default:
		valid = false
	}
	if run.Status == "OK" {
		if run.Error != "" || run.AuthErrors > 0 || run.Profile == "absent" {
			valid = false
		}
		for _, step := range run.Steps {
			count := 0
			for _, turn := range run.Turns {
				if turn.Step == step.Step && turn.Outcome == "success" && turn.Integrity == "passed" {
					count++
				}
			}
			if count != step.Planned || step.HistoryVerified != step.Concurrency || step.HistoryErrors+step.HistoryUnsupported+step.CleanupErrors > 0 {
				valid = false
			}
		}
	}
	observedHTMLHistory(run, historyCounts)
	if !valid {
		run.Status = "incomplete"
		run.Warning += " Résumé incohérent avec les tours ou vérifications disponibles."
	}
	return run, header.Campaign, nil
}

func observedHTMLHistory(run *htmlRun, counts map[int][3]int) {
	for i := range run.Steps {
		s := &run.Steps[i]
		c := counts[s.Step]
		s.HistoryVerified, s.HistoryErrors, s.HistoryUnsupported = c[0], c[1], c[2]
	}
}

func applyHTMLStep(run *htmlRun, step stepReport) error {
	if step.Step < 1 || step.Step > len(run.Steps) {
		return errors.New("invalid step number")
	}
	dest := &run.Steps[step.Step-1]
	if step.Concurrency != dest.Concurrency || step.Planned != dest.Planned || step.LoadElapsedMS < 0 || step.HistoryVerified < 0 || step.HistoryErrors < 0 || step.HistoryUnsupported < 0 || step.CleanupErrors < 0 {
		return errors.New("step plan or measurements invalid")
	}
	if step.LoadElapsedMS > 0 {
		ms := step.LoadElapsedMS
		dest.Duration = &ms
	}
	dest.HistoryVerified, dest.HistoryErrors, dest.HistoryUnsupported, dest.CleanupErrors = step.HistoryVerified, step.HistoryErrors, step.HistoryUnsupported, step.CleanupErrors
	return nil
}

func reportMetrics(row scenarioTurn) map[string]*float64 {
	// Reject impossible/missing dates instead of deriving huge or negative samples.
	validPair := func(start time.Time, end *time.Time) *time.Time {
		if start.IsZero() || end == nil || end.IsZero() || end.Before(start) {
			return nil
		}
		return end
	}
	row.FinalAt = validPair(row.StartedAt, row.FinalAt)
	row.StreamClosedAt = validPair(row.StartedAt, row.StreamClosedAt)
	if row.ExecutionStartedAt != nil {
		row.ExecutionStartedAt = validPair(row.StartedAt, row.ExecutionStartedAt)
		if row.ExecutionStartedAt != nil {
			row.FirstTextAt = validPair(*row.ExecutionStartedAt, row.FirstTextAt)
			row.FinalAt = validPair(*row.ExecutionStartedAt, row.FinalAt)
			row.StreamClosedAt = validPair(*row.ExecutionStartedAt, row.StreamClosedAt)
		}
	}
	if row.Preparation != nil && validPair(row.Preparation.StartedAt, &row.Preparation.FinishedAt) == nil {
		row.Preparation = nil
	}
	g := summarizeTurns([]scenarioTurn{row}, row.FirstTurn)
	out := map[string]*float64{}
	for key, m := range map[string]metricSummary{"execution_first_text": g.ExecutionFirstText, "execution_final": g.ExecutionFinal, "execution_eof": g.ExecutionEOF, "total_final": g.TotalFinal, "total_eof": g.TotalEOF, "preparation": g.Preparation} {
		if m.Count > 0 {
			v := m.P50
			out[key] = &v
		} else {
			out[key] = nil
		}
	}
	return out
}

func reportError(values ...string) string {
	for _, value := range values {
		if value == "" {
			continue
		}
		switch value {
		case "timeout", "canceled", "transport_error", "execution_error", "execution_interrupted", "incomplete_stream", "http_status", "invalid_event", "event_too_large", "invalid_session", "session_not_created", "invalid_binding", "model_unavailable", "invalid_response", "invalid_execution_url", "unsupported_transport", "terms_acceptance_required", "preflight_model_or_binding_unavailable", "preflight_route_or_team_mismatch", "ack_context_mismatch", "ack_fragment_mismatch", "ack_missing", "ack_stream_final_mismatch", "ack_terminal_count", "history_missing_turns", "history_context_mismatch", "history_turn_mismatch", "history_ack_mismatch", "history_unsupported":
			return value
		}
		for _, prefix := range []string{"http_", "auth_http_", "history_http_"} {
			for code := 400; code <= 599; code++ {
				if value == fmt.Sprintf("%s%d", prefix, code) {
					return value
				}
			}
		}
		return "other_error"
	}
	return ""
}

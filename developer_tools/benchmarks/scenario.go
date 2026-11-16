package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

func scenarioSteps(cfg config) ([]int, error) {
	if cfg.Scenario != "conversation" || cfg.CredentialFile == "" || cfg.RawReportPath == "" || cfg.Protocol != "sse" || cfg.AgentInstanceID == "" || cfg.RequestsPerClient < 1 || cfg.RequestsPerClient > 100 || cfg.Timeout <= 0 || cfg.AuthConcurrency < 1 || cfg.AuthConcurrency > 64 || (cfg.IdentityMode != "per-conversation" && cfg.IdentityMode != "shared") || (cfg.MockProfile != "reference" && cfg.MockProfile != "streaming") {
		return nil, benchmarkError("scenario_requires_managed_sse_credentials_raw_report_and_explicit_steps")
	}
	if cfg.SessionID != "" || !cfg.CreateSession || cfg.TokenInQuery || cfg.AllowEmptyTok || cfg.InsecureTLS || cfg.PrepareSessions || cfg.EnsureV2DefinitionRef != "" || cfg.EnsureV2ProfileID != "" || cfg.AgentUUID != "" {
		return nil, benchmarkError("unsupported_scenario_option")
	}
	for _, name := range cfg.ExplicitFlags {
		switch name {
		case "clients", "requests", "token", "sse-user-id", "prepare-sessions", "ramp-duration":
			return nil, benchmarkError("scenario_owns_clients_identity_and_zero_ramp")
		}
	}
	var steps []int
	for _, value := range strings.Split(cfg.ConcurrencySteps, ",") {
		n, err := strconv.Atoi(strings.TrimSpace(value))
		if err != nil || n < 1 || n > 10000 || len(steps) >= 32 {
			return nil, benchmarkError("invalid_concurrency_steps")
		}
		steps = append(steps, n)
	}
	checked := cfg
	checked.Token = "validated-after-credential-acquisition"
	if cfg.Target == "swift" {
		checked.ExplicitFlags = scenarioExplicitFlags(cfg.ExplicitFlags)
	}
	if err := validateConfig(checked); err != nil {
		return nil, benchmarkError("invalid_scenario_target_config")
	}
	if cfg.Target != "weaver" {
		u, err := url.Parse(cfg.URL)
		if err != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Hostname() == "" || u.User != nil || u.RawQuery != "" || u.ForceQuery || u.Fragment != "" || u.RawPath != "" || !weaverPublicPath(u.Path, "/agents/execute/stream") {
			return nil, benchmarkError("invalid_swift_execution_url")
		}
	}
	return steps, nil
}

func runScenarioCLI(cfg config) int {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	report, err := runScenario(ctx, cfg)
	if err != nil {
		fmt.Fprintln(os.Stderr, "scenario:", classifyError(err))
		return 2
	}
	fmt.Printf("Scenario %s: %d steps, %s\n", cfg.Target, len(report.Steps), report.Outcome)
	if report.Outcome != "OK" {
		return 1
	}
	return 0
}

func runScenario(ctx context.Context, cfg config) (scenarioReport, error) {
	report := scenarioReport{Kind: "summary", SchemaVersion: "fred.bench.scenario.v1", CampaignID: newExchangeID(), Target: cfg.Target, IdentityMode: cfg.IdentityMode, MockProfile: cfg.MockProfile, Outcome: "FAILED"}
	steps, err := scenarioSteps(cfg)
	if err != nil {
		return report, err
	}
	count := 1
	for _, n := range steps {
		if cfg.IdentityMode == "per-conversation" && n > count {
			count = n
		}
	}
	credentials, err := readCredentials(cfg.CredentialFile, count)
	if err != nil {
		return report, err
	}
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	writer, err := newScenarioWriter(cfg.RawReportPath, cancel)
	if err != nil {
		return report, err
	}
	var summaryFile *os.File
	if cfg.JSONReportPath != "" {
		summaryFile, err = os.OpenFile(cfg.JSONReportPath, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
		if err != nil {
			_ = writer.close()
			return report, benchmarkError("summary_report_unavailable")
		}
		defer summaryFile.Close()
	}
	writer.write(map[string]any{"kind": "run", "schema_version": report.SchemaVersion, "campaign_id": report.CampaignID, "target": cfg.Target, "identity_mode": cfg.IdentityMode, "concurrency_steps": steps, "turns": cfg.RequestsPerClient})
	client := sseHTTPClient(config{})
	defer client.CloseIdleConnections()
	var authMu sync.Mutex
	var acquires, refreshes []float64
	identities, authErr := acquireIdentities(ctx, cfg, credentials, count, report.CampaignID, client, func(record authRecord) {
		writer.write(record)
		authMu.Lock()
		defer authMu.Unlock()
		if record.Error != "" {
			report.AuthErrors++
		} else if record.Operation == "acquire" {
			acquires = append(acquires, millis(record.FinishedAt.Sub(record.StartedAt)))
		} else {
			refreshes = append(refreshes, millis(record.FinishedAt.Sub(record.StartedAt)))
		}
	})
	// Credentials are never retained by conversations; refresh only uses rotated tokens.
	credentials = credentialFile{}
	if authErr != nil {
		report.Error = classifyError(authErr)
	}
	if authErr == nil {
		authErr = preflightScenario(ctx, cfg, identities, client, writer)
		if authErr != nil {
			report.Error = classifyError(authErr)
		}
	}
	for index, n := range steps {
		summary := stepReport{Step: index + 1, Concurrency: n, Planned: n * cfg.RequestsPerClient}
		if authErr != nil || ctx.Err() != nil {
			summary.NotStarted = summary.Planned
			report.Steps = append(report.Steps, summary)
			continue
		}
		var mu sync.Mutex
		var conversations []*scenarioConversation
		var rows []scenarioTurn
		open := func(openCtx context.Context, worker int) (conversation, error) {
			identity := identities[0]
			if cfg.IdentityMode == "per-conversation" {
				identity = identities[worker]
			}
			c := &scenarioConversation{cfg: cfg, identity: identity, client: client, campaign: report.CampaignID, markerID: newExchangeID(), completed: make([]turnMarker, 0)}
			token, _, err := identity.token(openCtx)
			if err != nil {
				return nil, err
			}
			c.cfg.Token, c.cfg.SSEUserID = token, identity.subject
			if cfg.Target == "weaver" {
				c.weaver = &weaverAdapter{cfg: c.cfg, http: client}
				c.inner, err = c.weaver.Open(openCtx, worker)
			} else {
				c.swift = &swiftAdapter{cfg: c.cfg, http: client}
				c.inner, err = c.swift.Open(openCtx, worker)
			}
			c.opened = err == nil
			mu.Lock()
			conversations = append(conversations, c)
			mu.Unlock()
			return c, err
		}
		started := time.Now()
		runLoad(ctx, loadPlan{Clients: n, Turns: cfg.RequestsPerClient, Timeout: cfg.Timeout, Observe: func(r result) {
			row := scenarioTurn{PerformanceOutcome: "error", PerformanceError: r.Measurement.Error, Integrity: "not_observed"}
			if r.Scenario != nil {
				row = *r.Scenario
			}
			row.turnMeasurement = r.Measurement
			if r.Scenario != nil {
				row.ConversationID = r.Scenario.ConversationID
			}
			row.Kind, row.SchemaVersion, row.CampaignID = "turn", "fred.bench.scenario.turn.v1", report.CampaignID
			row.Step, row.Concurrency, row.FirstTurn, row.Target = index+1, n, r.Measurement.Turn == 1, cfg.Target
			row.PreparationMode = "not_performed"
			if cfg.Target == "weaver" {
				row.PreparationMode = "per_turn"
			}
			identity := identities[0]
			if cfg.IdentityMode == "per-conversation" {
				identity = identities[r.Measurement.ClientID-1]
			}
			row.IdentityID = identity.pseudonym
			rows = append(rows, row)
			writer.write(row)
		}}, open)
		summary.LoadElapsedMS = millis(time.Since(started))
		summary.Attempted, summary.NotStarted = len(rows), summary.Planned-len(rows)
		for _, row := range rows {
			if row.Outcome == "success" {
				summary.Success++
			} else {
				summary.Errors++
			}
			if row.PerformanceOutcome != "success" {
				summary.PerformanceErrors++
			}
			if row.Integrity == "failed" {
				summary.IntegrityErrors++
			}
		}
		summary.First, summary.Following = summarizeTurns(rows, true), summarizeTurns(rows, false)
		// runLoad has joined all workers. No history GET or cleanup competes with
		// the measured load window. Cancellation skips verification but still cleans up.
		for _, c := range conversations {
			if c.opened && c.attempts > 0 {
				h := historyRecord{Kind: "history", Step: index + 1, IdentityID: c.identity.pseudonym, ConversationID: pseudonym(report.CampaignID, c.ID()), Status: "not_verified", phaseMeasurement: phaseMeasurement{StartedAt: time.Now()}}
				historyCtx, done := context.WithTimeout(ctx, cfg.Timeout)
				err := c.history(historyCtx)
				done()
				h.finish(err)
				switch {
				case err == nil:
					h.Status = "verified"
					summary.HistoryVerified++
				case err == benchmarkError("history_unsupported"):
					h.Status = "unsupported"
					summary.HistoryUnsupported++
				default:
					h.Status = "failed"
					summary.HistoryErrors++
				}
				writer.write(h)
			}
			if c.inner != nil && c.weaver != nil {
				cleanupCtx, done := context.WithTimeout(context.Background(), cfg.Timeout)
				token, _, tokenErr := c.identity.token(cleanupCtx)
				done()
				if tokenErr == nil {
					c.weaver.cfg.Token = token
					c.inner.Close()
				} else if c.cfg.DeleteSession && c.inner.(*weaverConversation).created {
					summary.CleanupErrors++
				}
			}
			if c.weaver != nil {
				summary.CleanupErrors += int(c.weaver.cleanupErrors.Load())
			}
			if c.swift != nil && c.inner != nil && cfg.DeleteSession && c.inner.(*swiftConversation).created {
				cleanupCtx, done := context.WithTimeout(context.Background(), cfg.Timeout)
				token, _, err := c.identity.token(cleanupCtx)
				done()
				if err == nil {
					c.swift.cfg.Token = token
					c.inner.Close()
				} else {
					summary.CleanupErrors++
				}
				summary.CleanupErrors += int(c.swift.cleanupErrors.Load())
			}
		}
		report.Steps = append(report.Steps, summary)
		writer.write(struct {
			Kind string `json:"kind"`
			stepReport
		}{"step", summary})
	}
	report.Outcome = "OK"
	if report.Error != "" || ctx.Err() != nil {
		report.Outcome = "FAILED"
	}
	successes := 0
	for _, s := range report.Steps {
		successes += s.Success
		if s.Success != s.Planned || s.Attempted == 0 || s.HistoryErrors > 0 || s.HistoryUnsupported > 0 || s.CleanupErrors > 0 {
			report.Outcome = "DEGRADED"
		}
	}
	if successes == 0 {
		report.Outcome = "FAILED"
	}
	report.AuthAcquire, report.AuthRefresh = metric(acquires), metric(refreshes)
	writer.write(report)
	if err := writer.close(); err != nil {
		return report, err
	}
	if summaryFile != nil {
		if json.NewEncoder(summaryFile).Encode(report) != nil || summaryFile.Sync() != nil {
			return report, benchmarkError("summary_report_failed")
		}
	}
	return report, nil
}

type scenarioConversation struct {
	cfg       config
	identity  *benchmarkIdentity
	client    *http.Client
	inner     conversation
	weaver    *weaverAdapter
	swift     *swiftAdapter
	markerID  string
	campaign  string
	completed []turnMarker
	attempts  int
	opened    bool
}

func (c *scenarioConversation) ID() string {
	if c.inner == nil {
		return ""
	}
	return c.inner.ID()
}
func (c *scenarioConversation) Close() {} // scenario owns post-window verification and cleanup
func (c *scenarioConversation) Execute(ctx context.Context) result {
	c.attempts++
	started := time.Now()
	token, auth, err := c.identity.token(ctx)
	row := &scenarioTurn{Auth: auth, PerformanceOutcome: "error", Integrity: "not_observed"}
	row.ConversationID = pseudonym(c.campaign, c.ID())
	if err != nil {
		row.PerformanceError = classifyError(err)
		return result{Err: err, Measurement: turnMeasurement{StartedAt: started}, Scenario: row}
	}
	marker := turnMarker{c.markerID, c.attempts, newExchangeID()}
	data, _ := json.Marshal(marker)
	observer := &answerObserver{}
	prompt := c.cfg.Message + "\n" + markerPrefix + string(data)
	if c.weaver != nil {
		c.weaver.cfg.Token, c.weaver.cfg.Message, c.weaver.cfg.RuntimeDecoder = token, prompt, observer.decode
	}
	if c.swift != nil {
		c.swift.cfg.Token, c.swift.cfg.Message, c.swift.cfg.RuntimeDecoder = token, prompt, observer.decode
	}
	r := c.inner.Execute(ctx)
	r.Measurement.StartedAt = started
	if r.Measurement.FinalAt != nil {
		r.Duration = r.Measurement.FinalAt.Sub(started)
	}
	row.TextFragments = observer.fragments
	if r.Measurement.ExecutionStartedAt != nil {
		gap := observer.maxGap
		if !observer.first.IsZero() && observer.first.Sub(*r.Measurement.ExecutionStartedAt) > gap {
			gap = observer.first.Sub(*r.Measurement.ExecutionStartedAt)
		}
		if r.Measurement.StreamClosedAt != nil {
			last := *r.Measurement.ExecutionStartedAt
			if !observer.last.IsZero() {
				last = observer.last
			}
			if r.Measurement.StreamClosedAt.Sub(last) > gap {
				gap = r.Measurement.StreamClosedAt.Sub(last)
			}
			ms := millis(gap)
			row.MaxSilenceMS = &ms
		}
	}
	if r.Err == nil {
		row.PerformanceOutcome = "success"
		row.Integrity = "passed"
		if err := observer.verify(marker, c.completed, c.cfg.MockProfile); err != nil {
			row.Integrity = "failed"
			row.IntegrityError = classifyError(err)
			r.Err = err
		}
		c.completed = append(c.completed, marker)
	} else {
		row.PerformanceError = classifyError(r.Err)
	}
	r.Scenario = row
	return r
}

func (c *scenarioConversation) history(ctx context.Context) error {
	token, _, err := c.identity.token(ctx)
	if err != nil {
		return err
	}
	var messages []json.RawMessage
	if c.weaver != nil {
		c.weaver.cfg.Token = token
		conv := c.inner.(*weaverConversation)
		var session weaverSession
		_, err = c.weaver.json(ctx, http.MethodGet, conv.path(), nil, &session)
		if err != nil {
			return err
		}
		if !session.matches(c.cfg, conv.revision) || session.SessionID != c.ID() {
			return benchmarkError("invalid_session")
		}
		if session.MessagesURL == "" {
			return benchmarkError("history_unsupported")
		}
		if !weaverPublicPath(session.MessagesURL, "/agents/sessions/"+c.ID()+"/messages") {
			return benchmarkError("invalid_history_url")
		}
		_, err = c.weaver.json(ctx, http.MethodGet, session.MessagesURL, nil, &messages)
	} else {
		messages, err = c.swiftHistoryRequest(ctx)
	}
	if err != nil {
		return err
	}
	return verifyHistory(messages, c.ID(), c.completed, c.cfg.MockProfile)
}

func (c *scenarioConversation) swiftHistoryRequest(ctx context.Context) ([]json.RawMessage, error) {
	token, _, err := c.identity.token(ctx)
	if err != nil {
		return nil, err
	}
	endpoint := strings.TrimSuffix(c.cfg.URL, "/execute/stream") + "/sessions/" + url.PathEscape(c.ID()) + "/messages"
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, benchmarkError("invalid_history_url")
	}
	req.Header.Set("Authorization", "Bearer "+token)
	resp, err := c.client.Do(req)
	if err != nil {
		return nil, safeAuthError(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode == 404 || resp.StatusCode == 405 || resp.StatusCode == 503 {
		return nil, benchmarkError("history_unsupported")
	}
	if resp.StatusCode != http.StatusOK {
		return nil, benchmarkError(fmt.Sprintf("history_http_%d", resp.StatusCode))
	}
	data, err := io.ReadAll(io.LimitReader(resp.Body, 4*1024*1024+1))
	if err != nil {
		return nil, safeAuthError(err)
	}
	if len(data) > 4*1024*1024 {
		return nil, benchmarkError("history_too_large")
	}
	var messages []json.RawMessage
	if json.Unmarshal(data, &messages) != nil || messages == nil {
		return nil, benchmarkError("invalid_history")
	}
	return messages, nil
}

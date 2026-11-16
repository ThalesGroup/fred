package main

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"sort"
	"sync"
	"time"
)

func pseudonym(campaign, value string) string {
	return fmt.Sprintf("%x", sha256.Sum256([]byte(campaign+":"+value)))
}

type scenarioTurn struct {
	turnMeasurement
	TraceID            string            `json:"trace_id,omitempty"`
	SpanID             string            `json:"span_id,omitempty"`
	Kind               string            `json:"kind"`
	Step               int               `json:"step"`
	Concurrency        int               `json:"concurrency"`
	IdentityID         string            `json:"identity_id"`
	FirstTurn          bool              `json:"first_turn"`
	Target             string            `json:"target"`
	PreparationMode    string            `json:"preparation_mode"`
	Auth               *phaseMeasurement `json:"auth,omitempty"`
	PerformanceOutcome string            `json:"performance_outcome"`
	PerformanceError   string            `json:"performance_error,omitempty"`
	Integrity          string            `json:"integrity"`
	IntegrityError     string            `json:"integrity_error,omitempty"`
	TextFragments      int               `json:"text_fragments"`
	MaxSilenceMS       *float64          `json:"max_silence_ms,omitempty"`
}

// This writer is the only export path for scenario records. Sync after every
// record preserves completed turns even during cancellation or later failures.
type scenarioWriter struct {
	mu     sync.Mutex
	f      *os.File
	err    error
	cancel func()
}

func newScenarioWriter(path string, cancel func()) (*scenarioWriter, error) {
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return nil, benchmarkError("raw_report_unavailable")
	}
	return &scenarioWriter{f: f, cancel: cancel}, nil
}
func (w *scenarioWriter) write(value any) {
	w.mu.Lock()
	defer w.mu.Unlock()
	if w.err != nil {
		return
	}
	w.err = json.NewEncoder(w.f).Encode(value)
	if w.err == nil {
		w.err = w.f.Sync()
	}
	if w.err != nil {
		w.cancel()
	}
}
func (w *scenarioWriter) close() error {
	w.mu.Lock()
	defer w.mu.Unlock()
	err := w.f.Close()
	if w.err != nil || err != nil {
		return benchmarkError("raw_report_failed")
	}
	return nil
}

type metricSummary struct {
	Count int     `json:"count"`
	P50   float64 `json:"p50_ms"`
	P95   float64 `json:"p95_ms"`
	Max   float64 `json:"max_ms"`
}

func metric(values []float64) metricSummary {
	if len(values) == 0 {
		return metricSummary{}
	}
	sort.Float64s(values)
	return metricSummary{len(values), values[int(math.Ceil(float64(len(values))*.50))-1], values[int(math.Ceil(float64(len(values))*.95))-1], values[len(values)-1]}
}
func millis(d time.Duration) float64 { return float64(d) / float64(time.Millisecond) }

type latencyGroup struct {
	Turns              int           `json:"successful_turns"`
	Preparation        metricSummary `json:"preparation"`
	ExecutionFirstText metricSummary `json:"execution_first_text"`
	ExecutionFinal     metricSummary `json:"execution_final"`
	ExecutionEOF       metricSummary `json:"execution_eof"`
	TotalFinal         metricSummary `json:"total_final"`
	TotalEOF           metricSummary `json:"total_eof"`
	MaxSilence         metricSummary `json:"max_silence"`
}

func summarizeTurns(rows []scenarioTurn, first bool) latencyGroup {
	var p, text, final, eof, totalFinal, totalEOF, silence []float64
	g := latencyGroup{}
	for _, r := range rows {
		if r.Outcome != "success" || r.FirstTurn != first {
			continue
		}
		g.Turns++
		m := r.turnMeasurement
		if m.Preparation != nil && m.Preparation.Error == "" {
			p = append(p, millis(m.Preparation.FinishedAt.Sub(m.Preparation.StartedAt)))
		}
		if m.ExecutionStartedAt != nil {
			if m.FirstTextAt != nil {
				text = append(text, millis(m.FirstTextAt.Sub(*m.ExecutionStartedAt)))
			}
			if m.FinalAt != nil {
				final = append(final, millis(m.FinalAt.Sub(*m.ExecutionStartedAt)))
			}
			if m.StreamClosedAt != nil {
				eof = append(eof, millis(m.StreamClosedAt.Sub(*m.ExecutionStartedAt)))
			}
		}
		if m.FinalAt != nil {
			totalFinal = append(totalFinal, millis(m.FinalAt.Sub(m.StartedAt)))
		}
		if m.StreamClosedAt != nil {
			totalEOF = append(totalEOF, millis(m.StreamClosedAt.Sub(m.StartedAt)))
		}
		if r.MaxSilenceMS != nil {
			silence = append(silence, *r.MaxSilenceMS)
		}
	}
	g.Preparation, g.ExecutionFirstText, g.ExecutionFinal, g.ExecutionEOF = metric(p), metric(text), metric(final), metric(eof)
	g.TotalFinal, g.TotalEOF, g.MaxSilence = metric(totalFinal), metric(totalEOF), metric(silence)
	return g
}

type historyRecord struct {
	Kind           string `json:"kind"`
	Step           int    `json:"step"`
	ConversationID string `json:"conversation_id"`
	IdentityID     string `json:"identity_id"`
	Status         string `json:"status"`
	phaseMeasurement
}
type stepReport struct {
	Step               int          `json:"step"`
	Concurrency        int          `json:"concurrency"`
	Planned            int          `json:"planned"`
	Attempted          int          `json:"attempted"`
	NotStarted         int          `json:"not_started"`
	Success            int          `json:"success"`
	Errors             int          `json:"errors"`
	PerformanceErrors  int          `json:"performance_errors"`
	IntegrityErrors    int          `json:"integrity_errors"`
	HistoryVerified    int          `json:"history_verified"`
	HistoryErrors      int          `json:"history_errors"`
	HistoryUnsupported int          `json:"history_unsupported"`
	CleanupErrors      int          `json:"cleanup_errors"`
	LoadElapsedMS      float64      `json:"load_elapsed_ms"`
	First              latencyGroup `json:"first_turn"`
	Following          latencyGroup `json:"following_turns"`
}
type scenarioReport struct {
	Kind          string        `json:"kind"`
	SchemaVersion string        `json:"schema_version"`
	CampaignID    string        `json:"campaign_id"`
	Target        string        `json:"target"`
	IdentityMode  string        `json:"identity_mode"`
	MockProfile   string        `json:"mock_profile"`
	Outcome       string        `json:"outcome"`
	Error         string        `json:"error,omitempty"`
	Steps         []stepReport  `json:"steps"`
	AuthAcquire   metricSummary `json:"auth_acquire"`
	AuthRefresh   metricSummary `json:"auth_refresh"`
	AuthErrors    int           `json:"auth_errors"`
}

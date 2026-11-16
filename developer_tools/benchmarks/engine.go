package main

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"sync"
	"time"
)

// A conversation executes one turn at a time. The engine alone owns scheduling,
// timeouts, failure policy and collection; adapters own wire/session details.
type conversation interface {
	Execute(context.Context) result
	ID() string
	Close()
}

type loadPlan struct {
	Clients, Requests, Turns int
	Ramp, Timeout            time.Duration
	Observe                  func(result)
}

type result struct {
	Duration    time.Duration // Legacy summary: time to final, never time to EOF.
	Err         error
	Measurement turnMeasurement
	Scenario    *scenarioTurn
}

// observe records only semantic milestones shared by both transports.
func (r *result) observe(event streamEvent) {
	now := time.Now()
	if event.Text && r.Measurement.FirstTextAt == nil {
		r.Measurement.FirstTextAt = &now
	}
	if event.Final && r.Measurement.FinalAt == nil {
		r.Measurement.FinalAt = &now
		r.Duration = now.Sub(r.Measurement.StartedAt)
	}
}

// Phase observations are client-side work, never server admission evidence.
type phaseMeasurement struct {
	StartedAt  time.Time `json:"started_at"`
	FinishedAt time.Time `json:"finished_at"`
	Error      string    `json:"error,omitempty"`
}

func (p *phaseMeasurement) finish(err error) {
	p.FinishedAt = time.Now()
	if err != nil {
		p.Error = classifyError(err)
	}
}

// Optional observations are pointers: an unobserved milestone is never zero.
type turnMeasurement struct {
	Preparation        *phaseMeasurement `json:"preparation,omitempty"`
	ExecutionStartedAt *time.Time        `json:"execution_started_at,omitempty"`
	History            *phaseMeasurement `json:"history,omitempty"`
	HistoryMessages    *int              `json:"history_messages,omitempty"`
	SchemaVersion      string            `json:"schema_version"`
	CampaignID         string            `json:"campaign_id"`
	ClientID           int               `json:"client_id"`
	ConversationID     string            `json:"conversation_id"`
	Turn               int               `json:"turn"`
	StartedAt          time.Time         `json:"started_at"`
	FirstTextAt        *time.Time        `json:"first_text_at,omitempty"`
	FinalAt            *time.Time        `json:"final_at,omitempty"`
	StreamClosedAt     *time.Time        `json:"stream_closed_at,omitempty"`
	Outcome            string            `json:"outcome"`
	Error              string            `json:"error,omitempty"`
}

func runLoad(ctx context.Context, plan loadPlan, open func(context.Context, int) (conversation, error)) []result {
	campaignID := newExchangeID()
	results := make(chan result)
	var wg sync.WaitGroup
	// Both legacy scheduling modes use this same sequential conversation loop.
	runTurns := func(client, turns int, previous map[string]int) {
		if ctx.Err() != nil {
			return
		}
		started := time.Now()
		setupCtx, cancel := context.WithTimeout(ctx, plan.Timeout)
		conv, err := open(setupCtx, client)
		cancel()
		identity := newExchangeID()
		if conv != nil {
			defer conv.Close()
			if conv.ID() != "" {
				identity = conv.ID()
			}
		}
		// Campaign-scoped pseudonyms retain shared-session identity without exporting
		// caller/server supplied strings, which may contain private data.
		conversationID := fmt.Sprintf("%x", sha256.Sum256([]byte(campaignID+":"+identity)))
		for turn := 1; turn <= turns; turn++ {
			if ctx.Err() != nil && err == nil {
				return
			}
			res := result{Err: err, Measurement: turnMeasurement{StartedAt: started}}
			if err == nil {
				deadline := time.Now().Add(plan.Timeout)
				if plan.Turns <= 0 {
					deadline = started.Add(plan.Timeout)
				}
				turnCtx, stop := context.WithDeadline(ctx, deadline)
				res = conv.Execute(turnCtx)
				stop()
				if plan.Turns <= 0 {
					// Historical total-request WS latency includes session creation and dial.
					res.Measurement.StartedAt = started
					if res.Measurement.FinalAt != nil {
						res.Duration = res.Measurement.FinalAt.Sub(started)
					}
				}
			}
			m := &res.Measurement
			m.SchemaVersion, m.CampaignID = "fred.bench.turn.v1", campaignID
			previous[conversationID]++
			m.ClientID, m.ConversationID, m.Turn = client+1, conversationID, previous[conversationID]
			m.Outcome = "success"
			if res.Err != nil {
				m.Error = classifyError(res.Err)
				m.Outcome = "error"
				if m.Error == "timeout" || m.Error == "canceled" {
					m.Outcome = m.Error
				}
				// Never allow transport errors, URLs or response content into summaries.
				res.Err = errors.New(m.Error)
			}
			results <- res
			if res.Err != nil {
				return
			}
		}
	}
	jobs := make(chan int)
	for client := 0; client < plan.Clients; client++ {
		wg.Add(1)
		go func(client int) {
			defer wg.Done()
			previous := make(map[string]int)
			if plan.Turns > 0 {
				if plan.Ramp > 0 && plan.Clients > 1 {
					timer := time.NewTimer(plan.Ramp * time.Duration(client) / time.Duration(plan.Clients-1))
					defer timer.Stop()
					select {
					case <-ctx.Done():
						return
					case <-timer.C:
					}
				}
				runTurns(client, plan.Turns, previous)
			} else {
				for range jobs {
					if ctx.Err() == nil {
						runTurns(client, 1, previous)
					}
				}
			}
		}(client)
	}
	go func() {
		defer close(jobs)
		if plan.Turns > 0 {
			return
		}
		for job := 0; job < plan.Requests; job++ {
			select {
			case <-ctx.Done():
				return
			case jobs <- job:
			}
		}
	}()
	go func() { wg.Wait(); close(results) }()
	var collected []result
	for res := range results {
		if plan.Observe != nil {
			plan.Observe(res)
		}
		collected = append(collected, res)
	}
	return collected
}

// benchmarkError carries only a fixed category, never upstream free text.
type benchmarkError string

func (e benchmarkError) Error() string { return string(e) }

func classifyError(err error) string {
	if errors.Is(err, context.DeadlineExceeded) {
		return "timeout"
	}
	if errors.Is(err, context.Canceled) {
		return "canceled"
	}
	var safe benchmarkError
	if errors.As(err, &safe) {
		return string(safe)
	}
	return "transport_error"
}

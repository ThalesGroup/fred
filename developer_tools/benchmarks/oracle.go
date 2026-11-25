package main

import (
	"crypto/sha256"
	"encoding/json"
	"strings"
	"time"
)

const maxAnswerBytes = 128 * 1024

// Keep only digests for post-run history checks; never export answer content.
type completedTurn struct {
	Input, Answer [32]byte
}

// Retain bounded text only until verification; no field below is serialized.
// Logical SDK deltas are observations, not model tokens or network reads.
type answerObserver struct {
	deltas      strings.Builder
	final       string
	finals      int
	fragments   int
	first, last time.Time
	maxGap      time.Duration
	err         error
}

func (o *answerObserver) decode(data []byte) (streamEvent, error) {
	event, err := decodeRuntimeEvent(data)
	if err != nil {
		return event, err
	}
	var body struct {
		Kind    string `json:"kind"`
		Delta   string `json:"delta"`
		Content string `json:"content"`
	}
	if json.Unmarshal(data, &body) != nil {
		return streamEvent{}, benchmarkError("invalid_event")
	}
	if body.Kind == "final" {
		o.finals++
		if len(body.Content) > maxAnswerBytes {
			o.err = benchmarkError("answer_too_large")
		} else {
			o.final = body.Content
		}
	}
	text := body.Delta
	if body.Kind != "assistant_delta" {
		text = ""
	}
	if body.Kind == "final" && o.fragments == 0 {
		text = body.Content
	}
	if text != "" {
		now := time.Now()
		if o.first.IsZero() {
			o.first = now
		}
		if !o.last.IsZero() && now.Sub(o.last) > o.maxGap {
			o.maxGap = now.Sub(o.last)
		}
		o.last = now
		o.fragments++
		if body.Kind == "assistant_delta" {
			if o.deltas.Len()+len(text) > maxAnswerBytes {
				o.err = benchmarkError("answer_too_large")
			} else if o.err == nil {
				o.deltas.WriteString(text)
			}
		}
	}
	return event, nil
}
func (o *answerObserver) verify() error {
	if o.err != nil {
		return o.err
	}
	if o.finals != 1 {
		return benchmarkError("answer_terminal_count")
	}
	answer := o.final
	if answer == "" {
		answer = o.deltas.String()
	}
	if answer == "" {
		return benchmarkError("answer_missing")
	}
	if o.deltas.Len() > 0 && o.final != "" && o.deltas.String() != o.final {
		return benchmarkError("answer_stream_final_mismatch")
	}
	return nil
}

type historyMessage struct {
	SessionID  string `json:"session_id"`
	ExchangeID string `json:"exchange_id"`
	Rank       int    `json:"rank"`
	Role       string `json:"role"`
	Channel    string `json:"channel"`
	Parts      []struct {
		Type string `json:"type"`
		Text string `json:"text"`
	} `json:"parts"`
}

func verifyHistory(data []json.RawMessage, session string, turns []completedTurn) error {
	if len(turns) == 0 {
		return benchmarkError("history_no_completed_turns")
	}
	user, assistant, rank := 0, 0, -1
	exchange := ""
	for _, raw := range data {
		var message historyMessage
		if json.Unmarshal(raw, &message) != nil || message.SessionID != session || message.Rank <= rank {
			return benchmarkError("history_invalid_message")
		}
		rank = message.Rank
		var text strings.Builder
		for _, part := range message.Parts {
			if part.Type == "text" {
				text.WriteString(part.Text)
			}
		}
		if text.Len() > maxAnswerBytes {
			return benchmarkError("history_answer_too_large")
		}
		switch {
		case message.Role == "user":
			if user != assistant || user >= len(turns) || message.ExchangeID == "" {
				return benchmarkError("history_turn_mismatch")
			}
			if sha256.Sum256([]byte(text.String())) != turns[user].Input {
				return benchmarkError("history_input_mismatch")
			}
			exchange = message.ExchangeID
			user++
		case message.Role == "assistant" && message.Channel == "final":
			if user != assistant+1 || message.ExchangeID != exchange || assistant >= len(turns) {
				return benchmarkError("history_turn_mismatch")
			}
			if sha256.Sum256([]byte(text.String())) != turns[assistant].Answer {
				return benchmarkError("history_answer_mismatch")
			}
			assistant++
		}
	}
	if user != len(turns) || assistant != len(turns) {
		return benchmarkError("history_missing_turns")
	}
	return nil
}

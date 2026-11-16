package main

import (
	"encoding/json"
	"io"
	"reflect"
	"strconv"
	"strings"
	"time"
)

const markerPrefix = "MOCK_BENCH_V1 "
const ackPrefix = "MOCK_BENCH_ACK_V1 "
const maxAnswerBytes = 128 * 1024

type turnMarker struct {
	Conversation string `json:"conversation"`
	Turn         int    `json:"turn"`
	Nonce        string `json:"nonce"`
}
type mockACK struct {
	turnMarker
	Previous []turnMarker `json:"previous"`
}

func strictJSON(text string, out any) bool {
	d := json.NewDecoder(strings.NewReader(text))
	d.DisallowUnknownFields()
	return d.Decode(out) == nil && d.Decode(new(any)) == io.EOF
}

func validateACK(answer string, marker turnMarker, previous []turnMarker, profile string) error {
	lines := strings.Split(strings.TrimSuffix(answer, "\n"), "\n")
	if len(lines) == 0 || !strings.HasPrefix(lines[0], ackPrefix) {
		return benchmarkError("ack_missing")
	}
	var ack mockACK
	if !strictJSON(strings.TrimPrefix(lines[0], ackPrefix), &ack) || ack.turnMarker != marker || !reflect.DeepEqual(ack.Previous, previous) {
		return benchmarkError("ack_context_mismatch")
	}
	want := 1
	if profile == "streaming" {
		want = 100
	}
	if len(lines) != want {
		return benchmarkError("ack_fragment_mismatch")
	}
	for i := 1; i < len(lines); i++ {
		if lines[i] != "MOCK_BENCH_FRAGMENT_V1 "+strconv.Itoa(i+1)+"/100" {
			return benchmarkError("ack_fragment_mismatch")
		}
	}
	return nil
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
func (o *answerObserver) verify(marker turnMarker, previous []turnMarker, profile string) error {
	if o.err != nil {
		return o.err
	}
	if o.finals != 1 {
		return benchmarkError("ack_terminal_count")
	}
	answer := o.final
	if answer == "" {
		answer = o.deltas.String()
	}
	if answer == "" {
		return benchmarkError("ack_missing")
	}
	if o.deltas.Len() > 0 && o.final != "" && o.deltas.String() != o.final {
		return benchmarkError("ack_stream_final_mismatch")
	}
	return validateACK(answer, marker, previous, profile)
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

func verifyHistory(data []json.RawMessage, session string, markers []turnMarker, profile string) error {
	if len(markers) == 0 {
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
			if user != assistant || user >= len(markers) || message.ExchangeID == "" {
				return benchmarkError("history_turn_mismatch")
			}
			var found []turnMarker
			for _, line := range strings.Split(text.String(), "\n") {
				if strings.HasPrefix(line, markerPrefix) {
					var marker turnMarker
					if !strictJSON(strings.TrimPrefix(line, markerPrefix), &marker) {
						return benchmarkError("history_marker_invalid")
					}
					found = append(found, marker)
				}
			}
			if len(found) != 1 || found[0] != markers[user] {
				return benchmarkError("history_context_mismatch")
			}
			exchange = message.ExchangeID
			user++
		case message.Role == "assistant" && message.Channel == "final":
			if user != assistant+1 || message.ExchangeID != exchange || assistant >= len(markers) {
				return benchmarkError("history_turn_mismatch")
			}
			if err := validateACK(text.String(), markers[assistant], markers[:assistant], profile); err != nil {
				return benchmarkError("history_ack_mismatch")
			}
			assistant++
		}
	}
	if user != len(markers) || assistant != len(markers) {
		return benchmarkError("history_missing_turns")
	}
	return nil
}

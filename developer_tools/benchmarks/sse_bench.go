package main

import (
	"bufio"
	"crypto/tls"
	"encoding/json"
	"net/http"
	"strings"
	"time"
)

const sseMaxLineBytes = 2 * 1024 * 1024

type streamEvent struct{ Text, Final bool }

func sseHTTPClient(cfg config) *http.Client {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	if cfg.InsecureTLS {
		transport.TLSClientConfig = &tls.Config{InsecureSkipVerify: true}
	}
	// Do not forward credentials or repeat a turn at a redirected endpoint.
	return &http.Client{Transport: transport, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
}

// executeSSE owns HTTP/SSE framing and common observations. The adapter only
// classifies complete data events. A final is necessary but not sufficient:
// success also requires clean EOF, including a complete last event frame.
func executeSSE(client *http.Client, req *http.Request, start time.Time, decode func([]byte) (streamEvent, error)) (res result) {
	res.Measurement.StartedAt = start
	resp, err := client.Do(req)
	if err != nil {
		res.Err = err
		return
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		res.Err = benchmarkError("http_status")
		return
	}
	scanner := bufio.NewScanner(resp.Body)
	scanner.Buffer(make([]byte, 4096), sseMaxLineBytes)
	var data strings.Builder
	hasData := false
	for scanner.Scan() {
		line := scanner.Text()
		if line == "" {
			if !hasData {
				continue
			}
			evt, decodeErr := decode([]byte(strings.TrimSuffix(data.String(), "\n")))
			data.Reset()
			hasData = false
			if decodeErr != nil {
				// Keep draining so a clean remote close can still be measured. The first
				// terminal/protocol error remains the result even if final later arrives.
				if res.Err == nil {
					res.Err = decodeErr
				}
				continue
			}
			res.observe(evt)
			continue
		}
		field, value, _ := strings.Cut(line, ":")
		if field != "data" {
			continue
		}
		value = strings.TrimPrefix(value, " ")
		if data.Len()+len(value)+1 > sseMaxLineBytes {
			if res.Err == nil {
				res.Err = benchmarkError("event_too_large")
			}
			return
		}
		data.WriteString(value)
		data.WriteByte('\n')
		hasData = true
	}
	// Prefer the request's cancellation cause over a body-read wrapper error.
	if err := req.Context().Err(); err != nil {
		if res.Err == nil {
			res.Err = err
		}
		return
	}
	if err := scanner.Err(); err != nil {
		if res.Err == nil {
			res.Err = err
		}
		return
	}

	closed := time.Now()
	res.Measurement.StreamClosedAt = &closed
	if res.Err == nil {
		if hasData || res.Measurement.FinalAt == nil {
			res.Err = benchmarkError("incomplete_stream")
		}
	}
	return
}

// Swift and Weaver use the same SDK runtime event vocabulary.
func decodeRuntimeEvent(data []byte) (streamEvent, error) {
	var event struct {
		Kind    string `json:"kind"`
		Error   string `json:"error"`
		Delta   string `json:"delta"`
		Content string `json:"content"`
	}
	if err := json.Unmarshal(data, &event); err != nil {
		return streamEvent{}, benchmarkError("invalid_event")
	}
	if event.Kind == "node_error" {
		return streamEvent{}, nil
	}
	if event.Error != "" || event.Kind == "execution_error" {
		return streamEvent{}, benchmarkError("execution_error")
	}
	if event.Kind == "execution_interrupted" {
		return streamEvent{}, benchmarkError("execution_interrupted")
	}
	if event.Kind == "awaiting_human" {
		return streamEvent{}, benchmarkError("human_input_required")
	}
	if event.Kind == "" {
		return streamEvent{}, benchmarkError("invalid_event")
	}
	return streamEvent{
		Text:  (event.Kind == "assistant_delta" && event.Delta != "") || (event.Kind == "final" && event.Content != ""),
		Final: event.Kind == "final",
	}, nil
}

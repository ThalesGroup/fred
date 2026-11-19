package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"
)

const reportMaxSpans = 200000
const reportMaxTurnSpans = 2000

var traceCategories = []string{"runtime", "control_plane", "auth", "keycloak", "llm", "mcp", "tool", "persistence"}

type htmlInterval struct {
	Label string  `json:"label"`
	Start float64 `json:"start"`
	End   float64 `json:"end"`
}
type htmlSpan struct {
	ID         string   `json:"id"`
	Parent     string   `json:"parent"`
	Category   string   `json:"category"`
	Service    string   `json:"service"`
	Peer       string   `json:"peer"`
	Kind       int      `json:"kind"`
	Status     int      `json:"status"`
	Operation  string   `json:"operation"`
	FirstChunk *float64 `json:"firstChunk"`
	Start      float64  `json:"start"`
	End        float64  `json:"end"`
}

func (s htmlSpan) equal(other htmlSpan) bool {
	if (s.FirstChunk == nil) != (other.FirstChunk == nil) || (s.FirstChunk != nil && *s.FirstChunk != *other.FirstChunk) {
		return false
	}
	s.FirstChunk, other.FirstChunk = nil, nil
	return s == other
}

type htmlTurnDetail struct {
	TraceID      string             `json:"traceId"`
	RootID       string             `json:"rootId"`
	Duration     *float64           `json:"duration"`
	Complete     bool               `json:"complete"`
	Observations []htmlInterval     `json:"observations"`
	Spans        []htmlSpan         `json:"spans"`
	Components   map[string]float64 `json:"components"`
	Unattributed *float64           `json:"unattributed"`
	Warnings     []string           `json:"warnings"`
	start        time.Time
}
type htmlAuth struct {
	Operation string  `json:"operation"`
	Duration  float64 `json:"duration"`
	Error     bool    `json:"error"`
}

func (d *htmlTurnDetail) warn(message string) {
	for _, w := range d.Warnings {
		if w == message {
			return
		}
	}
	d.Warnings = append(d.Warnings, message)
}

func projectTurnDetail(row scenarioTurn) *htmlTurnDetail {
	d := &htmlTurnDetail{start: row.StartedAt, Observations: []htmlInterval{}, Spans: []htmlSpan{}, Components: map[string]float64{}, Warnings: []string{}}
	if row.TraceID != "" || row.SpanID != "" {
		if validTraceHex(row.TraceID, 32) && validTraceHex(row.SpanID, 16) {
			d.TraceID, d.RootID = strings.ToLower(row.TraceID), strings.ToLower(row.SpanID)
		} else {
			d.warn("Identifiants de trace invalides : aucune corrélation.")
		}
	}
	if row.StartedAt.IsZero() {
		d.warn("Début du tour absent.")
		return d
	}
	end := row.StreamClosedAt
	if end == nil || end.IsZero() || end.Before(row.StartedAt) {
		end = row.FinalAt
	} else {
		d.Complete = true
	}
	if end != nil && !end.IsZero() && !end.Before(row.StartedAt) {
		duration := millis(end.Sub(row.StartedAt))
		d.Duration = &duration
		d.Observations = append(d.Observations, htmlInterval{"Tour observé par le client", 0, duration})
	}
	if !d.Complete {
		d.warn("Fin du flux non observée : fenêtre du tour incomplète.")
	}
	add := func(label string, start, finish time.Time) {
		if start.IsZero() || finish.IsZero() || finish.Before(start) || start.Before(row.StartedAt) {
			d.warn("Horodatages clients incomplets ou incohérents.")
			return
		}
		d.Observations = append(d.Observations, htmlInterval{label, millis(start.Sub(row.StartedAt)), millis(finish.Sub(row.StartedAt))})
	}
	if row.Auth != nil {
		add("Renouvellement Keycloak (client)", row.Auth.StartedAt, row.Auth.FinishedAt)
	}
	if row.Preparation != nil {
		add("Préparation Control Plane (client)", row.Preparation.StartedAt, row.Preparation.FinishedAt)
	}
	if row.ExecutionStartedAt != nil && end != nil {
		add("Requête d'exécution / flux (client)", *row.ExecutionStartedAt, *end)
	}
	if row.FirstTextAt != nil {
		add("Premier texte (client)", *row.FirstTextAt, *row.FirstTextAt)
	}
	if row.FinalAt != nil {
		add("Réponse finale (client)", *row.FinalAt, *row.FinalAt)
	}
	return d
}

type otlpAttribute struct {
	Key   string `json:"key"`
	Value struct {
		String string          `json:"stringValue"`
		Int    json.RawMessage `json:"intValue"`
		Double json.RawMessage `json:"doubleValue"`
	} `json:"value"`
}
type otlpSpan struct {
	Name       string          `json:"name"`
	TraceID    string          `json:"traceId"`
	ID         string          `json:"spanId"`
	Parent     string          `json:"parentSpanId"`
	Start      json.RawMessage `json:"startTimeUnixNano"`
	End        json.RawMessage `json:"endTimeUnixNano"`
	Kind       int             `json:"kind"`
	Attributes []otlpAttribute `json:"attributes"`
	Status     struct {
		Code int `json:"code"`
	} `json:"status"`
}
type otlpExport struct {
	Resources []struct {
		Resource struct {
			Attributes []otlpAttribute `json:"attributes"`
		} `json:"resource"`
		Scopes []struct {
			Spans []otlpSpan `json:"spans"`
		} `json:"scopeSpans"`
	} `json:"resourceSpans"`
}

func attributeValue(attrs []otlpAttribute, key string) string {
	value := ""
	for _, attr := range attrs {
		if attr.Key == key {
			if value != "" {
				return ""
			}
			value = attr.Value.String
		}
	}
	return value
}
func traceCategory(value string) string {
	for _, category := range traceCategories {
		if value == category {
			return value
		}
	}
	return "unknown"
}
func traceService(value string) string {
	switch value {
	case "fred-agents", "fred-runtime", "control-plane", "keycloak", "llm", "mcp", "persistence":
		return value
	}
	return "unknown"
}
func traceOperation(value string) string {
	switch value {
	case "agent.invoke", "agent.stream", "v2.graph.await_human", "v2.graph.model",
		"v2.graph.structured_model", "v2.react.model", "v2.graph.tool",
		"v2.graph.runtime_tool", "v2.react.runtime_tool", "tool.invoke",
		"artifact.publish", "resource.fetch", "agent.http", "pod_authz",
		"runtime_binding", "runtime_binding_internal", "control_plane.runtime",
		"auth.jwt.verify", "auth.m2m.acquire", "iam.jwks.http", "iam.token.initial",
		"iam.token.renewal", "mcp.http", "history.write", "checkpoint.operation",
		"runtime.operation", "control_plane.http", "control_plane.resolve_runtime",
		"auth.jwt.validate", "auth.jwks.lookup", "auth.jwks.fetch":
		return value
	}
	return ""
}
func firstChunkMillis(attrs []otlpAttribute) *float64 {
	var result *float64
	seen := false
	for _, attr := range attrs {
		if attr.Key != "first_chunk_ms" {
			continue
		}
		if seen {
			return nil
		}
		seen = true
		raw := attr.Value.Double
		if len(attr.Value.Int) > 0 {
			if len(raw) > 0 {
				return nil
			}
			raw = attr.Value.Int
		}
		value, err := strconv.ParseFloat(strings.Trim(string(raw), "\""), 64)
		if err == nil && !math.IsNaN(value) && !math.IsInf(value, 0) && value >= 0 && value <= 86400000 {
			result = &value
		}
	}
	return result
}
func otlpTime(data json.RawMessage) (time.Time, bool) {
	// OTLP permits decimal strings or numbers, never a floating-point round trip.
	text := strings.Trim(string(data), "\"")
	value, err := strconv.ParseInt(text, 10, 64)
	if err != nil || value <= 0 {
		return time.Time{}, false
	}
	return time.Unix(0, value), true
}

// Accept standard ExportTraceServiceRequest objects, one or many (Collector
// file exporter JSONL). Nothing from unknown fields/attributes reaches HTML.
func attachOTLPTraces(runs []htmlRun, path string) error {
	if path == "" {
		return nil
	}
	info, err := os.Lstat(path)
	if err != nil || !info.Mode().IsRegular() || info.Size() > reportMaxBytes {
		return errors.New("OTLP input must be a regular file of at most 128 MiB")
	}
	file, err := os.Open(path)
	if err != nil {
		return errors.New("cannot open OTLP input")
	}
	defer file.Close()
	turns := map[string]*htmlTurnDetail{}
	for i := range runs {
		for j := range runs[i].Turns {
			d := runs[i].Turns[j].Detail
			if d.TraceID != "" {
				if turns[d.TraceID] != nil {
					return errors.New("duplicate trace ID across scenario turns")
				}
				turns[d.TraceID] = d
			}
		}
	}
	decoder := json.NewDecoder(io.LimitReader(file, reportMaxBytes+1))
	spans := map[string]map[string]htmlSpan{}
	total, unmatched, invalid, duplicates := 0, 0, 0, 0
	for {
		var batch otlpExport
		err := decoder.Decode(&batch)
		if err == io.EOF {
			break
		}
		if err != nil || batch.Resources == nil {
			return errors.New("invalid OTLP JSON export; expected resourceSpans/scopeSpans/spans")
		}
		for _, resource := range batch.Resources {
			for _, scope := range resource.Scopes {
				for _, raw := range scope.Spans {
					total++
					if total > reportMaxSpans {
						return errors.New("OTLP limit: 200000 spans")
					}
					traceID, id, parent := strings.ToLower(raw.TraceID), strings.ToLower(raw.ID), strings.ToLower(raw.Parent)
					if !validTraceHex(traceID, 32) || !validTraceHex(id, 16) || (parent != "" && !validTraceHex(parent, 16)) {
						invalid++
						continue
					}
					d := turns[traceID]
					if d == nil {
						unmatched++
						continue
					}
					start, okStart := otlpTime(raw.Start)
					end, okEnd := otlpTime(raw.End)
					if !okStart || !okEnd || end.Before(start) || raw.Kind < 0 || raw.Kind > 5 || raw.Status.Code < 0 || raw.Status.Code > 2 || id == d.RootID {
						invalid++
						d.warn("Span invalide ou incomplet ignoré.")
						continue
					}
					projected := htmlSpan{ID: id, Parent: parent, Category: traceCategory(attributeValue(raw.Attributes, "fred.category")), Service: traceService(attributeValue(resource.Resource.Attributes, "service.name")), Peer: traceService(attributeValue(raw.Attributes, "peer.service")), Kind: raw.Kind, Status: raw.Status.Code, Operation: traceOperation(raw.Name), Start: millis(start.Sub(d.start)), End: millis(end.Sub(d.start))}
					if projected.Category == "llm" {
						projected.FirstChunk = firstChunkMillis(raw.Attributes)
						if projected.FirstChunk != nil && *projected.FirstChunk > projected.End-projected.Start {
							d.warn("Premier fragment LLM après la fin du span : mesure incohérente ignorée.")
							projected.FirstChunk = nil
						}
					}
					if d.start.IsZero() {
						invalid++
						continue
					}
					if spans[traceID] == nil {
						spans[traceID] = map[string]htmlSpan{}
					}
					if existing, found := spans[traceID][id]; found {
						duplicates++
						if !existing.equal(projected) {
							return errors.New("conflicting duplicate OTLP span ID")
						}
						d.warn("Spans dupliqués dédupliqués ; aucun temps compté deux fois.")
						continue
					}
					if len(spans[traceID]) >= reportMaxTurnSpans {
						return errors.New("OTLP limit: 2000 spans per turn")
					}
					spans[traceID][id] = projected
				}
			}
		}
	}
	for traceID, byID := range spans {
		d := turns[traceID]
		for _, span := range byID {
			d.Spans = append(d.Spans, span)
		}
		sort.Slice(d.Spans, func(i, j int) bool {
			a, b := d.Spans[i], d.Spans[j]
			if a.Start == b.Start {
				return a.ID < b.ID
			}
			return a.Start < b.Start
		})
		colors := map[string]int{}
		var visit func(string)
		visit = func(id string) {
			if colors[id] == 1 {
				d.warn("Cycle dans les parents de spans : arbre incomplet.")
				return
			}
			if colors[id] == 2 {
				return
			}
			colors[id] = 1
			if p := byID[id].Parent; p != "" && p != d.RootID {
				if _, ok := byID[p]; ok {
					visit(p)
				}
			}
			colors[id] = 2
		}
		groups := map[string][]htmlInterval{}
		var attributed []htmlInterval
		for _, span := range d.Spans {
			visit(span.ID)
			if span.Parent == "" {
				d.warn("Span racine distant : parent client non attesté.")
			} else if span.Parent != d.RootID {
				if parent, ok := byID[span.Parent]; !ok {
					d.warn("Parent de span absent de l'export : carte partielle.")
				} else if span.Start < parent.Start || span.End > parent.End {
					d.warn("Span hors intervalle de son parent : horloges décalées ou travail asynchrone ; parenté conservée.")
				}
			}
			if span.Category == "unknown" {
				d.warn("Catégorie non reconnue : span visible, durée non attribuée.")
			}
			if span.Start < 0 || (d.Duration != nil && span.End > *d.Duration) {
				d.warn("Span hors fenêtre client : horloges décalées ou travail après le tour ; agrégats bornés à la fenêtre.")
			}
			if d.Duration == nil || span.Category == "unknown" {
				continue
			}
			start, end := max(0, span.Start), min(*d.Duration, span.End)
			if end < start {
				continue
			}
			interval := htmlInterval{Start: start, End: end}
			groups[span.Category] = append(groups[span.Category], interval)
			attributed = append(attributed, interval)
		}
		for category, intervals := range groups {
			d.Components[category] = unionIntervals(intervals)
		}
		if d.Duration != nil {
			remaining := max(0, *d.Duration-unionIntervals(attributed))
			d.Unattributed = &remaining
		}
	}
	message := fmt.Sprintf("Import OTLP : %d spans lus, %d sans tour correspondant, %d invalides ignorés, %d doublons dédupliqués. L'export ne garantit pas une trace exhaustive.", total, unmatched, invalid, duplicates)
	for i := range runs {
		runs[i].TraceImport = message
	}
	return nil
}

func unionIntervals(intervals []htmlInterval) float64 {
	if len(intervals) == 0 {
		return 0
	}
	sort.Slice(intervals, func(i, j int) bool { return intervals[i].Start < intervals[j].Start })
	start, end, total := intervals[0].Start, intervals[0].End, 0.0
	for _, span := range intervals[1:] {
		if span.Start <= end {
			end = max(end, span.End)
		} else {
			total += end - start
			start, end = span.Start, span.End
		}
	}
	return total + end - start
}

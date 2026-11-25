package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

type benchCommand func(context.Context, string, ...string) ([]byte, error)
type cappedOutput struct {
	bytes.Buffer
	limit int
}

func (w *cappedOutput) Write(p []byte) (int, error) {
	if len(p) > w.limit-w.Len() {
		return 0, fmt.Errorf("command output exceeds the size limit")
	}
	return w.Buffer.Write(p)
}
func readBenchCommand(ctx context.Context, name string, args ...string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, name, args...)
	out := &cappedOutput{limit: reportMaxBytes}
	cmd.Stdout, cmd.Stderr = out, io.Discard
	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("cannot read using %s", name)
	}
	return out.Bytes(), nil
}

type benchCollector struct {
	node, directory string
	command         benchCommand
}

var k3dNodeName = regexp.MustCompile(`^k3d-fred-(server|agent)-[0-9]+$`)
var traceBackupName = regexp.MustCompile(`^traces\.otlp(-[0-9T:.+-]+)?\.jsonl$`)

func discoverBenchCollector(ctx context.Context, command benchCommand) (*benchCollector, error) {
	get := func(resource, name, namespace string, out any) error {
		args := []string{"--context", "k3d-fred"}
		if namespace != "" {
			args = append(args, "-n", namespace)
		}
		args = append(args, "get", resource, name, "-o", "json")
		data, err := command(ctx, "kubectl", args...)
		if err != nil || len(data) > 1<<20 || json.Unmarshal(data, out) != nil {
			return fmt.Errorf("k3d collector is unreachable")
		}
		return nil
	}
	var deployment struct {
		Status struct {
			Ready int `json:"readyReplicas"`
		} `json:"status"`
	}
	if err := get("deployment", "otel-collector", "fred-infra", &deployment); err != nil || deployment.Status.Ready < 1 {
		return nil, fmt.Errorf("k3d collector is missing or not ready")
	}
	var pvc struct {
		Spec struct {
			Volume string `json:"volumeName"`
		} `json:"spec"`
	}
	if err := get("pvc", "otel-traces", "fred-infra", &pvc); err != nil {
		return nil, err
	}
	if !strings.HasPrefix(pvc.Spec.Volume, "pvc-") || !canonicalUUID.MatchString(strings.TrimPrefix(pvc.Spec.Volume, "pvc-")) {
		return nil, fmt.Errorf("unexpected trace volume")
	}
	var pv struct {
		Spec struct {
			Local struct {
				Path string `json:"path"`
			} `json:"local"`
			Affinity struct {
				Required struct {
					Terms []struct {
						Expressions []struct {
							Key, Operator string
							Values        []string
						} `json:"matchExpressions"`
					} `json:"nodeSelectorTerms"`
				} `json:"required"`
			} `json:"nodeAffinity"`
		} `json:"spec"`
	}
	if err := get("pv", pvc.Spec.Volume, "", &pv); err != nil {
		return nil, err
	}
	expected := "/var/lib/rancher/k3s/storage/" + pvc.Spec.Volume + "_fred-infra_otel-traces"
	if pv.Spec.Local.Path != expected {
		return nil, fmt.Errorf("trace volume is not local; manual import is required")
	}
	node := ""
	for _, t := range pv.Spec.Affinity.Required.Terms {
		for _, e := range t.Expressions {
			if e.Key == "kubernetes.io/hostname" && e.Operator == "In" && len(e.Values) == 1 && k3dNodeName.MatchString(e.Values[0]) {
				if node != "" && node != e.Values[0] {
					return nil, fmt.Errorf("trace volume spans multiple nodes")
				}
				node = e.Values[0]
			}
		}
	}
	if node == "" {
		return nil, fmt.Errorf("collector k3d node was not found")
	}
	c := &benchCollector{node, expected, command}
	if _, err := c.files(ctx); err != nil {
		return nil, err
	}
	return c, nil
}
func (c *benchCollector) files(ctx context.Context) ([]string, error) {
	data, err := c.command(ctx, "docker", "exec", c.node, "find", c.directory, "-maxdepth", "1", "-type", "f", "-name", "traces*.jsonl", "-print")
	if err != nil || len(data) > 65536 {
		return nil, fmt.Errorf("trace file is not accessible through Docker")
	}
	var files []string
	for _, f := range strings.Split(strings.TrimSpace(string(data)), "\n") {
		if path.Dir(f) == c.directory && traceBackupName.MatchString(path.Base(f)) {
			files = append(files, f)
		}
	}
	if len(files) == 0 || len(files) > 8 {
		return nil, fmt.Errorf("trace file is missing or rotation is unexpected")
	}
	return files, nil
}

// Persist only this run's spans and the report's allowlisted technical fields.
// A partial last record belongs to an active collector write; the next snapshot
// retries it. No other user's trace or arbitrary attribute reaches the result.
func filterBenchTraces(data []byte, ids map[string]bool, output io.Writer) error {
	decoder := json.NewDecoder(bytes.NewReader(data))
	for {
		var batch otlpExport
		err := decoder.Decode(&batch)
		if err == io.EOF || err == io.ErrUnexpectedEOF {
			return nil
		}
		if err != nil || batch.Resources == nil {
			return fmt.Errorf("invalid OTLP export")
		}
		for ri := range batch.Resources {
			resource := &batch.Resources[ri]
			service := traceService(attributeValue(resource.Resource.Attributes, "service.name"))
			resource.Resource.Attributes = nil
			a := otlpAttribute{Key: "service.name"}
			a.Value.String = service
			resource.Resource.Attributes = append(resource.Resource.Attributes, a)
			for si := range resource.Scopes {
				scope := &resource.Scopes[si]
				kept := []otlpSpan{}
				for _, span := range scope.Spans {
					if !ids[strings.ToLower(span.TraceID)] {
						continue
					}
					_, validStart := otlpTime(span.Start)
					_, validEnd := otlpTime(span.End)
					if !validTraceHex(span.ID, 16) || (span.Parent != "" && !validTraceHex(span.Parent, 16)) || !validStart || !validEnd {
						return fmt.Errorf("invalid OTLP identifiers or timestamps")
					}
					span.Name = traceOperation(span.Name)
					attrs := []otlpAttribute{}
					for _, attr := range span.Attributes {
						safe := otlpAttribute{Key: attr.Key}
						switch attr.Key {
						case "fred.category":
							safe.Value.String = traceCategory(attr.Value.String)
							attrs = append(attrs, safe)
						case "peer.service":
							safe.Value.String = traceService(attr.Value.String)
							attrs = append(attrs, safe)
						case "first_chunk_ms":
							if value := firstChunkMillis([]otlpAttribute{attr}); value != nil {
								safe.Value.Double, _ = json.Marshal(*value)
								attrs = append(attrs, safe)
							}
						}
					}
					span.Attributes = attrs
					kept = append(kept, span)
				}
				scope.Spans = kept
			}
		}
		if err := json.NewEncoder(output).Encode(batch); err != nil {
			return err
		}
	}
}

func benchTraceCoverage(runs []htmlRun) (matched, complete, spans int) {
	for _, run := range runs {
		for _, turn := range run.Turns {
			if turn.Detail == nil {
				continue
			}
			n := len(turn.Detail.Spans)
			spans += n
			if n > 0 {
				matched++
			}
			if n > 0 && turn.Detail.Complete && len(turn.Detail.Warnings) == 0 {
				complete++
			}
		}
	}
	return
}

func (c *benchCollector) collect(ctx context.Context, directory string) (int, int, error) {
	runs, err := readHTMLRuns(directory)
	if err != nil {
		return 0, 0, err
	}
	ids := map[string]bool{}
	for _, run := range runs {
		for _, turn := range run.Turns {
			if turn.Detail != nil && turn.Detail.TraceID != "" {
				ids[turn.Detail.TraceID] = true
			}
		}
	}
	if len(ids) == 0 {
		return 0, 0, nil
	}
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	matched, complete, previous, stable := 0, 0, -1, 0
	for attempt := 0; attempt < 10; attempt++ {
		files, err := c.files(ctx)
		if err != nil {
			return matched, complete, err
		}
		snapshot := &cappedOutput{limit: reportMaxBytes}
		for _, f := range files {
			data, err := c.command(ctx, "docker", "exec", c.node, "cat", f)
			if err != nil {
				return matched, complete, err
			}
			if err := filterBenchTraces(data, ids, snapshot); err != nil {
				return matched, complete, err
			}
		}
		file, err := os.CreateTemp(directory, ".traces-*.otlp.jsonl")
		if err != nil {
			return matched, complete, err
		}
		name := file.Name()
		_, writeErr := file.Write(snapshot.Bytes())
		closeErr := file.Close()
		if writeErr != nil || closeErr != nil {
			os.Remove(name)
			return matched, complete, fmt.Errorf("cannot write traces")
		}
		fresh, err := readHTMLRuns(directory, name)
		if err == nil {
			err = attachOTLPTraces(fresh, name)
		}
		if err != nil {
			os.Remove(name)
			return matched, complete, err
		}
		var spans int
		matched, complete, spans = benchTraceCoverage(fresh)
		if err := os.Rename(name, filepath.Join(directory, "traces.otlp.jsonl")); err != nil {
			os.Remove(name)
			return matched, complete, err
		}
		if spans == previous {
			stable++
		} else {
			stable = 0
		}
		previous = spans
		if matched == len(ids) && stable >= 2 {
			return matched, complete, nil
		}
		select {
		case <-ctx.Done():
			return matched, complete, ctx.Err()
		case <-time.After(2 * time.Second):
		}
	}
	return matched, complete, nil
}

package main

import (
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strconv"
)

type benchOptions struct {
	mode                          string
	requests, concurrency, warmup int
	sampleRate                    float64
	cleanup                       bool
}

func (o benchOptions) resolved() (benchOptions, error) {
	if o.mode == "" {
		o.mode = "diagnostic"
	}
	if o.mode != "diagnostic" && o.mode != "performance" {
		return o, fmt.Errorf("--mode must be diagnostic or performance")
	}
	if o.requests == 0 {
		if o.mode == "performance" {
			o.requests = 1000
		} else {
			o.requests = 10
		}
	}
	if o.concurrency == 0 {
		if o.mode == "performance" {
			o.concurrency = min(10, (o.requests+9)/10)
		} else {
			o.concurrency = 1
		}
	}
	if o.warmup == -1 {
		if o.mode == "performance" {
			o.warmup = 20
		} else {
			o.warmup = 0
		}
	}
	if o.sampleRate == -1 {
		if o.mode == "performance" {
			o.sampleRate = 0
		} else {
			o.sampleRate = 1
		}
	}
	if o.requests < 1 || o.requests > 50000 {
		return o, fmt.Errorf("--requests must be between 1 and 50000")
	}
	if o.concurrency < 1 || o.concurrency > 256 || o.concurrency > (o.requests+9)/10 {
		return o, fmt.Errorf("--concurrency must be 1..256 and cannot exceed the number of 10-question conversations")
	}
	if o.warmup < 0 || o.warmup > 1000 {
		return o, fmt.Errorf("--warmup must be between 0 and 1000")
	}
	if !(o.sampleRate >= 0 && o.sampleRate <= 1) {
		return o, fmt.Errorf("--trace-sample must be between 0 and 1")
	}
	if o.mode == "diagnostic" && (o.requests != 10 || o.concurrency != 1 || o.warmup != 0) {
		return o, fmt.Errorf("diagnostic uses 10 questions, one conversation and no warm-up; use performance for load settings")
	}
	return o, nil
}
func (o benchOptions) apply(cfg config) config {
	cfg.Mode, cfg.WarmupTurns, cfg.DeleteSession = o.mode, o.warmup, o.cleanup
	cfg.TraceTurns = true
	rate := o.sampleRate
	cfg.TraceSampleRate = &rate
	cfg.ConcurrencySteps = strconv.Itoa(o.concurrency)
	if o.mode == "performance" {
		cfg.TotalTurns = o.requests
	}
	return cfg
}

// Bound retained local results without deleting earlier runs. Each run has
// independent raw/trace/HTML limits; reserve room before any warm-up/model call.
func checkBenchStorage(dir string) error {
	var size int64
	count := 0
	err := filepath.WalkDir(dir, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		count++
		if count > 50000 {
			return fmt.Errorf("too many result files; archive old .bench runs first")
		}
		if d.Type()&os.ModeSymlink != 0 {
			return fmt.Errorf("symbolic links are not allowed inside .bench")
		}
		if !d.IsDir() {
			info, err := d.Info()
			if err != nil {
				return err
			}
			size += info.Size()
		}
		if size > 512<<20 {
			return fmt.Errorf(".bench exceeds 512 MiB; archive old runs before starting another run")
		}
		return nil
	})
	return err
}

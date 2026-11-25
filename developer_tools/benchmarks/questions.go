package main

import (
	"encoding/json"
	"io"
	"os"
	"slices"
	"strings"
)

// Load once, before authentication or creating any conversation. Every client
// receives the same ordered questions; neither questions nor answers are exported.
func scenarioQuestions(cfg config) (config, error) {
	if cfg.ConcurrencySteps == "" {
		cfg.ConcurrencySteps = "1"
	}
	if cfg.QuestionsFile == "" && len(cfg.Questions) == 0 {
		if strings.TrimSpace(cfg.Message) == "" || len(cfg.Message) > maxAnswerBytes {
			return cfg, benchmarkError("invalid_question")
		}
		return cfg, nil
	}
	if slices.Contains(cfg.ExplicitFlags, "message") || slices.Contains(cfg.ExplicitFlags, "requests-per-client") {
		return cfg, benchmarkError("questions_file_sets_messages_and_turn_count")
	}
	if cfg.QuestionsFile != "" {
		f, err := os.Open(cfg.QuestionsFile)
		if err != nil {
			return cfg, benchmarkError("questions_unreadable")
		}
		defer f.Close()
		info, err := f.Stat()
		if err != nil || !info.Mode().IsRegular() || info.Size() > 1024*1024 {
			return cfg, benchmarkError("questions_require_regular_file_under_1MiB")
		}
		d := json.NewDecoder(io.LimitReader(f, 1024*1024+1))
		if d.Decode(&cfg.Questions) != nil || d.Decode(new(any)) != io.EOF || len(cfg.Questions) < 1 || len(cfg.Questions) > 100 {
			return cfg, benchmarkError("questions_require_1_to_100_strings")
		}
	}
	if len(cfg.Questions) < 1 || len(cfg.Questions) > 100 {
		return cfg, benchmarkError("questions_require_1_to_100_strings")
	}
	for _, question := range cfg.Questions {
		if strings.TrimSpace(question) == "" || len(question) > maxAnswerBytes {
			return cfg, benchmarkError("invalid_question")
		}
	}
	cfg.RequestsPerClient = len(cfg.Questions)
	return cfg, nil
}

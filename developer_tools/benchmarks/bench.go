package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"

	"golang.org/x/term"
)

const benchHelp = `bench - measure Fred agents and save JSON/JSONL results

Usage:
  ./bench
  ./bench run [options]
  ./bench report [options]
  ./bench help [command]

Commands:
  run       Choose diagnostic or performance, then select a Fred agent
  report    Optional legacy HTML tool; never called by run
  help      Show usage for bench, run or report

Options:
  -h, --h, -help, --help    Show help and exit

Defaults:
  Diagnostic: 10 questions, one conversation, all traces requested.
  Performance: 1000 questions, concurrency 10, warm-up 20, traces off.
  Both modes measure client latency, throughput and errors for every turn.
  The selected Fred agent owns the model choice (real provider or mock).
  CPU/RAM are not collected. Runs save JSON/JSONL, without generating HTML.
  Results and preferences are saved in .bench/ alongside this binary.
  No installation, deployment or model call is performed by help commands.

Environment:
  NO_COLOR         Disable terminal colors
  BENCH_STATE_DIR   Explicit alternative results directory (absolute path)

Examples:
  ./bench
  ./bench run --origin http://weaver.localhost:8088
  ./bench run --mode performance --requests 10000 --concurrency 20
  ./bench run --mode performance --trace-sample 0.01

Use arrow keys and Enter to select; Ctrl+C to stop.
Legacy -scenario/-target options remain available for scripts; see README.md.
`

var generalBenchQuestions = []string{
	"Explain the difference between weather and climate in three short sentences.",
	"Give a concrete everyday example of the difference you just explained.",
	"A shop sells notebooks for 4 dollars each and pens for 2 dollars each. What is the total price of 3 notebooks and 5 pens? Show your calculation.",
	"A train leaves at 09:15 and arrives at 11:05 on the same day. How long is the journey? Explain briefly.",
	"Summarize this paragraph in one sentence: A small town replaced its streetlights with LED bulbs. Electricity use fell, maintenance became less frequent, and residents reported better visibility at night. The initial investment was recovered through lower running costs.",
	"Rewrite this message in a polite, professional tone: Send me the numbers today. I cannot finish the report without them.",
	"Give three advantages and three limitations of working from home. Use short bullet points.",
	"All blue boxes are heavy. Some heavy boxes are fragile. Does it follow that some blue boxes are fragile? Explain your reasoning.",
	"Plan a simple two-hour study session with two short breaks. Specify the duration of each activity so the total is exactly two hours.",
	"Earlier in this conversation you calculated the price of notebooks and pens. What was the total, and what would it be with a 10 percent discount?",
}

func documentBenchQuestions(topic string) []string {
	prompts := []string{
		"Using the available documents, explain what %s is. Cite your sources; say if the documents do not contain the answer.",
		"What problem does %s address, according to the documents? Cite the relevant evidence.",
		"Describe the main components or ideas of %s found in the documents. Cite your sources.",
		"How does %s work, step by step, according to the documents? Distinguish evidence from inference.",
		"What benefits of %s are reported in the documents? Cite your sources.",
		"What limitations or risks of %s are explicitly mentioned? Do not invent missing evidence.",
		"What evidence or results support %s in the documents? Include numbers only when sourced.",
		"Which alternatives to %s are discussed in the documents, and how do they compare? Cite your sources.",
		"What important questions about %s remain unanswered by the available documents?",
		"Summarize our discussion of %s in five points, each supported by a source where available.",
	}
	questions := make([]string, len(prompts))
	for i, p := range prompts {
		questions[i] = fmt.Sprintf(p, topic)
	}
	return questions
}

type benchPreferences struct {
	Origin  string `json:"origin"`
	Space   string `json:"space,omitempty"`
	Agent   string `json:"agent,omitempty"`
	LastRun string `json:"last_run,omitempty"`
}

func benchStateDirectory() (string, error) {
	dir := os.Getenv("BENCH_STATE_DIR")
	if dir == "" {
		executable, err := os.Executable()
		if err != nil {
			return "", err
		}
		dir = filepath.Join(filepath.Dir(executable), ".bench")
	}
	if !filepath.IsAbs(dir) {
		return "", fmt.Errorf("BENCH_STATE_DIR must be an absolute path")
	}
	if err := os.MkdirAll(dir, 0700); err != nil {
		return "", err
	}
	info, err := os.Lstat(dir)
	if err != nil || !info.IsDir() || info.Mode().Perm()&0077 != 0 {
		return "", fmt.Errorf("bench state directory must be private (0700), not a symbolic link")
	}
	return dir, nil
}
func readBenchPreferences(dir string) (benchPreferences, error) {
	p := benchPreferences{Origin: "http://weaver.localhost:8088"}
	file := filepath.Join(dir, "preferences.json")
	info, err := os.Lstat(file)
	if os.IsNotExist(err) {
		return p, nil
	}
	if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0077 != 0 || info.Size() > 16384 {
		return p, fmt.Errorf("bench preferences are unreadable or not private")
	}
	data, err := os.ReadFile(file)
	if err != nil || json.Unmarshal(data, &p) != nil {
		return p, fmt.Errorf("invalid bench preferences")
	}
	return p, nil
}
func saveBenchPreferences(dir string, p benchPreferences) error {
	data, err := json.MarshalIndent(p, "", "  ")
	if err != nil {
		return err
	}
	f, err := os.CreateTemp(dir, ".preferences-*")
	if err != nil {
		return err
	}
	defer os.Remove(f.Name())
	_, writeErr := f.Write(data)
	closeErr := f.Close()
	if writeErr != nil {
		return writeErr
	}
	if closeErr != nil {
		return closeErr
	}
	return os.Rename(f.Name(), filepath.Join(dir, "preferences.json"))
}
func reportBenchURL(file string) string { return (&url.URL{Scheme: "file", Path: file}).String() }
func openLatestBenchReport() int {
	dir, err := benchStateDirectory()
	var p benchPreferences
	if err == nil {
		p, err = readBenchPreferences(dir)
	}
	if err == nil && (p.LastRun == "" || filepath.Base(p.LastRun) != p.LastRun || !strings.HasPrefix(p.LastRun, "run-")) {
		err = fmt.Errorf("no saved report; run ./bench first")
	}
	file := filepath.Join(dir, p.LastRun, "report.html")
	if err == nil {
		parent, e := os.Lstat(filepath.Dir(file))
		if e != nil || !parent.IsDir() {
			err = fmt.Errorf("latest report directory is unavailable")
		}
		info, e := os.Lstat(file)
		if e != nil || !info.Mode().IsRegular() {
			err = fmt.Errorf("latest run has no HTML report; its JSON/JSONL files are in %s", filepath.Dir(file))
		}
	}
	if err == nil {
		err = openBenchURL(reportBenchURL(file))
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		if p.LastRun != "" {
			fmt.Println(file)
		}
		return 1
	}
	fmt.Println("Report opened:", file)
	return 0
}

func runBenchCLI(args []string) int {
	fs := flag.NewFlagSet("bench run", flag.ContinueOnError)
	origin := fs.String("origin", "", "Fred URL (default: last selection or local Weaver k3d)")
	clientOnly := fs.Bool("client-only", false, "Skip trace retrieval (does not change server sampling)")
	mode := fs.String("mode", "", "diagnostic or performance (default: interactive selection)")
	requests := fs.Int("requests", 0, "Measured Fred turns (diagnostic: 10; performance: 1000; max: 50000)")
	concurrency := fs.Int("concurrency", 0, "Concurrent conversations (diagnostic: 1; performance: 10; max: 256)")
	warmup := fs.Int("warmup", 0, "Warm-up turns excluded from statistics (performance: 20; 0 disables)")
	sample := fs.Float64("trace-sample", 0, "Fraction of turns requesting server traces (diagnostic: 1; performance: 0)")
	cleanup := fs.Bool("cleanup", false, "Delete only this run's new conversations after measurement and verification")
	fs.Usage = func() {
		fmt.Fprint(fs.Output(), "bench run - interactive benchmark\n\nUsage:\n  ./bench run [options]\n\nSign in through your browser, select a space and agent, then confirm the run.\nDefaults: diagnostic 10 turns / concurrency 1; performance 1000 / concurrency 10.\nWarm-up is excluded; statistics always cover every measured turn.\nThe agent selects the model. Results: JSON/JSONL; no automatic HTML.\n")
		fmt.Fprintln(fs.Output(), "\nOptions:")
		fs.PrintDefaults()
		fmt.Fprintln(fs.Output(), "\n  -h, --h, -help, --help, help\n        Show this help and exit\n\nExample:\n  ./bench run --mode performance")
	}
	args = benchHelpArguments(fs, args)
	if err := fs.Parse(args); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			return 0
		}
		return 2
	}
	if fs.NArg() != 0 {
		fmt.Fprintln(os.Stderr, "bench: unexpected arguments; see ./bench --help")
		return 2
	}
	options := benchOptions{*mode, *requests, *concurrency, -1, -1, *cleanup}
	fs.Visit(func(f *flag.Flag) {
		switch f.Name {
		case "warmup":
			options.warmup = *warmup
		case "trace-sample":
			options.sampleRate = *sample
		}
	})
	checked := options
	if checked.mode == "" {
		checked.mode = "performance"
	}
	if _, err := checked.resolved(); err != nil {
		fmt.Fprintln(os.Stderr, "bench:", err)
		return 2
	}
	if !term.IsTerminal(int(os.Stdin.Fd())) {
		fmt.Fprintln(os.Stderr, "bench: an interactive terminal is required; use -scenario options for scripts (see README)")
		return 2
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	u := newBenchUI(ctx)
	err := interactiveBench(ctx, u, *origin, *clientOnly, options)
	if errors.Is(err, context.Canceled) || ctx.Err() != nil {
		u.printf("\nStopped.\n")
		return 130
	}
	if err != nil {
		fmt.Fprintf(os.Stderr, "bench: %s\n", terminalText(err.Error()))
		return 1
	}
	return 0
}

func isBenchHelp(arg string) bool {
	switch arg {
	case "-h", "--h", "-help", "--help", "help":
		return true
	}
	return false
}

// Help is handled before terminal checks, state creation or network access.
func benchHelpArguments(fs *flag.FlagSet, args []string) []string {
	if len(args) == 1 && args[0] == "help" {
		args = []string{"--help"}
	}
	for _, arg := range args {
		if isBenchHelp(arg) && arg != "help" {
			fs.SetOutput(os.Stdout)
			break
		}
	}
	return args
}

func interactiveBench(ctx context.Context, u *benchUI, origin string, clientOnly bool, options benchOptions) error {
	u.printf("\n%s  %s\n", u.style("1;36", "FRED BENCH"), "Questions -> Fred agent -> configured model")
	u.printf("Client KPIs = response time, throughput and errors, measured for every question.\n")
	u.printf("%s  10 questions + server traces to understand internal calls.\n", u.style("1;36", "Diagnostic"))
	u.printf("%s  More questions, concurrent conversations; server traces off by default.\n", u.style("1;35", "Performance"))
	if options.mode == "" {
		choice, err := u.choose("What do you want to measure?", []string{"Diagnostic: understand calls", "Performance: measure speed"}, 0)
		if err != nil {
			return err
		}
		options.mode = []string{"diagnostic", "performance"}[choice]
		resolved, err := options.resolved()
		if err != nil {
			return err
		}
		options = resolved
		if options.mode == "performance" {
			u.printf("Each conversation asks up to 10 questions, one after another.\nConcurrency = conversations running at the same time, using your Fred account.\n")
			count, err := u.ask("Measured questions", strconv.Itoa(options.requests))
			if err != nil {
				return err
			}
			options.requests, err = strconv.Atoi(count)
			if err != nil {
				return fmt.Errorf("question count must be an integer")
			}
			options.concurrency = min(options.concurrency, max(1, (options.requests+9)/10))
			parallel, err := u.ask("Concurrent conversations", strconv.Itoa(options.concurrency))
			if err != nil {
				return err
			}
			options.concurrency, err = strconv.Atoi(parallel)
			if err != nil {
				return fmt.Errorf("concurrency must be an integer")
			}
		}
	}
	options, err := options.resolved()
	if err != nil {
		return err
	}
	state, err := benchStateDirectory()
	if err != nil {
		return err
	}
	prefs, err := readBenchPreferences(state)
	if err != nil {
		return err
	}
	if origin == "" {
		origin, err = u.ask("Fred URL", prefs.Origin)
		if err != nil {
			return err
		}
	}
	origin = strings.TrimRight(origin, "/")
	parsed, err := secureBenchURL(origin)
	if err != nil {
		return err
	}
	if parsed.Path != "" {
		return fmt.Errorf("enter the Fred URL without a path")
	}
	cfg := config{Scenario: "conversation", Target: "weaver", Protocol: "sse", FredOrigin: origin, ControlPlanePath: "/control-plane/v1", IdentityMode: "shared", AuthConcurrency: 1, ConcurrencySteps: "1", CreateSession: true, DeleteSession: false, SessionTitle: "Benchmark", Timeout: 120 * time.Second, TraceTurns: true, RequestsPerClient: 10, ReadLimitBytes: 4 << 20}
	cfg = options.apply(cfg)
	client := sseHTTPClient(config{})
	defer client.CloseIdleConnections()
	a := &weaverAdapter{cfg: cfg, http: client}
	var frontend struct {
		Auth benchPublicAuth `json:"user_auth"`
	}
	readCtx, cancel := context.WithTimeout(ctx, 20*time.Second)
	_, err = a.json(readCtx, http.MethodGet, cfg.ControlPlanePath+"/frontend/config", nil, &frontend)
	cancel()
	if err != nil {
		return fmt.Errorf("Fred is unreachable (%s). Check the URL and deployment", classifyError(err))
	}
	identity, err := browserBenchLogin(ctx, frontend.Auth, client, openBenchURL, func(s string) { u.printf("%s\n", s) })
	if err != nil {
		return err
	}
	u.printf("%s\n", u.style("32", "Signed in."))
	cfg.Identity, cfg.Token = identity, identity.access
	if err := prepareIdentityTerms(ctx, cfg, []*benchmarkIdentity{identity}, client, "", nil); err != nil {
		return fmt.Errorf("Fred access: %s. Complete onboarding and accept the terms in Fred, then run ./bench again", classifyError(err))
	}
	catalog := benchCatalog{a, identity}
	prefs.Origin = origin
	var collector *benchCollector
	if !clientOnly && options.sampleRate > 0 {
		u.printf("Checking the collector...\n")
		if origin == "http://weaver.localhost:8088" {
			collector, err = discoverBenchCollector(ctx, readBenchCommand)
		} else {
			err = fmt.Errorf("automatic trace retrieval is supported for local Weaver k3d only")
		}
		if err != nil {
			u.printf("%s %s\n", u.style("33", "Traces unavailable:"), terminalText(err.Error()))
			choice, e := u.choose("Client KPIs still work without server traces", []string{"Exit and set up tracing", "Continue with client timings only"}, 0)
			if e != nil {
				return e
			}
			if choice == 0 {
				return nil
			}
			clientOnly = true
		}
	}
	questions, questionLabel := append([]string(nil), generalBenchQuestions...), "General English · 10 questions"
	for {
		spaces, err := catalog.spaces(ctx)
		if err != nil {
			return err
		}
		if len(spaces) == 0 {
			return fmt.Errorf("no accessible spaces; join a space in Fred first")
		}
		labels, selected := []string{}, 0
		for i, s := range spaces {
			labels = append(labels, s.Label)
			if s.ID == prefs.Space {
				selected = i
			}
		}
		spaceIndex, err := u.choose("Space", labels, selected)
		if err != nil {
			return err
		}
		space := spaces[spaceIndex]
		agents, err := catalog.agents(ctx, space.ID)
		if err != nil {
			return err
		}
		if len(agents) == 0 {
			u.printf("No enabled agents in this space. Choose another space.\n")
			continue
		}
		labels, selected = nil, 0
		for i, agent := range agents {
			labels = append(labels, agent.Name)
			if agent.ID == prefs.Agent {
				selected = i
			}
		}
		labels = append(labels, "Back to spaces")
		index, err := u.choose("Agent", labels, selected)
		if err != nil {
			return err
		}
		if index == len(agents) {
			continue
		}
		agent := agents[index]
		cfg.SpaceID, cfg.AgentInstanceID = space.ID, agent.ID
		prefs.Space, prefs.Agent = space.ID, agent.ID
		if err := saveBenchPreferences(state, prefs); err != nil {
			return err
		}
		for {
			// Resolve Fred's current default/fallback, not only the saved recommendation.
			var preparation weaverPreparation
			if err := catalog.request(ctx, http.MethodPost, "/spaces/"+space.ID+"/agent-instances/"+agent.ID+"/prepare-execution", &preparation); err != nil {
				return fmt.Errorf("cannot read the agent's model: %w", err)
			}
			if (len(preparation.ModelError) > 0 && string(preparation.ModelError) != "null") || preparation.Inference == nil || preparation.Inference.Key.UpstreamID == "" || preparation.Inference.Key.SourceID == "" {
				return fmt.Errorf("this agent has no available model; check its model selection in Fred")
			}
			u.printf("\n%s\n  Space       %s\n  Agent       %s\n", u.style("1", "Ready to run"), terminalText(space.Label), terminalText(agent.Name))
			u.printf("  Model       %s\n  Source      %s\n", terminalText(preparation.Inference.Key.UpstreamID), terminalText(preparation.Inference.Key.SourceID))
			u.printf("  Fred selects this model now; change it in Fred to use a real provider or mock.\n")
			u.printf("  Questions   %s\n  Mode        %s\n  Load        %d measured questions / %d concurrent conversations\n", terminalText(questionLabel), u.style("1;36", options.mode), options.requests, options.concurrency)
			if options.warmup > 0 {
				u.printf("  Warm-up     %d extra questions BEFORE measurement (excluded from KPIs)\n", options.warmup)
			} else {
				u.printf("  Warm-up     None\n")
			}
			u.printf("  KPIs        %s\n", u.style("32", "All measured questions: latency, throughput, errors"))
			switch {
			case options.sampleRate == 0:
				u.printf("  Traces      Off - no server traces requested\n")
			case clientOnly:
				u.printf("  Traces      %.2f%% requested, but retrieval is OFF\n", options.sampleRate*100)
			default:
				u.printf("  Traces      %.2f%% requested; collected after the run\n", options.sampleRate*100)
			}
			if options.sampleRate > 0 {
				u.printf("              Traces explain sampled calls; they do not determine the KPIs.\n")
			}
			u.printf("  Resources   CPU / RAM not collected\n  Files       JSONL observations + JSON summary; no HTML\n")
			if options.cleanup {
				u.printf("  Sessions    Delete this run's conversations after verification\n")
			} else {
				u.printf("  Sessions    Keep in Fred\n")
			}
			choice, err := u.choose("", []string{fmt.Sprintf("Run %d measured questions", options.requests), "Change questions", "Change space or agent", "Exit"}, 0)
			if err != nil {
				return err
			}
			if choice == 3 {
				return nil
			}
			if choice == 2 {
				break
			}
			if choice == 1 {
				q, e := u.choose("Questions", []string{"General English · 10 built-in questions", "Documents · 10 questions about a topic", "Preview selected questions", "Back"}, 0)
				if e != nil {
					return e
				}
				switch q {
				case 0:
					questions, questionLabel = append([]string(nil), generalBenchQuestions...), "General English · 10 questions"
				case 1:
					topic, e := u.ask("Document topic (for example, RAGuard)", "")
					if e != nil {
						return e
					}
					if topic == "" {
						u.printf("The topic cannot be empty.\n")
						continue
					}
					questions, questionLabel = documentBenchQuestions(topic), "Documents · "+topic+" · 10 questions"
				case 2:
					for i, q := range questions {
						u.printf("  %02d. %s\n", i+1, terminalText(q))
					}
				}
				continue
			}
			cfg.Questions = questions
			if err := checkBenchStorage(state); err != nil {
				return err
			}
			runDir, err := os.MkdirTemp(state, "run-"+time.Now().Format("20060102-150405")+"-")
			if err != nil {
				return err
			}
			cfg.RawReportPath = filepath.Join(runDir, "conversation.jsonl")
			cfg.JSONReportPath = filepath.Join(runDir, "summary.json")
			if err := executeInteractiveBench(ctx, u, cfg, collector, runDir); err != nil {
				return err
			}
			prefs.LastRun = filepath.Base(runDir)
			if err := saveBenchPreferences(state, prefs); err != nil {
				return err
			}
			if ctx.Err() != nil {
				return ctx.Err()
			}
			action, err := u.choose("Next", []string{"Run the same questions again", "Choose another agent", "Exit"}, 2)
			if err != nil {
				return err
			}
			if action == 2 {
				return nil
			}
			if action == 1 {
				break
			}
		}
	}
}

func runBenchProgress(ctx context.Context, u *benchUI, cfg config, dir string) (scenarioReport, error) {
	planned := len(cfg.Questions)
	if cfg.TotalTurns > 0 {
		planned = cfg.TotalTurns
	}
	started := time.Now()
	rows := make(chan scenarioTurn, 100)
	observe := cfg.ObserveTurn
	cfg.ObserveTurn = func(row scenarioTurn) {
		if observe != nil {
			observe(row)
		}
		rows <- row
	}
	type outcome struct {
		report scenarioReport
		err    error
	}
	done := make(chan outcome, 1)
	go func() { report, err := runScenario(ctx, cfg); done <- outcome{report, err} }()
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()
	completed, success := 0, 0
	show := func(row scenarioTurn) {
		completed++
		status, color := "FAILED", "31"
		if row.Outcome == "success" {
			status, color = "OK", "32"
			success++
		}
		if cfg.Mode == "performance" {
			return
		}
		if u.ansi {
			u.printf("\r\x1b[2K")
		}
		u.printf("  %02d/%02d  %s  %s\n", completed, planned, u.style(color, status), benchTurnDuration(row))
		if row.Error != "" {
			u.printf("         %s\n", terminalText(row.Error))
		}
	}
	u.printf("\nQuestion 1/%d in progress · Ctrl+C to stop\n", planned)
	var result outcome
running:
	for {
		select {
		case row := <-rows:
			show(row)
		case <-ticker.C:
			if u.ansi {
				u.printf("\r\x1b[2K%d/%d completed · %d successful · %s elapsed", completed, planned, success, time.Since(started).Round(time.Second))
			}
		case result = <-done:
			for len(rows) > 0 {
				show(<-rows)
			}
			break running
		}
	}
	if u.ansi {
		u.printf("\r\x1b[2K")
	}
	if result.err != nil {
		return result.report, fmt.Errorf("benchmark interrupted (%s). Results saved: %s", classifyError(result.err), dir)
	}
	u.printf("\nSuccessful questions: %d/%d · %s\n", success, planned, time.Since(started).Round(time.Second))
	return result.report, nil
}

func executeInteractiveBench(ctx context.Context, u *benchUI, cfg config, collector *benchCollector, dir string) error {
	defer printBenchFiles(u, dir)
	var cleanup []func() int
	// Warm-up deletion is deferred until after measured traffic, so background
	// erasure cannot compete with the measured load. Always run on early exit too.
	defer func() {
		if len(cleanup) == 0 {
			return
		}
		failures := 0
		for _, close := range cleanup {
			failures += close()
		}
		u.printf("Warm-up cleanup: %d requested, %d errors (server deletion is asynchronous)\n", len(cleanup), failures)
		data, _ := json.Marshal(map[string]int{"requested": len(cleanup), "errors": failures})
		if err := os.WriteFile(filepath.Join(dir, "warmup", "cleanup.json"), data, 0600); err != nil {
			u.printf("Could not save warm-up cleanup receipt.\n")
		}
	}()
	if cfg.WarmupTurns > 0 {
		warmDir := filepath.Join(dir, "warmup")
		if err := os.Mkdir(warmDir, 0700); err != nil {
			return err
		}
		warm := cfg
		warm.TotalTurns = cfg.WarmupTurns
		warm.WarmupTurns = 0
		rate := 0.0
		warm.TraceSampleRate = &rate
		concurrency, _ := strconv.Atoi(cfg.ConcurrencySteps)
		warm.ConcurrencySteps = strconv.Itoa(min(concurrency, (warm.TotalTurns+len(cfg.Questions)-1)/len(cfg.Questions)))
		warm.RawReportPath = filepath.Join(warmDir, "conversation.jsonl")
		warm.JSONReportPath = filepath.Join(warmDir, "summary.json")
		warm.DeferCleanup = func(close func() int) { cleanup = append(cleanup, close) }
		u.printf("\nWarm-up - extra questions, excluded from the measured results\n")
		result, err := runBenchProgress(ctx, u, warm, warmDir)
		if err != nil {
			return err
		}
		if result.Outcome != "OK" {
			return fmt.Errorf("warm-up failed; measured run not started. Results: %s", warmDir)
		}
	}
	u.printf("\n%s\n", u.style("1;36", "Measured run - collecting client KPIs"))
	sampled := 0
	cfg.ObserveTurn = func(row scenarioTurn) {
		if row.TraceID != "" {
			sampled++
		}
	}
	report, err := runBenchProgress(ctx, u, cfg, dir)
	if err != nil {
		return err
	}
	printBenchSummary(u, report)
	if collector != nil && sampled > 0 && ctx.Err() == nil {
		u.printf("Retrieving traces (up to 30 seconds)...\n")
		matched, _, err := collector.collect(ctx, dir)
		u.printf("Server traces found for %d/%d sampled questions.\n", matched, sampled)
		if err != nil {
			u.printf("%s %s\n", u.style("33", "Partial collection:"), terminalText(err.Error()))
		}
		u.printf("Any saved trace snapshot is listed below; coverage may be partial.\n")
	}

	return nil
}

func benchTurnDuration(row scenarioTurn) string {
	if row.StreamClosedAt != nil {
		return row.StreamClosedAt.Sub(row.StartedAt).Round(time.Millisecond).String()
	}
	return "duration unavailable"
}

// Keep the terminal recap independent of the optional HTML renderer.
func printBenchSummary(u *benchUI, report scenarioReport) {
	color := "32"
	if report.Outcome != "OK" {
		color = "33"
	}
	u.printf("\n%s  %s\n", u.style("1;"+color, "RESULT"), report.Outcome)
	for _, step := range report.Steps {
		u.printf("  Questions   %d/%d successful | %d errors (%d timeouts) | %d not started\n", step.Success, step.Planned, step.Errors, step.Timeouts, step.NotStarted)
		if step.All.TotalEOF.Count > 0 {
			u.printf("  Full reply  Mean %.2f ms | P95 %.2f ms | P99 %.2f ms\n", step.All.TotalEOF.Mean, step.All.TotalEOF.P95, step.All.TotalEOF.P99)
		} else {
			u.printf("  Full reply  Not measured\n")
		}
		if step.All.ExecutionFirstText.Count > 0 {
			u.printf("  First text  Mean %.2f ms from execution start (excludes preparation)\n", step.All.ExecutionFirstText.Mean)
		}
		if step.LoadElapsedMS > 0 {
			u.printf("  Throughput  %.2f successful questions/s | %.2f s measured load\n", step.SuccessfulTurnsPerSecond, step.LoadElapsedMS/1000)
		}
		u.printf("  Checks      %d conversation histories verified | %d history/cleanup issues\n", step.HistoryVerified, step.HistoryErrors+step.HistoryUnsupported+step.CleanupErrors)
	}
	if report.Error != "" {
		u.printf("  Error       %s\n", terminalText(report.Error))
	}
	u.printf("  Latencies cover successful measured questions; warm-up is excluded.\n  P95: 95%% of those responses finished within this time. CPU/RAM not measured.\n")
}

func printBenchFiles(u *benchUI, dir string) {
	u.printf("\n%s\n", u.style("1;36", "SAVED FILES"))
	for _, item := range []struct{ name, description string }{
		{"conversation.jsonl", "Measured observations: timings, outcomes and checks"},
		{"summary.json", "Aggregated client KPIs"},
		{"traces.otlp.jsonl", "Server trace snapshot, separate from client KPIs"},
		{"warmup/conversation.jsonl", "Warm-up observations, excluded from measured KPIs"},
	} {
		file := filepath.Join(dir, item.name)
		if info, err := os.Stat(file); err == nil && info.Mode().IsRegular() && info.Size() > 0 {
			u.printf("  %s\n    %s\n", item.description, terminalText(file))
		}
	}
}

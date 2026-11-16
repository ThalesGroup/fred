package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"
)

type config struct {
	PrepareOnly           bool
	AcceptTestTerms       string
	Scenario              string
	TraceTurns            bool
	CredentialFile        string
	ConcurrencySteps      string
	IdentityMode          string
	AuthConcurrency       int
	MockProfile           string
	RuntimeDecoder        func([]byte) (streamEvent, error)
	Target                string
	FredOrigin            string
	ControlPlanePath      string
	SpaceID               string
	ExplicitFlags         []string
	RawReportPath         string
	URL                   string
	Token                 string
	TokenInQuery          bool
	AgentID               string
	AgentUUID             string
	AgentCreateURL        string
	EnsureV2DefinitionRef string
	EnsureV2ProfileID     string
	EnsureAgentName       string
	DeleteCreatedAgent    bool
	Message               string
	SessionID             string
	SessionURL            string
	SessionTitle          string
	CreateSession         bool
	PrepareSessions       bool
	PrepareConcurrency    int
	DeleteSession         bool
	Clients               int
	Requests              int
	RequestsPerClient     int
	Timeout               time.Duration
	InsecureTLS           bool
	AllowEmptyTok         bool
	DebugEvents           bool
	RampDuration          time.Duration
	ReadLimitBytes        int64
	DocumentLibraryIDs    []string
	DocumentUIDs          []string
	SearchPolicy          string
	SearchRagScope        string
	IncludeSessionScope   *bool
	IncludeCorpusScope    *bool
	Protocol              string // "ws" or "sse"
	SSEUserID             string
	SSETeamID             string
	AgentInstanceID       string
	JSONReportPath        string
}

func main() { os.Exit(run()) }

func run() int {
	if len(os.Args) > 1 && os.Args[1] == "report" {
		return runHTMLReportCLI(os.Args[2:])
	}
	cfg := parseFlags()
	if cfg.TraceTurns && (cfg.Scenario != "conversation" || cfg.PrepareOnly) {
		fmt.Fprintln(os.Stderr, "trace-turns requires -scenario=conversation (not prepare-only)")
		return 2
	}
	if cfg.PrepareOnly {
		return runTermsCLI(cfg)
	}
	if cfg.AcceptTestTerms != "" {
		fmt.Fprintln(os.Stderr, "accept-test-terms requires prepare-only")
		return 2
	}
	if cfg.Scenario != "" {
		return runScenarioCLI(cfg)
	}
	if cfg.CredentialFile != "" || cfg.ConcurrencySteps != "" {
		fmt.Fprintln(os.Stderr, "credential-file and concurrency-steps require -scenario=conversation")
		return 2
	}
	if err := validateConfig(cfg); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 2
	}
	if cfg.Clients <= 0 {
		fmt.Fprintln(os.Stderr, "clients must be > 0")
		return 2
	}
	perClientMode := cfg.RequestsPerClient > 0
	if cfg.Timeout <= 0 || cfg.RequestsPerClient < 0 || cfg.RampDuration < 0 {
		fmt.Fprintln(os.Stderr, "timeout must be positive; requests-per-client and ramp-duration must be nonnegative")
		return 2
	}
	if !perClientMode && cfg.Requests <= 0 {
		fmt.Fprintln(os.Stderr, "requests must be > 0")
		return 2
	}

	if cfg.Token == "" && !cfg.AllowEmptyTok && !urlHasToken(cfg.URL) {
		fmt.Fprintln(os.Stderr, "token is required (use -token or include token query param)")
		return 2
	}

	start := time.Now()
	if shouldEnsureV2Agent(cfg) {
		createdAgentID, err := ensureV2Agent(cfg)
		if err != nil {
			fmt.Fprintf(os.Stderr, "ensure v2 agent failed: %s\n", classifyError(err))
			return 2
		}
		cfg.AgentID = createdAgentID
		if cfg.DeleteCreatedAgent {
			defer func() {
				ctx, cancel := context.WithTimeout(context.Background(), cfg.Timeout)
				if err := deleteAgent(ctx, cfg, createdAgentID); err != nil {
					fmt.Fprintf(os.Stderr, "delete agent failed: %s\n", classifyError(err))
				}
				cancel()
			}()
		}
	}
	totalRequests := cfg.Requests
	effectiveClients := cfg.Clients
	if perClientMode {
		totalRequests = cfg.Clients * cfg.RequestsPerClient
	} else if cfg.Requests < cfg.Clients {
		effectiveClients = cfg.Requests
	}
	printConfigRecap(cfg, perClientMode, totalRequests, effectiveClients)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	var open func(context.Context, int) (conversation, error)
	var closeAdapter func()
	var weaver *weaverAdapter
	if cfg.Target == "weaver" {
		weaver = newWeaverAdapter(cfg)
		open, closeAdapter = weaver.Open, weaver.Close
	} else {
		adapter := newSwiftAdapter(cfg)
		if err := adapter.Prepare(ctx); err != nil {
			stop()
			adapter.Close()
			fmt.Fprintln(os.Stderr, "prepare sessions failed")
			return 2
		}
		open, closeAdapter = adapter.Open, adapter.Close
	}
	defer closeAdapter()
	if !perClientMode {
		cfg.Clients = effectiveClients
	}
	results := runLoad(ctx, loadPlan{
		Clients: effectiveClients, Requests: cfg.Requests, Turns: cfg.RequestsPerClient,
		Ramp: cfg.RampDuration, Timeout: cfg.Timeout,
	}, open)
	stop()
	closeAdapter()
	elapsed := time.Since(start)
	exitCode := 0
	cleanupErrors := 0
	if weaver != nil {
		cleanupErrors = int(weaver.cleanupErrors.Load())
		if cleanupErrors > 0 {
			fmt.Fprintf(os.Stderr, "Weaver session cleanup failed: %d deletion requests; retained conversations require operator follow-up\n", cleanupErrors)
			exitCode = 1
		}
	}
	if cfg.RawReportPath != "" {
		if err := writeRawReport(cfg.RawReportPath, cfg, results); err != nil {
			fmt.Fprintln(os.Stderr, "write raw report failed:", err)
			exitCode = 1
		}
	}

	var durations []time.Duration
	var errorSamples []string
	errorCount := 0
	for _, res := range results {
		if res.Err != nil {
			errorCount++
			if len(errorSamples) < 5 {
				errorSamples = append(errorSamples, res.Err.Error())
			}
			continue
		}
		durations = append(durations, res.Duration)
	}

	report := printSummary(cfg, totalRequests, durations, errorCount, errorSamples, elapsed, cleanupErrors)
	if cfg.JSONReportPath != "" {
		if err := writeJSONReport(cfg.JSONReportPath, report, cfg.RawReportPath); err != nil {
			fmt.Fprintf(os.Stderr, "write JSON report: %v\n", err)
			exitCode = 1
		} else {
			fmt.Printf("JSON report: %s\n", cfg.JSONReportPath)
		}
	}
	return exitCode
}

// parseFlags exists to let the benchmark exercise plain chat and public RAG
// flows from the same binary. Use the runtime-context flags below to scope
// Rico's retrieval behaviour without changing the code.
func parseFlags() config {
	flag.Usage = func() {
		fmt.Fprintf(flag.CommandLine.Output(), "Usage: %s [options]\n\n", os.Args[0])
		flag.PrintDefaults()
		fmt.Fprintln(flag.CommandLine.Output(), "\nExample:")
		fmt.Fprintln(flag.CommandLine.Output(), "  make run ARGS='-url ws://localhost:8000/agentic/v1/chatbot/query/ws -token $TOKEN -clients 100 -requests 100'")
	}

	targetFlag := flag.String("target", "swift", "Backend target: swift or weaver")
	scenarioFlag := flag.String("scenario", "", "Opt-in conversation scenario (managed SSE, explicit concurrency steps)")
	traceTurnsFlag := flag.Bool("trace-turns", false, "Opt-in W3C trace correlation per scenario turn; no telemetry export by the client")
	prepareOnlyFlag := flag.Bool("prepare-only", false, "Check synthetic identities and terms without creating sessions or running load")
	acceptTermsFlag := flag.String("accept-test-terms", "", "Explicit prepare-only terms acceptance: current (synthetic bench-* accounts only)")
	credentialsFlag := flag.String("credential-file", "", "Private factory credentials JSON; scenario only, never put credentials in argv")
	stepsFlag := flag.String("concurrency-steps", "", "Explicit sequential concurrency levels, e.g. 1,10,50 (scenario only)")
	identityFlag := flag.String("identity-mode", "per-conversation", "Scenario identities: per-conversation or shared")
	authConcurrencyFlag := flag.Int("auth-concurrency", 8, "Maximum concurrent initial OIDC logins")
	mockProfileFlag := flag.String("mock-profile", "reference", "Expected opt-in mock profile: reference or streaming")
	fredOriginFlag := flag.String("fred-origin", "", "Weaver public HTTP(S) origin shared by Control Plane and runtime")
	controlPlanePathFlag := flag.String("control-plane-path", "/control-plane/v1", "Weaver Control Plane public path on fred-origin")
	spaceIDFlag := flag.String("space-id", "", "Weaver space UUID")
	rawReportFlag := flag.String("raw-report", "", "Explicit local JSONL export of per-turn measurements (Swift v1 / Weaver v2 schema)")
	protocolFlag := flag.String("protocol", "ws", "Transport protocol: ws (agentic-backend) or sse (fred-runtime)")
	sseUserIDFlag := flag.String("sse-user-id", "bench", "User ID injected into runtime_context for SSE requests (keys sessions per user)")
	sseTeamIDFlag := flag.String("sse-team-id", "", "Team ID injected into runtime_context for SSE requests (optional for direct mode, required for managed mode)")
	agentInstanceIDFlag := flag.String("agent-instance-id", "", "Managed agent instance UUID (SSE; Swift needs sse-team-id, Weaver needs space-id)")
	jsonReportFlag := flag.String("json-report", "", "Optional path for a machine-readable benchmark summary (never contains token or prompt)")
	urlFlag := flag.String("url", "ws://localhost:8000/agentic/v1/chatbot/query/ws", "Endpoint URL (ws/wss for protocol=ws, http/https for protocol=sse)")
	tokenFlag := flag.String("token", "", "Bearer token (or set AGENTIC_TOKEN)")
	tokenInQuery := flag.Bool("token-in-query", false, "Send token as ?token= query param")
	agentFlag := flag.String("agent", "Georges", "Agent ID (configuration.yaml for ws, fred_sdk agent_id for sse)")
	agentUUIDFlag := flag.String("agent-uuid", "", "Existing agent UUID to reuse for the benchmark; skips auto-creation when set")
	agentCreateURLFlag := flag.String("agent-create-url", "", "HTTP v2 agent creation endpoint URL override (optional)")
	ensureV2DefinitionRefFlag := flag.String("ensure-v2-definition-ref", "", "Optionally create a v2 agent from a definition_ref before benchmarking, e.g. v2.react.rag_expert")
	ensureV2ProfileIDFlag := flag.String("ensure-v2-profile-id", "", "Optionally create a Basic ReAct v2 agent from a react profile before benchmarking, e.g. rag_expert")
	ensureAgentNameFlag := flag.String("ensure-agent-name", "Bench RAG Expert", "Display name for an agent created automatically by the benchmark")
	deleteCreatedAgentFlag := flag.Bool("delete-created-agent", false, "Delete the automatically created v2 agent after the benchmark run")
	messageFlag := flag.String("message", "Hello", "Prompt message")
	sessionFlag := flag.String("session", "", "Session ID (optional)")
	sessionURLFlag := flag.String("session-url", "", "HTTP session endpoint URL (optional)")
	sessionTitleFlag := flag.String("session-title", "Benchmark", "Session title to skip auto-title")
	createSessionFlag := flag.Bool("create-session", true, "Create a session before asking (when no session is provided)")
	prepareSessionsFlag := flag.Bool("prepare-sessions", false, "Pre-create one session per client before measuring")
	prepareConcurrencyFlag := flag.Int("prepare-concurrency", 20, "Concurrent session creates/deletes during preparation/cleanup")
	deleteSessionFlag := flag.Bool("delete-session", true, "Delete sessions created by the benchmark when done")
	rampDurationFlag := flag.Duration("ramp-duration", 10*time.Second, "Optional stagger for client start (e.g. 10s spreads clients evenly over 10 seconds)")
	clientsFlag := flag.Int("clients", 150, "Concurrent clients")
	requestsFlag := flag.Int("requests", 0, "Total requests (defaults to clients)")
	requestsPerClientFlag := flag.Int("requests-per-client", 10, "Requests per client (sequential mode)")
	timeoutFlag := flag.Duration("timeout", 90*time.Second, "Timeout per request")
	readLimitBytesFlag := flag.Int64("read-limit-bytes", 4*1024*1024, "Maximum WebSocket message size accepted by the benchmark client before failing the read")
	insecureFlag := flag.Bool("insecure", false, "Skip TLS verification for wss://")
	allowEmptyTok := flag.Bool("allow-empty-token", false, "Allow missing token (not recommended)")
	debugEvents := flag.Bool("debug-events", false, "Print WebSocket event receipt notifications (no payload content)")
	documentLibraryIDsFlag := flag.String("document-library-ids", "", "Optional comma-separated document library ids for runtime_context.selected_document_libraries_ids")
	documentUIDsFlag := flag.String("document-uids", "", "Optional comma-separated document uids for runtime_context.selected_document_uids")
	searchPolicyFlag := flag.String("search-policy", "", "Optional runtime_context.search_policy, e.g. semantic, hybrid, strict")
	searchRagScopeFlag := flag.String("search-rag-scope", "", "Optional runtime_context.search_rag_scope: corpus_only, hybrid, general_only")
	includeSessionScopeFlag := flag.String("include-session-scope", "", "Optional runtime_context.include_session_scope: true or false")
	includeCorpusScopeFlag := flag.String("include-corpus-scope", "", "Optional runtime_context.include_corpus_scope: true or false")

	flag.Parse()
	var explicitFlags []string
	flag.Visit(func(f *flag.Flag) { explicitFlags = append(explicitFlags, f.Name) })
	target := strings.ToLower(strings.TrimSpace(*targetFlag))
	// Swift defaults are not Weaver options. Explicit incompatible flags are
	// still rejected, even when their value equals a historical default.
	if target == "weaver" {
		*urlFlag, *agentFlag, *ensureAgentNameFlag, *sseUserIDFlag = "", "", "", ""
		*agentInstanceIDFlag = strings.ToLower(*agentInstanceIDFlag)
		*sessionFlag = strings.ToLower(*sessionFlag)
	}

	token := strings.TrimSpace(*tokenFlag)
	if token == "" {
		token = strings.TrimSpace(os.Getenv("AGENTIC_TOKEN"))
	}
	if target != "weaver" && *scenarioFlag == "" && token == "" && !*allowEmptyTok && !urlHasToken(*urlFlag) {
		token = "fake-token"
	}

	requests := *requestsFlag
	if *requestsPerClientFlag == 0 && requests == 0 {
		requests = *clientsFlag
	}

	agentUUID := strings.TrimSpace(*agentUUIDFlag)
	agentID := strings.TrimSpace(*agentFlag)
	if agentUUID != "" {
		agentID = agentUUID
	}

	return config{
		TraceTurns:  *traceTurnsFlag,
		PrepareOnly: *prepareOnlyFlag, AcceptTestTerms: *acceptTermsFlag,
		Scenario: *scenarioFlag, CredentialFile: *credentialsFlag, ConcurrencySteps: *stepsFlag,
		IdentityMode: *identityFlag, AuthConcurrency: *authConcurrencyFlag, MockProfile: *mockProfileFlag,
		Target:                target,
		FredOrigin:            strings.TrimSpace(*fredOriginFlag),
		ControlPlanePath:      strings.TrimSpace(*controlPlanePathFlag),
		SpaceID:               strings.ToLower(strings.TrimSpace(*spaceIDFlag)),
		ExplicitFlags:         explicitFlags,
		RawReportPath:         strings.TrimSpace(*rawReportFlag),
		URL:                   strings.TrimSpace(*urlFlag),
		Token:                 token,
		TokenInQuery:          *tokenInQuery,
		AgentID:               agentID,
		AgentUUID:             agentUUID,
		AgentCreateURL:        strings.TrimSpace(*agentCreateURLFlag),
		EnsureV2DefinitionRef: strings.TrimSpace(*ensureV2DefinitionRefFlag),
		EnsureV2ProfileID:     strings.TrimSpace(*ensureV2ProfileIDFlag),
		EnsureAgentName:       strings.TrimSpace(*ensureAgentNameFlag),
		DeleteCreatedAgent:    *deleteCreatedAgentFlag,
		Message:               *messageFlag,
		SessionID:             strings.TrimSpace(*sessionFlag),
		SessionURL:            strings.TrimSpace(*sessionURLFlag),
		SessionTitle:          strings.TrimSpace(*sessionTitleFlag),
		CreateSession:         *createSessionFlag,
		PrepareSessions:       *prepareSessionsFlag,
		PrepareConcurrency:    *prepareConcurrencyFlag,
		DeleteSession:         *deleteSessionFlag,
		Clients:               *clientsFlag,
		Requests:              requests,
		RequestsPerClient:     *requestsPerClientFlag,
		Timeout:               *timeoutFlag,
		ReadLimitBytes:        *readLimitBytesFlag,
		InsecureTLS:           *insecureFlag,
		AllowEmptyTok:         *allowEmptyTok,
		DebugEvents:           *debugEvents,
		RampDuration:          *rampDurationFlag,
		DocumentLibraryIDs:    parseCSVFlag(*documentLibraryIDsFlag),
		DocumentUIDs:          parseCSVFlag(*documentUIDsFlag),
		SearchPolicy:          strings.TrimSpace(*searchPolicyFlag),
		SearchRagScope:        strings.TrimSpace(*searchRagScopeFlag),
		IncludeSessionScope:   parseOptionalBoolFlag(*includeSessionScopeFlag),
		IncludeCorpusScope:    parseOptionalBoolFlag(*includeCorpusScopeFlag),
		Protocol:              strings.ToLower(strings.TrimSpace(*protocolFlag)),
		SSEUserID:             strings.TrimSpace(*sseUserIDFlag),
		SSETeamID:             strings.TrimSpace(*sseTeamIDFlag),
		AgentInstanceID:       strings.TrimSpace(*agentInstanceIDFlag),
		JSONReportPath:        strings.TrimSpace(*jsonReportFlag),
	}
}

// validateConfig rejects unsupported target/transport combinations before any network work.
func validateConfig(cfg config) error {
	if cfg.Target != "" && cfg.Target != "swift" && cfg.Target != "weaver" {
		return fmt.Errorf("unknown target")
	}
	if cfg.Protocol != "ws" && cfg.Protocol != "sse" {
		return fmt.Errorf("protocol must be ws or sse")
	}
	if cfg.RawReportPath != "" && cfg.JSONReportPath != "" {
		raw, rawErr := filepath.Abs(cfg.RawReportPath)
		summary, summaryErr := filepath.Abs(cfg.JSONReportPath)
		if rawErr != nil || summaryErr != nil || raw == summary {
			return fmt.Errorf("raw-report and json-report must use different valid paths")
		}
	}

	if cfg.Target == "weaver" {
		return validateWeaverConfig(cfg)
	}
	if cfg.FredOrigin != "" || cfg.SpaceID != "" {
		return fmt.Errorf("-fred-origin and -space-id require -target=weaver")
	}
	for _, name := range cfg.ExplicitFlags {
		if name == "control-plane-path" {
			return fmt.Errorf("-control-plane-path requires -target=weaver")
		}
	}
	if cfg.AgentInstanceID == "" {
		return nil
	}
	if cfg.Protocol != "sse" {
		return fmt.Errorf("-agent-instance-id requires -protocol=sse (got %q)", cfg.Protocol)
	}
	if cfg.SSETeamID == "" {
		return fmt.Errorf("-agent-instance-id (managed mode) requires -sse-team-id")
	}
	return nil
}

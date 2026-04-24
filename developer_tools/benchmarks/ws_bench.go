package main

import (
	"context"
	"crypto/rand"
	"crypto/tls"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"math"
	"net/http"
	"net/url"
	"os"
	"sort"
	"strings"
	"sync"
	"time"

	"nhooyr.io/websocket"
)

const (
	colorReset  = "\033[0m"
	colorBold   = "\033[1m"
	colorDim    = "\033[2m"
	colorRed    = "\033[31m"
	colorGreen  = "\033[32m"
	colorYellow = "\033[33m"
	colorCyan   = "\033[36m"
)

type askPayload struct {
	Type             string                 `json:"type,omitempty"`
	SessionID        string                 `json:"session_id,omitempty"`
	Message          string                 `json:"message"`
	AgentID          string                 `json:"agent_id,omitempty"`
	RuntimeContext   *runtimeContextPayload `json:"runtime_context,omitempty"`
	ClientExchangeID string                 `json:"client_exchange_id,omitempty"`
}

type runtimeContextPayload struct {
	SessionID                    string   `json:"session_id,omitempty"`
	SelectedDocumentLibrariesIDs []string `json:"selected_document_libraries_ids,omitempty"`
	SelectedDocumentUIDs         []string `json:"selected_document_uids,omitempty"`
	SearchPolicy                 string   `json:"search_policy,omitempty"`
	SearchRagScope               string   `json:"search_rag_scope,omitempty"`
	IncludeSessionScope          *bool    `json:"include_session_scope,omitempty"`
	IncludeCorpusScope           *bool    `json:"include_corpus_scope,omitempty"`
}

type eventEnvelope struct {
	Type string `json:"type"`
}

type errorEvent struct {
	Type    string `json:"type"`
	Content string `json:"content"`
}

type createV2AgentPayload struct {
	Name          string `json:"name"`
	DefinitionRef string `json:"definition_ref,omitempty"`
	ProfileID     string `json:"profile_id,omitempty"`
}

type createdAgentResponse struct {
	ID string `json:"id"`
}

type config struct {
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
}

type result struct {
	Duration time.Duration
	Err      error
}

func main() {
	cfg := parseFlags()
	if cfg.Clients <= 0 {
		fmt.Fprintln(os.Stderr, "clients must be > 0")
		os.Exit(2)
	}
	perClientMode := cfg.RequestsPerClient > 0
	if perClientMode {
		if cfg.RequestsPerClient <= 0 {
			fmt.Fprintln(os.Stderr, "requests-per-client must be > 0")
			os.Exit(2)
		}
	} else if cfg.Requests <= 0 {
		fmt.Fprintln(os.Stderr, "requests must be > 0")
		os.Exit(2)
	}

	if cfg.Token == "" && !cfg.AllowEmptyTok && !urlHasToken(cfg.URL) {
		fmt.Fprintln(os.Stderr, "token is required (use -token or include token query param)")
		os.Exit(2)
	}

	start := time.Now()
	if shouldEnsureV2Agent(cfg) {
		createdAgentID, err := ensureV2Agent(cfg)
		if err != nil {
			fmt.Fprintf(os.Stderr, "ensure v2 agent failed: %v\n", err)
			os.Exit(2)
		}
		cfg.AgentID = createdAgentID
		if cfg.DeleteCreatedAgent {
			defer func() {
				ctx, cancel := context.WithTimeout(context.Background(), cfg.Timeout)
				if err := deleteAgent(ctx, cfg, createdAgentID); err != nil {
					fmt.Fprintf(os.Stderr, "delete agent failed: %v\n", err)
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

	var results chan result
	var wg sync.WaitGroup

	if perClientMode {
		results = make(chan result, totalRequests)
		sessionIDs := []string{}
		if cfg.SessionID != "" {
			sessionIDs = make([]string, cfg.Clients)
			for i := 0; i < cfg.Clients; i++ {
				sessionIDs[i] = cfg.SessionID
			}
		} else if cfg.CreateSession && cfg.PrepareSessions {
			ids, err := createSessions(cfg, cfg.Clients)
			if err != nil {
				fmt.Fprintf(os.Stderr, "prepare sessions failed: %v\n", err)
				os.Exit(2)
			}
			sessionIDs = ids
		}

		// Optional ramp-up: spread client starts evenly over RampDuration
		delayPerClient := time.Duration(0)
		if cfg.RampDuration > 0 && cfg.Clients > 1 {
			delayPerClient = cfg.RampDuration / time.Duration(cfg.Clients-1)
		}
		for i := 0; i < cfg.Clients; i++ {
			wg.Add(1)
			sessionID := ""
			if len(sessionIDs) > 0 {
				sessionID = sessionIDs[i]
			}
			startDelay := delayPerClient * time.Duration(i)
			go func(id string, d time.Duration) {
				defer wg.Done()
				if d > 0 {
					time.Sleep(d)
				}
				resList := runClientPersistent(cfg, id)
				for _, r := range resList {
					results <- r
				}
			}(sessionID, startDelay)
		}
		wg.Wait()
		close(results)
		if cfg.DeleteSession && cfg.CreateSession && cfg.PrepareSessions && cfg.SessionID == "" {
			deleteSessions(cfg, sessionIDs)
		}
	} else {
		cfg.Clients = effectiveClients
		results = make(chan result, totalRequests)
		jobs := make(chan int)
		for i := 0; i < cfg.Clients; i++ {
			wg.Add(1)
			go func() {
				defer wg.Done()
				for range jobs {
					res := runOnce(cfg)
					results <- res
				}
			}()
		}
		for i := 0; i < cfg.Requests; i++ {
			jobs <- i
		}
		close(jobs)
		wg.Wait()
		close(results)
	}

	var durations []time.Duration
	var errorSamples []string
	errorCount := 0
	for res := range results {
		if res.Err != nil {
			errorCount++
			if len(errorSamples) < 5 {
				errorSamples = append(errorSamples, res.Err.Error())
			}
			continue
		}
		durations = append(durations, res.Duration)
	}

	elapsed := time.Since(start)
	printSummary(cfg, totalRequests, durations, errorCount, errorSamples, elapsed)
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

	urlFlag := flag.String("url", "ws://localhost:8000/agentic/v1/chatbot/query/ws", "WebSocket URL")
	tokenFlag := flag.String("token", "", "Bearer token (or set AGENTIC_TOKEN)")
	tokenInQuery := flag.Bool("token-in-query", false, "Send token as ?token= query param")
	agentFlag := flag.String("agent", "Georges", "Agent ID (matches configuration.yaml)")
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
	debugEvents := flag.Bool("debug-events", false, "Print every WebSocket event payload")
	documentLibraryIDsFlag := flag.String("document-library-ids", "", "Optional comma-separated document library ids for runtime_context.selected_document_libraries_ids")
	documentUIDsFlag := flag.String("document-uids", "", "Optional comma-separated document uids for runtime_context.selected_document_uids")
	searchPolicyFlag := flag.String("search-policy", "", "Optional runtime_context.search_policy, e.g. semantic, hybrid, strict")
	searchRagScopeFlag := flag.String("search-rag-scope", "", "Optional runtime_context.search_rag_scope: corpus_only, hybrid, general_only")
	includeSessionScopeFlag := flag.String("include-session-scope", "", "Optional runtime_context.include_session_scope: true or false")
	includeCorpusScopeFlag := flag.String("include-corpus-scope", "", "Optional runtime_context.include_corpus_scope: true or false")

	flag.Parse()

	token := strings.TrimSpace(*tokenFlag)
	if token == "" {
		token = strings.TrimSpace(os.Getenv("AGENTIC_TOKEN"))
	}
	if token == "" && !*allowEmptyTok && !urlHasToken(*urlFlag) {
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
	}
}

func runOnce(cfg config) result {
	return runOnceWithSession(cfg, cfg.SessionID)
}

// runClientPersistent keeps a single WebSocket open for all requests of one client
// and optionally deletes the session at the end if it was created here.
func runClientPersistent(cfg config, sessionID string) []result {
	results := make([]result, 0, maxInt(1, cfg.RequestsPerClient))

	createdByBench := false
	ctx, cancel := context.WithTimeout(context.Background(), cfg.Timeout*time.Duration(maxInt(1, cfg.RequestsPerClient)))
	defer cancel()

	if sessionID == "" && cfg.CreateSession {
		createdID, err := createSession(ctx, cfg)
		if err != nil {
			results = append(results, result{Err: err})
			return results
		}
		sessionID = createdID
		createdByBench = true
	}

	urlStr, err := buildURL(cfg.URL, cfg.Token, cfg.TokenInQuery)
	if err != nil {
		results = append(results, result{Err: err})
		return results
	}

	dialOpts := &websocket.DialOptions{CompressionMode: websocket.CompressionDisabled}
	if cfg.Token != "" && !cfg.TokenInQuery {
		dialOpts.HTTPHeader = http.Header{"Authorization": []string{"Bearer " + cfg.Token}}
	}
	if cfg.InsecureTLS {
		dialOpts.HTTPClient = &http.Client{
			Transport: &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}},
		}
	}

	conn, _, err := websocket.Dial(ctx, urlStr, dialOpts)
	if err != nil {
		results = append(results, result{Err: err})
		return results
	}
	applyConnReadLimit(conn, cfg)
	defer conn.Close(websocket.StatusNormalClosure, "done")

	for i := 0; i < cfg.RequestsPerClient; i++ {
		res := runOverOpenConn(ctx, conn, cfg, sessionID)
		results = append(results, res)
		if res.Err != nil {
			break
		}
	}

	if createdByBench && cfg.DeleteSession {
		ctxDel, cancelDel := context.WithTimeout(context.Background(), cfg.Timeout)
		_ = deleteSession(ctxDel, cfg, sessionID)
		cancelDel()
	}

	return results
}

// runOverOpenConn sends one ask over an existing connection and waits for final.
func runOverOpenConn(ctx context.Context, conn *websocket.Conn, cfg config, sessionID string) result {
	start := time.Now()
	reqCtx, cancel := context.WithTimeout(ctx, cfg.Timeout)
	defer cancel()

	payload := buildAskPayload(cfg, sessionID)
	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		return result{Err: err}
	}

	if err := conn.Write(reqCtx, websocket.MessageText, payloadBytes); err != nil {
		return result{Err: err}
	}

	for {
		_, msg, err := conn.Read(reqCtx)
		if err != nil {
			return result{Err: err}
		}
		if cfg.DebugEvents {
			fmt.Printf("event raw: %s\n", string(msg))
		}
		var env eventEnvelope
		if err := json.Unmarshal(msg, &env); err != nil {
			return result{Err: fmt.Errorf("invalid event: %w", err)}
		}
		switch env.Type {
		case "stream":
			continue
		case "final":
			return result{Duration: time.Since(start)}
		case "error":
			var evt errorEvent
			if err := json.Unmarshal(msg, &evt); err != nil {
				return result{Err: fmt.Errorf("error event parse failed: %w", err)}
			}
			return result{Err: fmt.Errorf("server error: %s", evt.Content)}
		default:
			return result{Err: fmt.Errorf("unknown event type: %s", env.Type)}
		}
	}
}

// printConfigRecap exists to keep load-test runs self-describing.
func printConfigRecap(cfg config, perClientMode bool, totalRequests int, effectiveClients int) {
	style := makeStyler(shouldColor())
	mode := "total-requests"
	if perClientMode {
		mode = "per-client"
	}
	sessionPlan := "backend-managed"
	if cfg.SessionID != "" {
		sessionPlan = "reuse provided session"
	} else if cfg.CreateSession && cfg.PrepareSessions && perClientMode {
		sessionPlan = "prepare sessions per client"
	} else if cfg.CreateSession {
		sessionPlan = "create per request"
	}

	fmt.Printf("\n%s\n", style("WS BENCH CONFIG", colorBold, colorCyan))
	fmt.Printf("%s %s\n", style("Target:", colorDim), cfg.URL)
	fmt.Printf("%s %s\n", style("Agent ID:", colorDim), cfg.AgentID)
	if cfg.AgentUUID != "" {
		fmt.Printf("%s %s\n", style("Agent source:", colorDim), "provided UUID")
	}
	if cfg.AgentUUID == "" && cfg.EnsureV2DefinitionRef != "" {
		fmt.Printf("%s %s\n", style("Ensure v2 definition:", colorDim), cfg.EnsureV2DefinitionRef)
	}
	if cfg.AgentUUID == "" && cfg.EnsureV2ProfileID != "" {
		fmt.Printf("%s %s\n", style("Ensure v2 profile:", colorDim), cfg.EnsureV2ProfileID)
	}
	if len(cfg.DocumentLibraryIDs) > 0 {
		fmt.Printf("%s %s\n", style("Document libraries:", colorDim), strings.Join(cfg.DocumentLibraryIDs, ","))
	}
	if len(cfg.DocumentUIDs) > 0 {
		fmt.Printf("%s %s\n", style("Document UIDs:", colorDim), strings.Join(cfg.DocumentUIDs, ","))
	}
	if cfg.SearchPolicy != "" {
		fmt.Printf("%s %s\n", style("Search policy:", colorDim), cfg.SearchPolicy)
	}
	if cfg.SearchRagScope != "" {
		fmt.Printf("%s %s\n", style("RAG scope:", colorDim), cfg.SearchRagScope)
	}
	fmt.Printf("%s %s\n", style("Mode:", colorDim), mode)
	fmt.Printf("%s %d\n", style("Clients:", colorDim), effectiveClients)
	fmt.Printf("%s %d\n", style("Total requests:", colorDim), totalRequests)
	if perClientMode {
		fmt.Printf("%s %d\n", style("Requests per client:", colorDim), cfg.RequestsPerClient)
	}
	fmt.Printf("%s %s\n", style("Session plan:", colorDim), sessionPlan)
	fmt.Printf("%s %t\n", style("Create session:", colorDim), cfg.CreateSession)
	fmt.Printf("%s %t\n", style("Prepare sessions:", colorDim), cfg.PrepareSessions)
	fmt.Printf("%s %d\n", style("Prepare concurrency:", colorDim), cfg.PrepareConcurrency)
	fmt.Printf("%s %t\n", style("Delete sessions:", colorDim), cfg.DeleteSession)
	fmt.Printf("%s %s\n", style("Session title:", colorDim), cfg.SessionTitle)
	if cfg.SessionURL != "" {
		fmt.Printf("%s %s\n", style("Session URL override:", colorDim), cfg.SessionURL)
	}
	fmt.Printf("%s %s\n", style("Timeout:", colorDim), cfg.Timeout)
	fmt.Printf("%s %d\n", style("Read limit bytes:", colorDim), cfg.ReadLimitBytes)
	if cfg.TokenInQuery {
		fmt.Printf("%s %s\n", style("Auth:", colorDim), "query")
	} else {
		fmt.Printf("%s %s\n", style("Auth:", colorDim), "header")
	}
	fmt.Printf("%s %t\n", style("Insecure TLS:", colorDim), cfg.InsecureTLS)
}

// runOnceWithSession exists to measure one full websocket exchange, including
// optional session lifecycle.
func runOnceWithSession(cfg config, sessionID string) result {
	start := time.Now()
	ctx, cancel := context.WithTimeout(context.Background(), cfg.Timeout)
	defer cancel()

	createdByBench := false
	if sessionID == "" && cfg.CreateSession {
		createdID, err := createSession(ctx, cfg)
		if err != nil {
			return result{Err: err}
		}
		sessionID = createdID
		createdByBench = true
	}
	if createdByBench && cfg.DeleteSession {
		defer func() {
			ctx, cancel := context.WithTimeout(context.Background(), cfg.Timeout)
			if err := deleteSession(ctx, cfg, sessionID); err != nil {
				fmt.Fprintf(os.Stderr, "delete session failed: %v\n", err)
			}
			cancel()
		}()
	}

	urlStr, err := buildURL(cfg.URL, cfg.Token, cfg.TokenInQuery)
	if err != nil {
		return result{Err: err}
	}

	dialOpts := &websocket.DialOptions{
		CompressionMode: websocket.CompressionDisabled,
	}
	if cfg.Token != "" && !cfg.TokenInQuery {
		dialOpts.HTTPHeader = http.Header{
			"Authorization": []string{"Bearer " + cfg.Token},
		}
	}
	if cfg.InsecureTLS {
		dialOpts.HTTPClient = &http.Client{
			Transport: &http.Transport{
				TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
			},
		}
	}

	conn, _, err := websocket.Dial(ctx, urlStr, dialOpts)
	if err != nil {
		return result{Err: err}
	}
	applyConnReadLimit(conn, cfg)
	defer conn.Close(websocket.StatusNormalClosure, "done")

	payload := buildAskPayload(cfg, sessionID)
	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		return result{Err: err}
	}

	if err := conn.Write(ctx, websocket.MessageText, payloadBytes); err != nil {
		return result{Err: err}
	}

	for {
		_, msg, err := conn.Read(ctx)
		if err != nil {
			return result{Err: err}
		}
		if cfg.DebugEvents {
			fmt.Printf("event raw: %s\n", string(msg))
		}
		var env eventEnvelope
		if err := json.Unmarshal(msg, &env); err != nil {
			return result{Err: fmt.Errorf("invalid event: %w", err)}
		}
		switch env.Type {
		case "stream":
			continue
		case "final":
			return result{Duration: time.Since(start)}
		case "error":
			var evt errorEvent
			if err := json.Unmarshal(msg, &evt); err != nil {
				return result{Err: fmt.Errorf("error event parse failed: %w", err)}
			}
			return result{Err: fmt.Errorf("server error: %s", evt.Content)}
		default:
			return result{Err: fmt.Errorf("unknown event type: %s", env.Type)}
		}
	}
}

// buildAskPayload exists to keep the websocket request contract in one place.
// Usage: call before serializing an ask sent to `/chatbot/query/ws`.
func buildAskPayload(cfg config, sessionID string) askPayload {
	payload := askPayload{
		Type:             "ask",
		SessionID:        sessionID,
		Message:          cfg.Message,
		AgentID:          cfg.AgentID,
		ClientExchangeID: newExchangeID(),
	}
	if runtimeContext := buildRuntimeContextPayload(cfg, sessionID); runtimeContext != nil {
		payload.RuntimeContext = runtimeContext
	}
	return payload
}

// buildRuntimeContextPayload exists to pass retrieval-scoping hints to Rico.
// Usage: populate library filters or `search_rag_scope` to benchmark corpus search paths.
func buildRuntimeContextPayload(cfg config, sessionID string) *runtimeContextPayload {
	if sessionID == "" &&
		len(cfg.DocumentLibraryIDs) == 0 &&
		len(cfg.DocumentUIDs) == 0 &&
		cfg.SearchPolicy == "" &&
		cfg.SearchRagScope == "" &&
		cfg.IncludeSessionScope == nil &&
		cfg.IncludeCorpusScope == nil {
		return nil
	}

	return &runtimeContextPayload{
		SessionID:                    sessionID,
		SelectedDocumentLibrariesIDs: cfg.DocumentLibraryIDs,
		SelectedDocumentUIDs:         cfg.DocumentUIDs,
		SearchPolicy:                 cfg.SearchPolicy,
		SearchRagScope:               cfg.SearchRagScope,
		IncludeSessionScope:          cfg.IncludeSessionScope,
		IncludeCorpusScope:           cfg.IncludeCorpusScope,
	}
}

// applyConnReadLimit exists to let the benchmark receive larger RAG and MCP
// payloads without tripping the websocket library's conservative default cap.
// Usage: call immediately after each successful websocket dial.
func applyConnReadLimit(conn *websocket.Conn, cfg config) {
	if conn == nil || cfg.ReadLimitBytes <= 0 {
		return
	}
	conn.SetReadLimit(cfg.ReadLimitBytes)
}

func buildURL(rawURL, token string, tokenInQuery bool) (string, error) {
	if !tokenInQuery || token == "" {
		return rawURL, nil
	}
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return "", err
	}
	query := parsed.Query()
	query.Set("token", token)
	parsed.RawQuery = query.Encode()
	return parsed.String(), nil
}

func urlHasToken(rawURL string) bool {
	parsed, err := url.Parse(rawURL)
	if err != nil {
		return false
	}
	return parsed.Query().Get("token") != ""
}

func newExchangeID() string {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		return fmt.Sprintf("ex-%d", time.Now().UnixNano())
	}
	return hex.EncodeToString(b[:])
}

// shouldEnsureV2Agent exists so an explicit benchmark target agent always wins
// over the bench bootstrap flow. Use it before creating or deleting temporary
// agents. Example: `if shouldEnsureV2Agent(cfg) { ... }`.
func shouldEnsureV2Agent(cfg config) bool {
	if strings.TrimSpace(cfg.AgentUUID) != "" {
		return false
	}
	return cfg.EnsureV2DefinitionRef != "" || cfg.EnsureV2ProfileID != ""
}

// ensureV2Agent exists to create one dynamic v2 agent before the benchmark so
// the load test can hit a real v2 RAG runtime instead of a v1 fallback.
// Usage: pass either `-ensure-v2-definition-ref` or `-ensure-v2-profile-id`.
func ensureV2Agent(cfg config) (string, error) {
	agentCreateURL, err := getAgentCreateURL(cfg)
	if err != nil {
		return "", err
	}

	payload := createV2AgentPayload{
		Name:          cfg.EnsureAgentName,
		DefinitionRef: cfg.EnsureV2DefinitionRef,
		ProfileID:     cfg.EnsureV2ProfileID,
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}

	ctx, cancel := context.WithTimeout(context.Background(), cfg.Timeout)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, agentCreateURL, strings.NewReader(string(body)))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	if cfg.Token != "" {
		req.Header.Set("Authorization", "Bearer "+cfg.Token)
	}

	client := &http.Client{}
	if cfg.InsecureTLS {
		client.Transport = &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
		}
	}

	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", fmt.Errorf("create v2 agent failed: %s", resp.Status)
	}

	var created createdAgentResponse
	if err := json.NewDecoder(resp.Body).Decode(&created); err != nil {
		return "", err
	}
	if created.ID == "" {
		return "", fmt.Errorf("create v2 agent returned empty id")
	}
	return created.ID, nil
}

// parseCSVFlag exists to keep list-style benchmark flags compact for CLI and
// Helm usage. Example: `-document-library-ids=lib-a,lib-b`.
func parseCSVFlag(raw string) []string {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return nil
	}
	parts := strings.Split(trimmed, ",")
	values := make([]string, 0, len(parts))
	for _, part := range parts {
		value := strings.TrimSpace(part)
		if value != "" {
			values = append(values, value)
		}
	}
	if len(values) == 0 {
		return nil
	}
	return values
}

// parseOptionalBoolFlag exists because runtime_context booleans need a tri-state:
// unset, true, or false. Example: `-include-corpus-scope=false`.
func parseOptionalBoolFlag(raw string) *bool {
	trimmed := strings.TrimSpace(strings.ToLower(raw))
	if trimmed == "" {
		return nil
	}
	value := trimmed == "true"
	return &value
}

func createSession(ctx context.Context, cfg config) (string, error) {
	sessionURL, err := getSessionURL(cfg)
	if err != nil {
		return "", err
	}

	payload := map[string]string{
		"agent_id": cfg.AgentID,
		"title":    cfg.SessionTitle,
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, sessionURL, strings.NewReader(string(body)))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/json")
	if cfg.Token != "" {
		req.Header.Set("Authorization", "Bearer "+cfg.Token)
	}

	client := &http.Client{}
	if cfg.InsecureTLS {
		client.Transport = &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
		}
	}

	resp, err := client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", fmt.Errorf("create session failed: %s", resp.Status)
	}

	var session struct {
		ID string `json:"id"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&session); err != nil {
		return "", err
	}
	if session.ID == "" {
		return "", fmt.Errorf("create session returned empty id")
	}
	return session.ID, nil
}

// deleteAgent exists to clean up an agent created only for one benchmark run.
// Usage: enable with `-delete-created-agent=true` when the bench creates a v2 agent.
func deleteAgent(ctx context.Context, cfg config, agentID string) error {
	deleteURL, err := getAgentDeleteURL(cfg, agentID)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, deleteURL, nil)
	if err != nil {
		return err
	}
	if cfg.Token != "" {
		req.Header.Set("Authorization", "Bearer "+cfg.Token)
	}

	client := &http.Client{}
	if cfg.InsecureTLS {
		client.Transport = &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
		}
	}

	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("delete agent failed: %s", resp.Status)
	}
	return nil
}

func createSessions(cfg config, count int) ([]string, error) {
	if count <= 0 {
		return []string{}, nil
	}
	type sessionResult struct {
		index int
		id    string
		err   error
	}
	ids := make([]string, count)
	results := make(chan sessionResult, count)
	jobs := make(chan int)
	workers := minInt(count, cfg.PrepareConcurrency)
	if workers < 1 {
		workers = 1
	}
	var wg sync.WaitGroup
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for idx := range jobs {
				ctx, cancel := context.WithTimeout(context.Background(), cfg.Timeout)
				id, err := createSession(ctx, cfg)
				cancel()
				results <- sessionResult{index: idx, id: id, err: err}
			}
		}()
	}
	for i := 0; i < count; i++ {
		jobs <- i
	}
	close(jobs)
	wg.Wait()
	close(results)

	var firstErr error
	for res := range results {
		if res.err != nil && firstErr == nil {
			firstErr = res.err
		}
		ids[res.index] = res.id
	}
	if firstErr != nil {
		return nil, firstErr
	}
	return ids, nil
}

func deleteSession(ctx context.Context, cfg config, sessionID string) error {
	deleteURL, err := getSessionDeleteURL(cfg, sessionID)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, deleteURL, nil)
	if err != nil {
		return err
	}
	if cfg.Token != "" {
		req.Header.Set("Authorization", "Bearer "+cfg.Token)
	}

	client := &http.Client{}
	if cfg.InsecureTLS {
		client.Transport = &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
		}
	}

	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("delete session failed: %s", resp.Status)
	}
	return nil
}

func deleteSessions(cfg config, sessionIDs []string) {
	if len(sessionIDs) == 0 {
		return
	}
	jobs := make(chan string)
	workers := minInt(len(sessionIDs), cfg.PrepareConcurrency)
	if workers < 1 {
		workers = 1
	}
	var wg sync.WaitGroup
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for id := range jobs {
				ctx, cancel := context.WithTimeout(context.Background(), cfg.Timeout)
				if err := deleteSession(ctx, cfg, id); err != nil {
					fmt.Fprintf(os.Stderr, "delete session failed: %v\n", err)
				}
				cancel()
			}
		}()
	}
	for _, id := range sessionIDs {
		if id == "" {
			continue
		}
		jobs <- id
	}
	close(jobs)
	wg.Wait()
}

func getSessionURL(cfg config) (string, error) {
	if cfg.SessionURL != "" {
		return cfg.SessionURL, nil
	}
	return deriveSessionURL(cfg.URL)
}

// getAgentCreateURL exists to derive the agent management endpoint from the
// websocket target so the benchmark can bootstrap a dynamic v2 agent itself.
// Usage: override with `-agent-create-url` when the default path is not correct.
func getAgentCreateURL(cfg config) (string, error) {
	if cfg.AgentCreateURL != "" {
		return cfg.AgentCreateURL, nil
	}
	parsed, err := url.Parse(cfg.URL)
	if err != nil {
		return "", err
	}
	switch parsed.Scheme {
	case "ws":
		parsed.Scheme = "http"
	case "wss":
		parsed.Scheme = "https"
	}
	replacements := []string{
		"/chatbot/query/ws-baseline",
		"/chatbot/query/ws",
	}
	for _, old := range replacements {
		if strings.Contains(parsed.Path, old) {
			parsed.Path = strings.Replace(parsed.Path, old, "/agents/v2/create", 1)
			return parsed.String(), nil
		}
	}
	return "", fmt.Errorf("cannot derive agent create URL from %s (set -agent-create-url)", cfg.URL)
}

// getAgentDeleteURL exists to address the delete endpoint for one benchmark-
// created agent after the run completes.
// Usage: only used when `-delete-created-agent=true`.
func getAgentDeleteURL(cfg config, agentID string) (string, error) {
	createURL, err := getAgentCreateURL(cfg)
	if err != nil {
		return "", err
	}
	parsed, err := url.Parse(createURL)
	if err != nil {
		return "", err
	}
	parsed.Path = strings.TrimSuffix(parsed.Path, "/v2/create") + "/" + agentID
	return parsed.String(), nil
}

func getSessionDeleteURL(cfg config, sessionID string) (string, error) {
	base, err := getSessionURL(cfg)
	if err != nil {
		return "", err
	}
	parsed, err := url.Parse(base)
	if err != nil {
		return "", err
	}
	parsed.Path = strings.TrimRight(parsed.Path, "/") + "/" + sessionID
	return parsed.String(), nil
}

func deriveSessionURL(wsURL string) (string, error) {
	parsed, err := url.Parse(wsURL)
	if err != nil {
		return "", err
	}
	switch parsed.Scheme {
	case "ws":
		parsed.Scheme = "http"
	case "wss":
		parsed.Scheme = "https"
	}

	// Support both main and baseline websocket routes.
	replacements := []string{
		"/chatbot/query/ws-baseline",
		"/chatbot/query/ws",
	}
	for _, old := range replacements {
		if strings.Contains(parsed.Path, old) {
			parsed.Path = strings.Replace(parsed.Path, old, "/chatbot/session", 1)
			return parsed.String(), nil
		}
	}

	return "", fmt.Errorf("cannot derive session URL from %s (set -session-url)", wsURL)
}

func shouldColor() bool {
	if os.Getenv("NO_COLOR") != "" || os.Getenv("TERM") == "dumb" {
		return false
	}
	info, err := os.Stdout.Stat()
	if err != nil {
		return false
	}
	return (info.Mode() & os.ModeCharDevice) != 0
}

func makeStyler(enabled bool) func(string, ...string) string {
	return func(s string, codes ...string) string {
		if !enabled || len(codes) == 0 {
			return s
		}
		return strings.Join(codes, "") + s + colorReset
	}
}

func printSummary(cfg config, total int, durations []time.Duration, errorCount int, errorSamples []string, elapsed time.Duration) {
	success := len(durations)
	style := makeStyler(shouldColor())
	outcome := "OK"
	outcomeColor := colorGreen
	if errorCount > 0 {
		outcome = "DEGRADED"
		outcomeColor = colorYellow
	}
	if success == 0 {
		outcome = "FAILED"
		outcomeColor = colorRed
	}
	successPct := 0.0
	if total > 0 {
		successPct = (float64(success) / float64(total)) * 100
	}

	fmt.Printf("\n%s\n", style("WS BENCH SUMMARY", colorBold, colorCyan))
	fmt.Printf("%s %s\n", style("Outcome:", colorDim), style(outcome, colorBold, outcomeColor))
	fmt.Printf("%s %s\n", style("Target:", colorDim), cfg.URL)
	fmt.Printf("%s %s\n", style("Agent ID:", colorDim), cfg.AgentID)
	fmt.Printf("%s %d\n", style("Total requests:", colorDim), total)
	fmt.Printf("%s %d\n", style("Concurrent clients:", colorDim), cfg.Clients)
	if cfg.RequestsPerClient > 0 {
		fmt.Printf("%s %d\n", style("Requests per client:", colorDim), cfg.RequestsPerClient)
	}
	fmt.Printf("%s %s\n", style("Success:", colorDim), style(fmt.Sprintf("%d (%.2f%%)", success, successPct), colorGreen))
	if errorCount > 0 {
		fmt.Printf("%s %s\n", style("Errors:", colorDim), style(fmt.Sprintf("%d", errorCount), colorRed))
	} else {
		fmt.Printf("%s %d\n", style("Errors:", colorDim), errorCount)
	}
	fmt.Printf("%s %s\n", style("Elapsed:", colorDim), elapsed.Round(time.Millisecond))
	if success > 0 {
		fmt.Printf("%s %.2f\n", style("Requests/sec:", colorDim), float64(success)/elapsed.Seconds())
		stats := summarize(durations)
		fmt.Printf("%s %s\n",
			style("Latency ms (min/avg/p50/p95/p99/max):", colorDim),
			style(fmt.Sprintf("%d/%d/%d/%d/%d/%d",
				stats.Min.Milliseconds(),
				stats.Avg.Milliseconds(),
				stats.P50.Milliseconds(),
				stats.P95.Milliseconds(),
				stats.P99.Milliseconds(),
				stats.Max.Milliseconds(),
			), colorBold, colorCyan),
		)
	}
	if len(errorSamples) > 0 {
		fmt.Printf("\n%s\n", style("Sample errors:", colorBold, colorRed))
		for _, sample := range errorSamples {
			fmt.Printf("%s %s\n", style("-", colorRed), sample)
		}
	}
}

type latencyStats struct {
	Min time.Duration
	Max time.Duration
	Avg time.Duration
	P50 time.Duration
	P95 time.Duration
	P99 time.Duration
}

func summarize(durations []time.Duration) latencyStats {
	sort.Slice(durations, func(i, j int) bool { return durations[i] < durations[j] })
	total := time.Duration(0)
	for _, d := range durations {
		total += d
	}
	return latencyStats{
		Min: durations[0],
		Max: durations[len(durations)-1],
		Avg: total / time.Duration(len(durations)),
		P50: percentile(durations, 0.50),
		P95: percentile(durations, 0.95),
		P99: percentile(durations, 0.99),
	}
}

func percentile(sorted []time.Duration, p float64) time.Duration {
	if len(sorted) == 0 {
		return 0
	}
	if p <= 0 {
		return sorted[0]
	}
	if p >= 1 {
		return sorted[len(sorted)-1]
	}
	pos := int(math.Ceil(p*float64(len(sorted)))) - 1
	if pos < 0 {
		pos = 0
	}
	if pos >= len(sorted) {
		pos = len(sorted) - 1
	}
	return sorted[pos]
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}

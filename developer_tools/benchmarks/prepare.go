package main

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func validateCPDestination(cfg config) error {
	u, err := url.Parse(cfg.FredOrigin)
	if err != nil || (u.Scheme != "http" && u.Scheme != "https") || u.Hostname() == "" || u.User != nil || u.RawQuery != "" || u.ForceQuery || u.Fragment != "" || (u.Path != "" && u.Path != "/") || !weaverPublicPath(cfg.ControlPlanePath+"/spaces", "/spaces") {
		return benchmarkError("invalid_control_plane_destination")
	}
	return nil
}

func runTermsCLI(cfg config) int {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if err := runTermsPreparation(ctx, cfg); err != nil {
		fmt.Fprintln(os.Stderr, "identity preparation:", classifyError(err))
		return 1
	}
	fmt.Println("Synthetic identity preparation completed; no sessions or load executed")
	return 0
}

func runTermsPreparation(ctx context.Context, cfg config) error {
	if !cfg.PrepareOnly || cfg.Scenario != "" || cfg.ConcurrencySteps != "" || cfg.CredentialFile == "" || cfg.RawReportPath == "" || (cfg.AcceptTestTerms != "" && cfg.AcceptTestTerms != "current") || (cfg.Target != "swift" && cfg.Target != "weaver") || cfg.Timeout <= 0 || cfg.AuthConcurrency < 1 || cfg.AuthConcurrency > 64 {
		return benchmarkError("invalid_identity_preparation_options")
	}
	if err := validateCPDestination(cfg); err != nil {
		return err
	}
	credentials, err := readCredentials(cfg.CredentialFile, 1)
	if err != nil {
		return err
	}
	if err := validateSyntheticCredentials(credentials); err != nil {
		return err
	}
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	writer, err := newScenarioWriter(cfg.RawReportPath, cancel)
	if err != nil {
		return err
	}
	client := sseHTTPClient(config{})
	defer client.CloseIdleConnections()
	identities, err := acquireIdentities(ctx, cfg, credentials, len(credentials.Users), newExchangeID(), client, func(r authRecord) { writer.write(r) })
	if err == nil {
		err = prepareIdentityTerms(ctx, cfg, identities, client, cfg.AcceptTestTerms, func(r onboardingRecord) { writer.write(r) })
	}
	outcome := "success"
	category := ""
	if err != nil {
		outcome = "error"
		category = classifyError(err)
	}
	writer.write(map[string]string{"kind": "preparation_summary", "schema_version": "fred.bench.preparation.v1", "outcome": outcome, "error": category})
	if closeErr := writer.close(); closeErr != nil {
		return closeErr
	}
	return err
}

// Read-only preflight completes for all required identities before any load.
// Swift preparation is performed once here, never added to its per-turn timing.
func preflightScenario(ctx context.Context, cfg config, identities []*benchmarkIdentity, client *http.Client, writer *scenarioWriter) error {
	cp := cfg
	if cfg.Target == "swift" {
		u, _ := url.Parse(cfg.URL)
		cp.FredOrigin = u.Scheme + "://" + u.Host
	}
	if err := validateCPDestination(cp); err != nil {
		return err
	}
	if err := prepareIdentityTerms(ctx, cp, identities, client, "", func(r onboardingRecord) { writer.write(r) }); err != nil {
		return err
	}
	for _, identity := range identities {
		phase := phaseMeasurement{StartedAt: time.Now()}
		checkCtx, cancel := context.WithTimeout(ctx, cfg.Timeout)
		token, _, err := identity.token(checkCtx)
		if err == nil {
			a := &weaverAdapter{cfg: cp, http: client}
			a.cfg.Token = token
			path := a.instancePath() + "/prepare-execution"
			if cfg.Target == "swift" {
				path = cp.ControlPlanePath + "/teams/" + url.PathEscape(cfg.SSETeamID) + "/agent-instances/" + url.PathEscape(cfg.AgentInstanceID) + "/prepare-execution"
			}
			var p struct {
				weaverPreparation
				TeamID string `json:"team_id"`
			}
			_, err = a.json(checkCtx, http.MethodPost, path, nil, &p)
			if err == nil && (p.Transport != "sse" || !p.SupportsStreaming || !weaverPublicPath(p.StreamURL, "/agents/execute/stream") || p.AgentInstanceID != cfg.AgentInstanceID) {
				err = benchmarkError("invalid_preflight_preparation")
			}
			if err == nil && cfg.Target == "weaver" && (!p.matches(cfg, p.Revision) || (len(p.ModelError) > 0 && string(p.ModelError) != "null") || p.Inference == nil) {
				err = benchmarkError("preflight_model_or_binding_unavailable")
			}
			if err == nil && cfg.Target == "swift" {
				u, _ := url.Parse(cfg.URL)
				if p.TeamID != cfg.SSETeamID || p.StreamURL != u.Path {
					err = benchmarkError("preflight_route_or_team_mismatch")
				}
			}
		}
		cancel()
		phase.finish(err)
		writer.write(struct {
			Kind       string `json:"kind"`
			IdentityID string `json:"identity_id"`
			phaseMeasurement
		}{"preflight", identity.pseudonym, phase})
		if err != nil {
			return err
		}
	}
	return nil
}

func scenarioExplicitFlags(names []string) []string {
	var out []string
	for _, name := range names {
		if name != "control-plane-path" {
			out = append(out, name)
		}
	}
	return out
}

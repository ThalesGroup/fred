package main

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"time"
	"unicode"
)

type onboardingRecord struct {
	Kind       string `json:"kind"`
	IdentityID string `json:"identity_id"`
	Target     string `json:"target"`
	Operation  string `json:"operation"`
	Version    string `json:"version,omitempty"`
	phaseMeasurement
}

// The factory marks disposable identities with bench- usernames. Labels are
// opaque report aliases (normally user-0001), not proof of synthetic ownership.
func validateSyntheticCredentials(c credentialFile) error {
	for _, user := range c.Users {
		if !strings.HasPrefix(user.Username, "bench-") || len(user.Username) == len("bench-") {
			return benchmarkError("preparation_requires_synthetic_credentials")
		}
	}
	if len(c.Users) == 0 {
		return benchmarkError("preparation_requires_synthetic_credentials")
	}
	return nil
}

// prepareIdentityTerms never creates sessions or calls an execution endpoint.
// The caller validates the CP origin/mount and synthetic credentials first.
// Empty accept is read-only; only the explicit operator choice "current" writes.
// Swift's versionless POST cannot enforce an atomic version precondition. We
// detect observed changes, but do not claim that rereading makes it atomic.
func prepareIdentityTerms(ctx context.Context, cfg config, identities []*benchmarkIdentity, client *http.Client, accept string, record func(onboardingRecord)) error {
	if (accept != "" && accept != "current") || (cfg.Target != "swift" && cfg.Target != "weaver") || cfg.Timeout <= 0 {
		return benchmarkError("invalid_terms_preparation")
	}
	a := &weaverAdapter{cfg: cfg, http: client}
	a.cfg.Token = ""
	configCtx, cancel := context.WithTimeout(ctx, cfg.Timeout)
	version, err := readTermsConfig(configCtx, a)
	cancel()
	if err != nil {
		return safeAuthError(err)
	}
	for _, identity := range identities {
		r := onboardingRecord{Kind: "onboarding", IdentityID: identity.pseudonym, Target: cfg.Target, Operation: "failed", Version: version, phaseMeasurement: phaseMeasurement{StartedAt: time.Now()}}
		identityCtx, cancel := context.WithTimeout(ctx, cfg.Timeout)
		operation, err := prepareIdentityTermsOnce(identityCtx, a, identity, version, accept)
		cancel()
		r.Operation = operation
		r.finish(err)
		if record != nil {
			record(r)
		}
		if err != nil {
			return safeAuthError(err)
		}
	}
	return nil
}

func prepareIdentityTermsOnce(ctx context.Context, a *weaverAdapter, identity *benchmarkIdentity, version, accept string) (string, error) {
	if err := ctx.Err(); err != nil {
		return "failed", err
	}
	if version == "" {
		return "disabled", nil
	}
	request := func(method, path string, body, out any) error {
		token, _, err := identity.token(ctx)
		if err != nil {
			return err
		}
		a.cfg.Token = token
		status, err := a.json(ctx, method, a.cfg.ControlPlanePath+path, body, out)
		if err != nil {
			return err
		}
		expected := http.StatusOK
		if method == http.MethodPost && a.cfg.Target == "weaver" {
			expected = http.StatusNoContent
		}
		if status != expected {
			return benchmarkError("invalid_terms_response")
		}
		return nil
	}
	status := func() (string, error) {
		if a.cfg.Target == "swift" {
			var state struct {
				Accepted json.RawMessage `json:"cguValidated"`
			}
			if err := request(http.MethodGet, "/user", nil, &state); err != nil {
				return "", err
			}
			return readTermsVersion(state.Accepted)
		}
		var state struct {
			UserID    string          `json:"user_id"`
			Version   json.RawMessage `json:"gcu_version"`
			Accepted  json.RawMessage `json:"acceptance"`
			Admitted  *bool           `json:"admitted"`
			Bootstrap *bool           `json:"root_bootstrap_required"`
		}
		if err := request(http.MethodGet, "/me/onboarding", nil, &state); err != nil {
			return "", err
		}
		if state.UserID != identity.subject || state.Admitted == nil || state.Bootstrap == nil || len(state.Accepted) == 0 {
			return "", benchmarkError("invalid_terms_response")
		}
		if !*state.Admitted || *state.Bootstrap {
			return "", benchmarkError("terms_identity_not_admitted")
		}
		active, err := readTermsVersion(state.Version)
		if err != nil {
			return "", err
		}
		if active != version {
			return "", benchmarkError("terms_version_changed")
		}
		if string(state.Accepted) == "null" {
			return "", nil
		}
		var acceptance struct {
			Version json.RawMessage `json:"version"`
		}
		if json.Unmarshal(state.Accepted, &acceptance) != nil {
			return "", benchmarkError("invalid_terms_response")
		}
		return readTermsVersion(acceptance.Version)
	}
	accepted, err := status()
	if err != nil {
		return "failed", err
	}
	// Also detects a deployment change between identities in this batch.
	active, err := readTermsConfig(ctx, a)
	if err != nil {
		return "failed", err
	}
	if active != version {
		return "failed", benchmarkError("terms_version_changed")
	}
	if accepted == version {
		return "already_accepted", nil
	}
	if accept != "current" {
		return "required", benchmarkError("terms_acceptance_required")
	}
	var body any
	if a.cfg.Target == "weaver" {
		body = map[string]string{"version": version}
	}
	if err := request(http.MethodPost, "/gcu", body, nil); err != nil {
		return "failed", err
	}
	// A successful POST is a side effect even if subsequent verification fails.
	active, err = readTermsConfig(ctx, a)
	if err != nil {
		return "accepted_unverified", err
	}
	if active != version {
		return "accepted_unverified", benchmarkError("terms_version_changed")
	}
	accepted, err = status()
	if err != nil {
		return "accepted_unverified", err
	}
	if accepted != version {
		return "accepted_unverified", benchmarkError("terms_acceptance_not_verified")
	}
	return "accepted", nil
}

func readTermsConfig(ctx context.Context, a *weaverAdapter) (string, error) {
	var cfg struct {
		Version   json.RawMessage `json:"gcu_version"`
		Bootstrap *bool           `json:"root_bootstrap_required"`
	}
	status, err := a.json(ctx, http.MethodGet, a.cfg.ControlPlanePath+"/frontend/config", nil, &cfg)
	if err != nil {
		return "", err
	}
	if status != http.StatusOK || cfg.Bootstrap == nil {
		return "", benchmarkError("invalid_terms_response")
	}
	if *cfg.Bootstrap {
		return "", benchmarkError("terms_platform_bootstrap_required")
	}
	return readTermsVersion(cfg.Version)
}

func readTermsVersion(raw json.RawMessage) (string, error) {
	if string(raw) == "null" {
		return "", nil
	}
	var version string
	if json.Unmarshal(raw, &version) != nil || version == "" || len(version) > 128 || strings.TrimSpace(version) != version || strings.ContainsFunc(version, unicode.IsControl) {
		return "", benchmarkError("invalid_terms_response")
	}
	return version, nil
}

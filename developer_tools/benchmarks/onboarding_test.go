package main

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

func TestPrepareIdentityTerms(t *testing.T) {
	for _, target := range []string{"weaver", "swift"} {
		for _, tc := range []struct {
			name, accept, accepted, operation, errorCode                        string
			posts                                                               int
			changeBefore, changeAfter, postFails, missing, disabled, unadmitted bool
		}{
			{name: "already accepted", accept: "current", accepted: "v1", operation: "already_accepted"},
			{name: "explicit current", accept: "current", operation: "accepted", posts: 1},
			{name: "read only", operation: "required", errorCode: "terms_acceptance_required"},
			{name: "disabled", accept: "current", operation: "disabled", disabled: true},
			{name: "version changed before", accept: "current", operation: "failed", errorCode: "terms_version_changed", changeBefore: true},
			{name: "version changed after", accept: "current", operation: "accepted_unverified", errorCode: "terms_version_changed", posts: 1, changeAfter: true},
			{name: "post failed safe", accept: "current", operation: "failed", errorCode: "http_409", posts: 1, postFails: true},
			{name: "missing state", accept: "current", operation: "failed", errorCode: "invalid_terms_response", missing: true},
			{name: "unadmitted", accept: "current", operation: "failed", errorCode: "terms_identity_not_admitted", unadmitted: true},
		} {
			t.Run(target+"/"+tc.name, func(t *testing.T) {
				if tc.unadmitted && target == "swift" {
					return
				}
				var mu sync.Mutex
				posts, configs := 0, 0
				accepted, active := tc.accepted, "v1"
				server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					mu.Lock()
					defer mu.Unlock()
					w.Header().Set("Content-Type", "application/json")
					switch r.Method + " " + r.URL.Path {
					case "GET /control-plane/v1/frontend/config":
						configs++
						if tc.changeBefore && configs == 2 {
							active = "v2"
						}
						var version any = active
						if tc.disabled {
							version = nil
						}
						_ = json.NewEncoder(w).Encode(map[string]any{"gcu_version": version, "root_bootstrap_required": false})
					case "GET /control-plane/v1/me/onboarding", "GET /control-plane/v1/user":
						if r.Header.Get("Authorization") != "Bearer private-token" {
							t.Error("missing identity credential")
						}
						if tc.missing {
							_, _ = io.WriteString(w, `{}`)
							return
						}
						var value any
						if accepted != "" {
							value = accepted
						}
						if target == "swift" {
							_ = json.NewEncoder(w).Encode(map[string]any{"cguValidated": value})
						} else {
							if accepted != "" {
								value = map[string]string{"version": accepted}
							}
							_ = json.NewEncoder(w).Encode(map[string]any{"user_id": "subject", "gcu_version": active, "acceptance": value, "admitted": !tc.unadmitted, "root_bootstrap_required": false})
						}
					case "POST /control-plane/v1/gcu":
						posts++
						body, _ := io.ReadAll(r.Body)
						if target == "weaver" && string(body) != `{"version":"v1"}` {
							t.Errorf("missing version precondition: %s", body)
						}
						if target == "swift" && len(body) != 0 {
							t.Error("Swift expects no body")
						}
						if tc.postFails {
							w.WriteHeader(409)
							_, _ = io.WriteString(w, "private-password private-token sensitive upstream")
							return
						}
						accepted = active
						if tc.changeAfter {
							active = "v2"
						}
						if target == "weaver" {
							w.WriteHeader(204)
						} else {
							_, _ = io.WriteString(w, "null")
						}
					default:
						t.Errorf("unexpected business/session request: %s %s", r.Method, r.URL.Path)
						w.WriteHeader(500)
					}
				}))
				defer server.Close()
				cfg := config{Target: target, FredOrigin: server.URL, ControlPlanePath: "/control-plane/v1", Timeout: time.Second}
				identity := &benchmarkIdentity{gate: make(chan struct{}, 1), access: "private-token", subject: "subject", pseudonym: "user-1", refreshAt: time.Now().Add(time.Hour)}
				var records []onboardingRecord
				err := prepareIdentityTerms(context.Background(), cfg, []*benchmarkIdentity{identity}, server.Client(), tc.accept, func(r onboardingRecord) { records = append(records, r) })
				got := ""
				if err != nil {
					got = err.Error()
				}
				if got != tc.errorCode {
					t.Errorf("error=%q want=%q", got, tc.errorCode)
				}
				mu.Lock()
				if posts != tc.posts {
					t.Errorf("POST count=%d want=%d", posts, tc.posts)
				}
				mu.Unlock()
				if len(records) != 1 || records[0].Operation != tc.operation {
					t.Fatalf("records=%+v", records)
				}
				data, _ := json.Marshal(records)
				for _, secret := range []string{"private-password", "private-token", "subject", server.URL, "sensitive upstream"} {
					if strings.Contains(string(data), secret) || strings.Contains(got, secret) {
						t.Errorf("output leaked %q", secret)
					}
				}
			})
		}
	}
}

func TestTermsVersionRejectsMissingAndInvalidData(t *testing.T) {
	for _, raw := range []string{"", `{}`, `true`, `""`, `" v1"`, `"v1\n"`, `"` + strings.Repeat("a", 129) + `"`} {
		if _, err := readTermsVersion(json.RawMessage(raw)); err == nil {
			t.Errorf("accepted invalid version %q", raw)
		}
	}
	if v, err := readTermsVersion(json.RawMessage(`null`)); err != nil || v != "" {
		t.Fatal("null must disable CGU")
	}
}

func TestPreparationRejectsNonSyntheticCredentials(t *testing.T) {
	for _, name := range []string{"", "bench-", "alice", "benchmark-user"} {
		if validateSyntheticCredentials(credentialFile{Users: []credentialUser{{Username: name}}}) == nil {
			t.Errorf("accepted %q", name)
		}
	}
	if validateSyntheticCredentials(credentialFile{}) == nil {
		t.Fatal("accepted empty file")
	}
	if err := validateSyntheticCredentials(credentialFile{Users: []credentialUser{{Username: "bench-run-0001", Label: "user-0001"}}}); err != nil {
		t.Fatal(err)
	}
}

func TestPreparationRejectsUnknownConsentBeforeNetwork(t *testing.T) {
	cfg := config{Target: "weaver", Timeout: time.Second}
	if err := prepareIdentityTerms(context.Background(), cfg, nil, nil, "yes", nil); err != benchmarkError("invalid_terms_preparation") {
		t.Fatalf("error=%v", err)
	}
}

func TestTermsPreparationRejectsConfigBeforeIdentityWrites(t *testing.T) {
	for _, response := range []string{`{}`, `{"root_bootstrap_required":false}`, `{"gcu_version":"v1","root_bootstrap_required":true}`, `{"gcu_version":"v1"}`} {
		server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if r.Method != http.MethodGet || r.URL.Path != "/cp/frontend/config" {
				t.Error("unexpected identity operation")
			}
			_, _ = io.WriteString(w, response)
		}))
		cfg := config{Target: "weaver", FredOrigin: server.URL, ControlPlanePath: "/cp", Timeout: time.Second}
		err := prepareIdentityTerms(context.Background(), cfg, []*benchmarkIdentity{{pseudonym: "user-1"}}, server.Client(), "current", nil)
		server.Close()
		if err == nil {
			t.Fatalf("accepted incomplete/blocked config %s", response)
		}
	}
}

func TestTermsPreparationStopsBatchAfterUnverifiedAcceptance(t *testing.T) {
	var mu sync.Mutex
	posts := 0
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		switch r.URL.Path {
		case "/cp/frontend/config":
			_, _ = io.WriteString(w, `{"gcu_version":"v1","root_bootstrap_required":false}`)
		case "/cp/user":
			_, _ = io.WriteString(w, `{"cguValidated":null}`)
		case "/cp/gcu":
			posts++
			_, _ = io.WriteString(w, "null")
		default:
			t.Error("unexpected request")
			w.WriteHeader(500)
		}
	}))
	defer server.Close()
	identities := []*benchmarkIdentity{}
	for _, id := range []string{"one", "two"} {
		identities = append(identities, &benchmarkIdentity{gate: make(chan struct{}, 1), access: "token", pseudonym: id, refreshAt: time.Now().Add(time.Hour)})
	}
	records := []onboardingRecord{}
	cfg := config{Target: "swift", FredOrigin: server.URL, ControlPlanePath: "/cp", Timeout: time.Second}
	err := prepareIdentityTerms(context.Background(), cfg, identities, server.Client(), "current", func(r onboardingRecord) { records = append(records, r) })
	if err != benchmarkError("terms_acceptance_not_verified") || len(records) != 1 || records[0].Operation != "accepted_unverified" {
		t.Fatalf("error=%v records=%+v", err, records)
	}
	mu.Lock()
	defer mu.Unlock()
	if posts != 1 {
		t.Fatalf("mutated more identities after unverified acceptance: %d", posts)
	}
}

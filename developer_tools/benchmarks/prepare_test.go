package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
)

func TestPrepareOnlyCLIAuthenticatesSyntheticUsersWithoutLoad(t *testing.T) {
	var logins, posts atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/realms/app/protocol/openid-connect/token":
			logins.Add(1)
			_ = r.ParseForm()
			_ = json.NewEncoder(w).Encode(map[string]any{"access_token": testJWT(r.Form.Get("username")), "refresh_token": "PRIVATE_REFRESH", "token_type": "Bearer", "expires_in": 300})
		case "/control-plane/v1/frontend/config":
			fmt.Fprint(w, `{"gcu_version":null,"root_bootstrap_required":false}`)
		default:
			posts.Add(1)
			t.Error("preparation reached business endpoint")
		}
	}))
	defer server.Close()
	path := testCredentialPath(t, server.URL+"/realms/app", 2)
	data, _ := os.ReadFile(path)
	data = []byte(strings.ReplaceAll(string(data), "private-user-", "bench-test-"))
	_ = os.WriteFile(path, data, 0600)
	raw := filepath.Join(t.TempDir(), "prepare.jsonl")
	args := []string{"-prepare-only", "-target=weaver", "-fred-origin=" + server.URL, "-credential-file=" + path, "-accept-test-terms=current", "-raw-report=" + raw}
	cmd := exec.Command(os.Args[0], "-test.run=^TestCLIHelper$")
	cmd.Env = append(os.Environ(), "BENCH_TEST_CLI=1", "BENCH_TEST_ARGS="+strings.Join(args, "\n"))
	output, err := cmd.CombinedOutput()
	if err != nil || logins.Load() != 2 || posts.Load() != 0 {
		t.Fatalf("%v %s logins=%d posts=%d", err, output, logins.Load(), posts.Load())
	}
	data, _ = os.ReadFile(raw)
	if !strings.Contains(string(data), `"kind":"preparation_summary"`) || strings.Contains(string(data)+string(output), "PRIVATE") {
		t.Fatal("preparation output")
	}
}

func TestPreparationRejectsPublicAccountsBeforeLogin(t *testing.T) {
	path := testCredentialPath(t, "http://localhost/realms/app", 1)
	err := runTermsPreparation(context.Background(), config{PrepareOnly: true, Target: "weaver", FredOrigin: "http://localhost", ControlPlanePath: "/control-plane/v1", CredentialFile: path, RawReportPath: filepath.Join(t.TempDir(), "out.jsonl"), Timeout: 1, AuthConcurrency: 1})
	if err != benchmarkError("preparation_requires_synthetic_credentials") {
		t.Fatal(err)
	}
}

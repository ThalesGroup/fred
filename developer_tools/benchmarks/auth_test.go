package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func testJWT(subject string) string {
	payload, _ := json.Marshal(map[string]string{"sub": subject})
	return "e30." + base64.RawURLEncoding.EncodeToString(payload) + ".signature"
}
func testCredentialPath(t *testing.T, issuer string, count int) string {
	t.Helper()
	c := credentialFile{SchemaVersion: 1, Issuer: issuer, ClientID: "test-client", ClientSecret: "PRIVATE_CLIENT_SECRET"}
	for i := 0; i < count; i++ {
		c.Users = append(c.Users, credentialUser{Label: fmt.Sprint(i), Username: fmt.Sprintf("private-user-%d", i), Password: "PRIVATE_PASSWORD"})
	}
	data, _ := json.Marshal(c)
	path := filepath.Join(t.TempDir(), "credentials.json")
	if err := os.WriteFile(path, data, 0600); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestCredentialValidationAndIssuerPolicy(t *testing.T) {
	for _, issuer := range []string{"http://localhost:8080/realms/app", "http://keycloak:8080/realms/app", "http://app-keycloak:8080/realms/app", "https://app.localhost/realms/app", "http://[::1]/realms/app", "http://127.2.3.4/realms/app"} {
		if _, err := tokenEndpoint(issuer); err != nil {
			t.Fatal(issuer, err)
		}
	}
	for _, issuer := range []string{"https://example.com/realms/app", "http://localhost@evil/realms/app", "http://localhost/realms/app?x=y", "http://localhost/realms/app#x", "http://localhost/realms/%61pp", "http://localhost/realms/../app", "http://localhost:8080/realms/app/"} {
		if _, err := tokenEndpoint(issuer); err == nil {
			t.Fatal("accepted", issuer)
		}
	}
	path := testCredentialPath(t, "http://localhost/realms/app", 2)
	if _, err := readCredentials(path, 3); err == nil {
		t.Fatal("insufficient users accepted")
	}
	if _, err := readCredentials(path, 2); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(path, 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := readCredentials(path, 2); err == nil {
		t.Fatal("public credentials accepted")
	}
}

func TestIdentityAcquisitionAndConcurrentRefreshRotation(t *testing.T) {
	var active, maxActive, refreshes atomic.Int32
	var mu sync.Mutex
	var records []authRecord
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := active.Add(1)
		defer active.Add(-1)
		for {
			old := maxActive.Load()
			if n <= old || maxActive.CompareAndSwap(old, n) {
				break
			}
		}
		if r.URL.Path != "/realms/app/protocol/openid-connect/token" || r.Method != "POST" {
			t.Error("invalid token endpoint")
		}
		_ = r.ParseForm()
		if r.Form.Get("client_secret") != "PRIVATE_CLIENT_SECRET" {
			t.Error("secret missing")
		}
		sub := r.Form.Get("username")
		refresh := "r1-" + sub
		if r.Form.Get("grant_type") == "refresh_token" {
			refreshes.Add(1)
			if r.Form.Get("refresh_token") != "r1-private-user-0" {
				t.Error("wrong rotating token")
			}
			sub = "private-user-0"
			refresh = "r2"
		}
		time.Sleep(time.Millisecond)
		_ = json.NewEncoder(w).Encode(map[string]any{"access_token": testJWT(sub), "refresh_token": refresh, "expires_in": 300, "token_type": "Bearer"})
	}))
	defer server.Close()
	path := testCredentialPath(t, server.URL+"/realms/app", 4)
	credentials, _ := readCredentials(path, 4)
	client := sseHTTPClient(config{})
	defer client.CloseIdleConnections()
	identities, err := acquireIdentities(context.Background(), config{Timeout: time.Second, AuthConcurrency: 2}, credentials, 4, "campaign", client, func(r authRecord) { mu.Lock(); records = append(records, r); mu.Unlock() })
	if err != nil || maxActive.Load() > 2 || len(identities) != 4 {
		t.Fatalf("%v %d", err, maxActive.Load())
	}
	a := identities[0]
	a.refreshAt = time.Now().Add(-time.Second)
	var wg sync.WaitGroup
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			token, _, err := a.token(context.Background())
			if err != nil || token != testJWT("private-user-0") {
				t.Error("refresh failed", err)
			}
		}()
	}
	wg.Wait()
	if refreshes.Load() != 1 || a.refresh != "r2" || len(records) != 5 {
		t.Fatalf("refresh count=%d records=%d", refreshes.Load(), len(records))
	}
	for i, a := range identities {
		if a.subject != fmt.Sprintf("private-user-%d", i) {
			t.Fatal("attribution changed")
		}
	}
	data, _ := json.Marshal(records)
	for _, secret := range []string{"PRIVATE", "private-user", "signature", "r1-"} {
		if strings.Contains(string(data), secret) {
			t.Fatal("auth privacy")
		}
	}
}

func TestRefreshFailureIsStickyAndRedirectRefused(t *testing.T) {
	var requests atomic.Int32
	external := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Error("redirect followed") }))
	defer external.Close()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests.Add(1)
		w.Header().Set("Location", external.URL)
		w.WriteHeader(307)
		fmt.Fprint(w, "PRIVATE upstream")
	}))
	defer server.Close()
	client := sseHTTPClient(config{})
	defer client.CloseIdleConnections()
	a := &benchmarkIdentity{gate: make(chan struct{}, 1), client: client, endpoint: server.URL, timeout: time.Second, refresh: "private"}
	for i := 0; i < 3; i++ {
		_, _, err := a.token(context.Background())
		if err == nil || strings.Contains(err.Error(), "PRIVATE") {
			t.Fatal("unsafe failure", err)
		}
	}
	if requests.Load() != 1 {
		t.Fatal("failed refresh retried")
	}
	a.gate <- struct{}{}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	_, _, err := a.token(ctx)
	<-a.gate
	if err != context.Canceled {
		t.Fatal("gate ignored cancellation", err)
	}
}

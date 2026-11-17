package main

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type benchPublicAuth struct {
	Enabled  bool   `json:"enabled"`
	Realm    string `json:"realm_url"`
	ClientID string `json:"client_id"`
	Provider string `json:"provider"`
	UIDClaim string `json:"uid_claim"`
}

func secureBenchURL(raw string) (*url.URL, error) {
	u, err := url.Parse(raw)
	if err != nil || u.Hostname() == "" || u.User != nil || u.RawQuery != "" || u.ForceQuery || u.Fragment != "" {
		return nil, fmt.Errorf("invalid HTTP(S) URL")
	}
	ip := net.ParseIP(u.Hostname())
	local := u.Hostname() == "localhost" || strings.HasSuffix(u.Hostname(), ".localhost") || (ip != nil && ip.IsLoopback())
	if u.Scheme == "http" && !local {
		local = benchLoopbackAlias(u.Hostname(), net.DefaultResolver.LookupIPAddr)
	}
	if u.Scheme != "https" && !(u.Scheme == "http" && local) {
		return nil, fmt.Errorf("HTTPS is required for nonlocal hosts")
	}
	return u, nil
}

// The local factory uses these issuer names inside and outside k3d. Permit
// cleartext only when the workstation resolves every address to loopback.
func benchLoopbackAlias(host string, lookup func(context.Context, string) ([]net.IPAddr, error)) bool {
	if host != "keycloak" && host != "app-keycloak" {
		return false
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	addresses, err := lookup(ctx, host)
	if err != nil || len(addresses) == 0 {
		return false
	}
	for _, address := range addresses {
		if !address.IP.IsLoopback() {
			return false
		}
	}
	return true
}

// Authorization code + PKCE, loopback listener and browser SSO. Credentials stay
// in Keycloak; access/refresh tokens live only in memory for this CLI session.
func browserBenchLogin(ctx context.Context, auth benchPublicAuth, client *http.Client, open func(string) error, tell func(string)) (*benchmarkIdentity, error) {
	if !auth.Enabled {
		return nil, fmt.Errorf("sign-in: authentication is not enabled in Fred")
	}
	if auth.ClientID == "" {
		return nil, fmt.Errorf("sign-in: Keycloak client is missing from the Fred configuration")
	}
	if auth.Provider != "keycloak" {
		return nil, fmt.Errorf("sign-in: Keycloak identity provider is required")
	}
	if auth.UIDClaim != "" && auth.UIDClaim != "sub" {
		return nil, fmt.Errorf("sign-in: sub identity claim is required")
	}
	issuer, err := secureBenchURL(strings.TrimRight(auth.Realm, "/"))
	if err != nil {
		return nil, fmt.Errorf("sign-in: invalid Keycloak URL (%w)", err)
	}
	ctx, cancel := context.WithTimeout(ctx, 3*time.Minute)
	defer cancel()
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, issuer.String()+"/.well-known/openid-configuration", nil)
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("Keycloak is unreachable")
	}
	data, readErr := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	resp.Body.Close()
	var discovery struct {
		Issuer    string `json:"issuer"`
		Authorize string `json:"authorization_endpoint"`
		Token     string `json:"token_endpoint"`
	}
	if readErr != nil || resp.StatusCode != 200 || json.Unmarshal(data, &discovery) != nil || discovery.Issuer != issuer.String() {
		return nil, fmt.Errorf("invalid Keycloak configuration")
	}
	for _, raw := range []string{discovery.Authorize, discovery.Token} {
		u, err := secureBenchURL(raw)
		if err != nil || u.Scheme != issuer.Scheme || u.Host != issuer.Host {
			return nil, fmt.Errorf("unexpected Keycloak endpoint")
		}
	}
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		return nil, fmt.Errorf("cannot listen for the local sign-in callback")
	}
	defer listener.Close()
	state, verifier := rand.Text()+rand.Text(), rand.Text()+rand.Text()
	challenge := sha256.Sum256([]byte(verifier))
	redirect := "http://" + listener.Addr().String() + "/callback"
	codes := make(chan string, 1)
	loginErrors := make(chan error, 1)
	server := &http.Server{ReadHeaderTimeout: 5 * time.Second, WriteTimeout: 5 * time.Second, MaxHeaderBytes: 8192}
	server.Handler = http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		q := r.URL.Query()
		if r.Method != http.MethodGet || r.URL.Path != "/callback" || r.Host != listener.Addr().String() || q.Get("state") != state || (q.Get("iss") != "" && q.Get("iss") != issuer.String()) {
			http.Error(w, "Invalid sign-in callback.", 400)
			return
		}
		if q.Get("error") != "" {
			select {
			case loginErrors <- fmt.Errorf("sign-in was denied in the browser"):
			default:
			}
			http.Error(w, "Sign-in denied. Return to the terminal.", 400)
			return
		}
		code := q.Get("code")
		if code == "" || len(code) > 8192 {
			http.Error(w, "Missing authorization code.", 400)
			return
		}
		select {
		case codes <- code:
			fmt.Fprintln(w, "Sign-in received. You can return to the bench terminal.")
		default:
			http.Error(w, "Callback already received.", 409)
		}
	})
	go func() { _ = server.Serve(listener) }()
	defer server.Close()
	endpoint, _ := url.Parse(discovery.Authorize)
	q := url.Values{"client_id": {auth.ClientID}, "redirect_uri": {redirect}, "response_type": {"code"}, "scope": {"openid"}, "state": {state}, "code_challenge": {base64.RawURLEncoding.EncodeToString(challenge[:])}, "code_challenge_method": {"S256"}}
	endpoint.RawQuery = q.Encode()
	tell("Signing in through your browser...")
	if err := open(endpoint.String()); err != nil {
		tell("Open this URL in your browser:\n" + endpoint.String())
	}
	var code string
	select {
	case <-ctx.Done():
		return nil, fmt.Errorf("sign-in cancelled or timed out after 3 minutes")
	case err := <-loginErrors:
		return nil, err
	case code = <-codes:
	}
	identity := &benchmarkIdentity{gate: make(chan struct{}, 1), client: client, endpoint: discovery.Token, clientID: auth.ClientID, timeout: 30 * time.Second}
	_, err = identity.exchange(ctx, url.Values{"grant_type": {"authorization_code"}, "code": {code}, "redirect_uri": {redirect}, "code_verifier": {verifier}}, "acquire")
	if err != nil {
		return nil, fmt.Errorf("Keycloak sign-in: %s", classifyError(err))
	}
	return identity, nil
}

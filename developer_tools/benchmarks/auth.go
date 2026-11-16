package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strings"
	"sync"
	"time"
)

type credentialUser struct {
	Label    string `json:"label"`
	Username string `json:"username"`
	Password string `json:"password"`
}
type credentialFile struct {
	SchemaVersion int              `json:"schema_version"`
	Issuer        string           `json:"issuer"`
	ClientID      string           `json:"client_id"`
	ClientSecret  string           `json:"client_secret"`
	Users         []credentialUser `json:"users"`
}

var realmPath = regexp.MustCompile(`^/realms/[A-Za-z0-9_-]+$`)

func tokenEndpoint(issuer string) (string, error) {
	u, err := url.Parse(issuer)
	if err != nil {
		return "", benchmarkError("invalid_issuer")
	}
	host := strings.ToLower(u.Hostname())
	ip := net.ParseIP(host)
	local := host == "localhost" || strings.HasSuffix(host, ".localhost") || host == "keycloak" || host == "app-keycloak" || (ip != nil && ip.IsLoopback())
	if !local || (u.Scheme != "http" && u.Scheme != "https") || u.User != nil || u.RawQuery != "" || u.ForceQuery || u.Fragment != "" || u.RawPath != "" || !realmPath.MatchString(u.Path) {
		return "", benchmarkError("invalid_issuer")
	}
	return issuer + "/protocol/openid-connect/token", nil
}

func readCredentials(path string, count int) (credentialFile, error) {
	var c credentialFile
	f, err := os.Open(path)
	if err != nil {
		return c, benchmarkError("credentials_unreadable")
	}
	defer f.Close()
	s, err := f.Stat()
	if err != nil || !s.Mode().IsRegular() || s.Mode().Perm()&0077 != 0 || s.Size() > 4*1024*1024 {
		return c, benchmarkError("credentials_require_private_regular_file")
	}
	d := json.NewDecoder(io.LimitReader(f, 4*1024*1024+1))
	d.DisallowUnknownFields()
	if d.Decode(&c) != nil || d.Decode(new(any)) != io.EOF || c.SchemaVersion != 1 || c.ClientID == "" || c.ClientSecret == "" || len(c.Users) < count {
		return credentialFile{}, benchmarkError("invalid_or_insufficient_credentials")
	}
	if _, err := tokenEndpoint(c.Issuer); err != nil {
		return credentialFile{}, err
	}
	seen := map[string]bool{}
	for _, u := range c.Users[:count] {
		if u.Username == "" || u.Password == "" || seen[u.Username] {
			return credentialFile{}, benchmarkError("invalid_or_duplicate_identity")
		}
		seen[u.Username] = true
	}
	return c, nil
}

type authRecord struct {
	Kind       string `json:"kind"`
	IdentityID string `json:"identity_id"`
	Operation  string `json:"operation"`
	phaseMeasurement
}

// Tokens belong to one identity. The gate also protects rotating refresh tokens
// when multiple conversations share an identity; failures are sticky, never a login retry.
type benchmarkIdentity struct {
	gate                                chan struct{}
	client                              *http.Client
	endpoint, clientID, clientSecret    string
	access, refresh, subject, pseudonym string
	refreshAt                           time.Time
	timeout                             time.Duration
	failure                             error
	record                              func(authRecord)
}

func (a *benchmarkIdentity) exchange(ctx context.Context, values url.Values, operation string) (p phaseMeasurement, err error) {
	p.StartedAt = time.Now()
	defer func() {
		p.finish(err)
		if a.record != nil {
			a.record(authRecord{Kind: "auth", IdentityID: a.pseudonym, Operation: operation, phaseMeasurement: p})
		}
	}()
	ctx, cancel := context.WithTimeout(ctx, a.timeout)
	defer cancel()
	values.Set("client_id", a.clientID)
	values.Set("client_secret", a.clientSecret)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, a.endpoint, strings.NewReader(values.Encode()))
	if err != nil {
		return p, benchmarkError("invalid_issuer")
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	injectTurnTrace(req)
	resp, err := a.client.Do(req)
	if err != nil {
		return p, safeAuthError(err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return p, benchmarkError(fmt.Sprintf("auth_http_%d", resp.StatusCode))
	}
	data, err := io.ReadAll(io.LimitReader(resp.Body, 1024*1024+1))
	if err != nil {
		return p, safeAuthError(err)
	}
	var tok struct {
		Access  string `json:"access_token"`
		Refresh string `json:"refresh_token"`
		Expires int64  `json:"expires_in"`
		Type    string `json:"token_type"`
	}
	if len(data) > 1024*1024 || json.Unmarshal(data, &tok) != nil || tok.Access == "" || tok.Refresh == "" || tok.Expires < 1 || tok.Expires > 86400 || !strings.EqualFold(tok.Type, "bearer") || strings.ContainsAny(tok.Access, "\r\n") {
		return p, benchmarkError("invalid_token_response")
	}
	// Attribution only: this decoding never verifies a JWT or grants authority.
	parts := strings.Split(tok.Access, ".")
	var claims struct {
		Sub string `json:"sub"`
	}
	if len(parts) != 3 {
		return p, benchmarkError("missing_token_subject")
	}
	payload, decodeErr := base64.RawURLEncoding.DecodeString(parts[1])
	if decodeErr != nil || json.Unmarshal(payload, &claims) != nil || claims.Sub == "" || len(claims.Sub) > 1024 {
		return p, benchmarkError("missing_token_subject")
	}
	if a.subject != "" && a.subject != claims.Sub {
		return p, benchmarkError("changed_token_subject")
	}
	lifetime := time.Duration(tok.Expires) * time.Second
	margin := lifetime / 10
	if margin > 30*time.Second {
		margin = 30 * time.Second
	}
	// Use request start, not response arrival, so network time cannot extend validity.
	next := p.StartedAt.Add(lifetime - margin)
	if !next.After(time.Now()) {
		return p, benchmarkError("expired_token_response")
	}
	if a.subject == "" {
		a.subject = claims.Sub
	}
	a.access, a.refresh, a.refreshAt = tok.Access, tok.Refresh, next
	return p, nil
}

func safeAuthError(err error) error { return benchmarkError(classifyError(err)) }

func (a *benchmarkIdentity) token(ctx context.Context) (string, *phaseMeasurement, error) {
	select {
	case a.gate <- struct{}{}:
	case <-ctx.Done():
		return "", nil, ctx.Err()
	}
	defer func() { <-a.gate }()
	if a.failure != nil {
		return "", nil, a.failure
	}
	if time.Now().Before(a.refreshAt) {
		return a.access, nil, nil
	}
	p, err := a.exchange(ctx, url.Values{"grant_type": {"refresh_token"}, "refresh_token": {a.refresh}}, "refresh")
	if err != nil {
		a.failure = err
		return "", &p, err
	}
	return a.access, &p, nil
}

func acquireIdentities(ctx context.Context, cfg config, credentials credentialFile, count int, campaign string, client *http.Client, record func(authRecord)) ([]*benchmarkIdentity, error) {
	endpoint, err := tokenEndpoint(credentials.Issuer)
	if err != nil {
		return nil, err
	}
	identities := make([]*benchmarkIdentity, count)
	errors := make([]error, count)
	jobs := make(chan int)
	var wg sync.WaitGroup
	workers := cfg.AuthConcurrency
	if workers > count {
		workers = count
	}
	for worker := 0; worker < workers; worker++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := range jobs {
				a := &benchmarkIdentity{gate: make(chan struct{}, 1), client: client, endpoint: endpoint, clientID: credentials.ClientID, clientSecret: credentials.ClientSecret, timeout: cfg.Timeout, pseudonym: pseudonym(campaign, fmt.Sprint(i)), record: record}
				u := credentials.Users[i]
				_, errors[i] = a.exchange(ctx, url.Values{"grant_type": {"password"}, "username": {u.Username}, "password": {u.Password}, "scope": {"openid"}}, "acquire")
				identities[i] = a
			}
		}()
	}
	for i := 0; i < count; i++ {
		jobs <- i
	}
	close(jobs)
	wg.Wait()
	seen := map[string]bool{}
	for i, a := range identities {
		if errors[i] != nil {
			return nil, errors[i]
		}
		if seen[a.subject] {
			return nil, benchmarkError("duplicate_token_subject")
		}
		seen[a.subject] = true
	}
	return identities, nil
}

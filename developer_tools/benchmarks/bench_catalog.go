package main

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"sort"
	"strings"
	"time"
)

type benchSpace struct {
	ID           string   `json:"id"`
	Kind         string   `json:"kind"`
	Name         string   `json:"name"`
	Organization string   `json:"organization_id"`
	Path         []string `json:"path"`
	Label        string   `json:"-"`
}
type benchAgent struct {
	ID     string `json:"agent_instance_id"`
	Name   string `json:"display_name"`
	Status string `json:"status"`
}

type benchCatalog struct {
	adapter  *weaverAdapter
	identity *benchmarkIdentity
}

func (c benchCatalog) request(ctx context.Context, method, path string, out any) error {
	ctx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	token, _, err := c.identity.token(ctx)
	if err != nil {
		return err
	}
	c.adapter.cfg.Token = token
	_, err = c.adapter.json(ctx, method, c.adapter.cfg.ControlPlanePath+path, nil, out)
	if err != nil {
		return fmt.Errorf("Fred: %s", classifyError(err))
	}
	return nil
}
func (c benchCatalog) spaces(ctx context.Context) ([]benchSpace, error) {
	var all []benchSpace
	if err := c.request(ctx, http.MethodGet, "/me/spaces", &all); err != nil {
		return nil, err
	}
	names := map[string]string{}
	for _, s := range all {
		names[s.ID] = s.Name
	}
	var spaces []benchSpace
	for _, s := range all {
		if s.Kind != "team" && s.Kind != "project" && s.Kind != "personal" {
			continue
		}
		if !canonicalUUID.MatchString(s.ID) {
			return nil, fmt.Errorf("invalid Fred space")
		}
		parts := []string{}
		seen := map[string]bool{}
		for _, id := range append([]string{s.Organization}, s.Path...) {
			if id != s.ID && names[id] != "" && !seen[id] {
				parts = append(parts, names[id])
				seen[id] = true
			}
		}
		name := s.Name
		if s.Kind == "personal" && (name == "" || canonicalUUID.MatchString(name)) {
			name = "Personal space"
		}
		parts = append(parts, name)
		s.Label = strings.Join(parts, " / ")
		if s.Kind == "personal" {
			s.Label += " (personal)"
		}
		spaces = append(spaces, s)
	}
	sort.SliceStable(spaces, func(i, j int) bool { return spaces[i].Label < spaces[j].Label })
	return spaces, nil
}
func (c benchCatalog) agents(ctx context.Context, space string) ([]benchAgent, error) {
	if !canonicalUUID.MatchString(space) {
		return nil, fmt.Errorf("invalid Fred space")
	}
	var agents []benchAgent
	cursor, seen := "", map[string]bool{}
	for pages := 0; pages < 100; pages++ {
		var page struct {
			Items []benchAgent `json:"items"`
			Next  string       `json:"next_cursor"`
		}
		path := "/spaces/" + space + "/agent-instances"
		if cursor != "" {
			path += "?after=" + url.QueryEscape(cursor)
		}
		if err := c.request(ctx, http.MethodGet, path, &page); err != nil {
			return nil, err
		}
		for _, a := range page.Items {
			if !canonicalUUID.MatchString(a.ID) {
				return nil, fmt.Errorf("invalid Fred agent")
			}
			if a.Status == "enabled" {
				agents = append(agents, a)
			}
		}
		if page.Next == "" {
			sort.SliceStable(agents, func(i, j int) bool { return agents[i].Name < agents[j].Name })
			return agents, nil
		}
		if seen[page.Next] {
			return nil, fmt.Errorf("inconsistent agent pagination")
		}
		seen[page.Next], cursor = true, page.Next
	}
	return nil, fmt.Errorf("agent catalog exceeds 100 pages")
}

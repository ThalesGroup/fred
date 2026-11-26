---
schema: 1
title: "Send a custom authentication header to the web research proxy"
impact: minor
configuration: production
configuration_reason: "Adds optional web_research.proxy_header_name and proxy_header_env for forward proxies that authenticate with a token header instead of Basic."
---

## Applicability

Deployments where web research goes through a forward proxy that expects a
token in a custom request header rather than Basic `Proxy-Authorization`.
Other deployments need no action.

## Prerequisites

`web_research.proxy_url` is configured and the proxy's header name and token
are known.

## Configuration

```yaml
web_research:
  proxy_url: http://relay.dmz.example:443
  proxy_header_name: X-Proxy-Token        # letters, digits and dashes
  proxy_header_env: WEB_RESEARCH_PROXY_HEADER
```

Set `WEB_RESEARCH_PROXY_HEADER` in the Fred Agents secret environment (chart:
`dotenv.WEB_RESEARCH_PROXY_HEADER`). Both fields go together and require
`proxy_url`. The header is sent to the proxy only, never to target sites, and
can be combined with `proxy_auth_env`.

## Upgrade

Deploy Fred normally, then add the configuration above where needed.

## Validation

A web search through the proxy succeeds instead of the proxy answering 407 or
403 to the tunnel. Fred Agents refuses to start if `proxy_header_env` names an
empty variable.

## Rollback

Remove both fields and the secret, then roll back normally. No data migration.

## Limitations

One header only. The value is a static secret; rotate it by updating the
secret and restarting Fred Agents.

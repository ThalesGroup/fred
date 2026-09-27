# Workload Secret Rotation

Each backend authenticates its outbound service calls with a client-credentials
secret. The chart names the environment variable in `security.m2m.secret_env_var`
and renders the value into the deployment's Secret, which the pod mounts as the
env file it loads into its process environment at startup.

## Procedure

1. **Open a rotation grace at the identity provider.** Create the new client
   secret with the provider's rotated-secret grace, so the previous secret keeps
   issuing tokens until the grace expires.
2. **Store the new secret.** Change the value in the deployment's secret facility
   — the chart's `dotenv` entry for that workload, or the external secret store
   that populates it.
3. **Roll the pods.** Restart every workload that reads the secret.
4. **Let the grace expire.** Once all readers are restarted and healthy, retire
   the previous secret.

The grace exists to cover step 3: between the first and the last restarted pod,
both secrets are in use at the same time.

## Why the restart is required

The token provider reads the environment variable once, when it is constructed,
and keeps that value for its lifetime. It never re-reads the variable — not on
the next refresh, and not after a refresh fails. The env file is read into that
environment once at start, so a rotated secret reaches a running pod only through
a restart.

A failed acquisition leaves the captured secret unchanged. The next caller can
retry immediately with that value. A pod that starts with an unset or empty
secret refuses acquisition until restarted with the corrected configuration.

## Work in flight

Steps 1 and 2 do not interrupt running turns. An issued token stays valid until
its own expiry, independent of the secret that minted it, so a turn already
running finishes on the token it holds. A refresh that lands before the restart
still uses the captured previous secret, which the grace keeps accepted. After
the restart, the provider fetches with the new secret.

## Context

The reusable `Docker-images.yml` workflow builds every `.github/docker-images.json` entry in a pull request and publishes only the selected entries on `swift` pushes and release tags. The pre-merge Buildx build currently has no local image output, so a scanner cannot inspect its result.

## Goals / Non-Goals

**Goals:**
- Scan the exact image built by each publishable pull request matrix job without registry credentials; `ws-bench` remains build-only.
- Distinguish vulnerability findings from build or scanner failures.

**Non-Goals:**
- Block merging on vulnerability findings or scan release publication jobs.
- Change the image manifest or Dockerfiles.

## Decisions

- The image manifest marks `ws-bench` with `scan: false`; matrix resolution defaults all other images to scanning. Load only scan-enabled Buildx output from `pull_request` runs into the runner Docker store under a local tag; release pushes never load or scan images. This preserves the existing build recipe and release push path. A separate rebuild would waste time and could scan a different artifact.
- Run the versioned Trivy action against the scan-enabled local tags, limited to critical OS and library vulnerabilities. Produce JSON so a following step can distinguish an empty result from a failed scan. `exit-code: 0` keeps findings advisory; an action failure still fails the job.
- Count findings from Trivy JSON and emit one GitHub warning annotation per affected image. Add a short job summary and upload the full JSON report for review. A warning annotation is visible without adding PR write permissions or a comment bot.

## Risks / Trade-offs

- Loading images and fetching Trivy's database increases PR duration and runner disk use. Existing matrix parallelism and Trivy caching limit the cost.
- Vulnerability database changes can change findings without code changes. The JSON report records what each run found.
- Docker's local image exporter supports the current single-platform build; a future multi-platform build would need a different export strategy.

## Migration Plan

The next pull request run exercises the scan automatically. Reverting the workflow change restores the previous build-only check. No deployment migration is needed.

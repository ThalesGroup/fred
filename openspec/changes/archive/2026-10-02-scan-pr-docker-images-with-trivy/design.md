## Context

The reusable `Docker-images.yml` workflow builds every `.github/docker-images.json` entry in a pull request and publishes only the selected entries on `swift` pushes and release tags. The pre-merge Buildx build currently has no local image output, so a scanner cannot inspect its result.

## Goals / Non-Goals

**Goals:**
- Scan the exact image built by each publishable pull request matrix job without registry credentials; `ws-bench` remains build-only.
- Distinguish vulnerability findings from build or scanner failures.

**Non-Goals:**
- Block merging on vulnerability findings or scan release publication jobs.
- Add misconfiguration, secret, or license policy checks; this change measures CVEs.
- Scan Python lockfiles or intermediate build stages.
- Change the image manifest or Dockerfiles.

## Decisions

- The image manifest marks `ws-bench` with `scan: false`; matrix resolution defaults all other images to scanning. Load scan-enabled Buildx output from every pull request build into the runner Docker store under a local tag; release pushes never load or scan images. This preserves the existing build recipe and release push path.
- Run the versioned Trivy action against final images with all severities and all package entries in JSON. Summaries count critical findings separately. `exit-code: 0` keeps findings advisory; an action failure still fails the job.
- Count findings from Trivy JSON and emit one GitHub warning annotation per affected image. Add a short job summary and upload the full JSON report for review. A warning annotation is visible without adding PR write permissions or a comment bot.
- Show dedicated `Scan Trivy / <image>` checks for the four final images. Build jobs scan and upload JSON artifacts; result jobs print every finding in their logs and emit warnings and concise summaries. This makes the result visible in GitHub's top-level job list without transferring large Docker images. GitHub Actions has no warning job conclusion, so findings leave checks successful with warning annotations; scanner or report failures fail the workflow.
- Add a `Scan Trivy / frontend dependencies` job for the npm lockfile with development dependencies included. It publishes the same all-severity log and JSON inventory, and verifies the lockfile was actually inventoried. Print findings from CRITICAL through UNKNOWN in every Trivy job log and summary.
- Remove the changed-file filter. Every pull request builds all five images and scans the four scan-enabled final images after the Docker builds. Release publication remains build/push only.

## Risks / Trade-offs

- Loading images and fetching Trivy's database increases PR duration and runner disk use. Existing matrix parallelism and Trivy caching limit the cost.
- Vulnerability database changes can change findings without code changes. The JSON report records what each run found.
- Pull request scans cannot report newly disclosed CVEs until a pull request runs; this workflow does not run on a schedule.
- The final frontend image contains static JavaScript assets, not npm package metadata. The separate npm lockfile scan catches declared dependencies but does not identify precisely which packages are present in the shipped bundle. Intermediate build-stage packages are outside scope.
- Docker's local image exporter supports the current single-platform build; a future multi-platform build would need a different export strategy.
- Dedicated result jobs wait for the whole build matrix before starting. This adds short artifact-download jobs to scan-triggering PRs but avoids a second image build.

## Migration Plan

The next pull request run exercises the scan automatically. Reverting the workflow change restores the previous build-only check. No deployment migration is needed.

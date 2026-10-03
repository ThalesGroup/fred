## Why

Every pull-request push builds all five Docker images, even for a documentation or frontend-only change. The knowledge-flow image is by far the most expensive and is rebuilt for changes that cannot reach it. GitHub issue #2920.

## What Changes

- The pull-request Docker check selects images from the PR's changed paths against its merge base, using rules held in `.github/docker-images.json`, the single image inventory.
- Documentation (`docs/**`, `openspec/**`, root `*.md`) builds no image; `apps/frontend/**` builds only the frontend; `libs/frontend/**` builds no image.
- The knowledge-flow image builds only when one of its declared inputs changes. Every other path builds every other image (general case).
- Release builds and a manual run of the check still build every image. An empty selection skips the build job cleanly.

## Capabilities

### New Capabilities

- `docker-image-ci-selection`: which Docker images a pull request builds, and when every image is built.

### Modified Capabilities

None.

## Impact

`.github/docker-images.json`, `.github/workflows/Docker-images.yml`, `.github/workflows/Check-docker-images.yml`, a new `scripts/select_docker_images.py` with its tests, and the PR migration note. No image content, release publication or runtime behavior changes.

## Why

Pull requests build the production Docker images but do not check those built images for known vulnerabilities. Critical findings should be visible during review without turning the existing build gate into a vulnerability policy gate.

## What Changes

- Scan the four publishable images in the existing pull request Docker matrix with Trivy after the build; keep building `ws-bench` with an explicit scan exception in the image manifest.
- Emit a GitHub Actions warning and job summary for critical OS or library vulnerabilities while allowing the job to succeed.
- Preserve hard failures for image build and scanner execution errors, and leave release publishing unchanged.

## Capabilities

This is CI tooling only. It does not change a shipped product capability, so this change skips delta specs.

## Impact

- `.github/workflows/Docker-images.yml` and the existing pull request image build workflow.
- GitHub Actions runner time, Docker image loading, and Trivy vulnerability database downloads.
- No application API, runtime, or deployment configuration changes.

## Why

Fred agents cannot execute Bash or Python in a security boundary separate from the agent pod. A portable execution contract is needed before code tools can be offered on Kubernetes or Docker without exposing the agent runtime to host or cluster privileges.

Tracking issue: #3226.

## What Changes

- Add an admin-gated `code_sandbox` capability with a single Bash/Python tool and a typed SDK execution port.
- Add a separately deployed broker with interchangeable Kubernetes Job and Docker backends. The broker selects an explicitly configured Kata or gVisor runtime and refuses to run when its isolation prerequisites are absent.
- Bound code size, execution time, output, CPU, memory, scratch storage, and concurrent work. Disable network access and remove every execution resource after completion or cancellation.
- Provide Kubernetes and Docker deployment examples and a cluster preflight. The prototype is not evidence that a particular CNI enforces `NetworkPolicy` or that s3ns nodes support KVM.

## Capabilities

### New Capabilities

- `agent-code-sandbox`: Isolated Bash/Python execution exposed as an agent capability through a portable sandbox backend contract.

### Modified Capabilities

None.

## Impact

- `fred-sdk` runtime port, one first-party capability package, `fred-runtime` service binding, and `fred-agents` package registration.
- New standalone broker process and operator examples for Kubernetes and Docker. No database migration or frontend API is required for the prototype.

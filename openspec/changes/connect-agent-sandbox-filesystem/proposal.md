## Why

Code execution and agent files currently live in separate spaces. A Deep or ReAct agent cannot use a published skill's script or analyze an authorized source file with Python while preserving the sandbox's isolation boundary.

## What Changes

- Expose one conversation-scoped logical workspace to Deep and ReAct with read-only `/skills` and `/inputs`, and writable `/work`. Keep Deep's existing conversation scratchpad and `/.deep` artifacts intact.
- Mount authorized source views into the isolated workload. Serve the conversation's readable team or personal corpus documents and its retained attachments on demand through read-only directories, without a selection tool, a guest scratch copy, or backing storage credentials in guest code.
- Run platform skill scripts and agent-generated Bash/Python against the same isolated conversation workload. Mark skills that require sandbox execution and make the interface able to accept future user-published skills without adding user skill import or management in this change.
- Preserve all existing skill discovery, instruction loading, document reading and tabular tools when `code_sandbox` is disabled. Skills requiring execution SHALL explain that their required capability is unavailable.
- Bind user, team, conversation, and file provenance privately; filter directory listings and recheck each read, rejecting unsafe paths, oversized files, unsupported types, and missing authorization.
- Keep the existing operator-approved isolation runtime, capacity limits, idle expiry, and admin gate for every execution path, including Deep native `execute` if exposed.
- Provision workloads only when a conversation first executes code. Remove ready capacity controls and keep the SIG Agent Sandbox claim pool at zero replicas.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-code-sandbox`: Authorized read-only source mounts and execution against a conversation workspace shared across supported runtimes.
- `platform-agent-skills`: A published skill may contain approved script files that agents can use only through the sandbox capability.
- `tabular-chat-attachments`: A conversation attachment's original file may be read through a scoped sandbox mount under the existing conversation and uploader scope.

## Impact

Touches `fred-sdk` ports, `fred-runtime` Deep/ReAct filesystem and skills integration, the `code_sandbox` capability, the sandbox broker and its Kubernetes/Docker/SIG backends, an operator-provided filesystem mount driver and authorized file gateway, attachment/corpus adapters, targeted tests, operator documentation and the runtime execution contract. The broker remains the only component with workload control privileges.

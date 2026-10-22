import json

import pytest
from fred_sdk.contracts.sandbox import SandboxError, SandboxRequest
from sandbox_broker.agent_sandbox_backend import AgentSandboxBackend
from sandbox_broker.command import CommandResult, CommandTimeout
from sandbox_broker.config import BrokerSettings
from sandbox_broker.docker_backend import DockerBackend
from sandbox_broker.kubernetes_backend import KubernetesBackend


def settings(backend="docker", **overrides):
    values = dict(
        backend=backend,
        isolation="kata",
        runtime_name="kata-qemu",
        image="python@sha256:" + "a" * 64,
        token="x" * 32,
        network_policy_verified=backend != "docker",
        pid_limit_verified=backend != "docker",
    )
    values.update(overrides)
    return BrokerSettings(**values)


class DockerRunner:
    def __init__(self, runtime="kata-runtime", timeout=False):
        self.calls = []
        self.runtime = runtime
        self.timeout = timeout

    async def run(self, args, *, timeout, output_limit=65536, input_data=None):
        self.calls.append((list(args), input_data))
        if args[:2] == ["docker", "info"]:
            return CommandResult(
                0, json.dumps({"kata-qemu": {"path": self.runtime}}), ""
            )
        if args[:2] == ["docker", "run"]:
            return CommandResult(0, "container-id", "")
        if args[:2] == ["docker", "exec"]:
            if self.timeout:
                raise CommandTimeout
            return CommandResult(0, "42\n", "", truncated=True)
        return CommandResult(0, "", "")


@pytest.mark.asyncio
async def test_docker_requires_isolated_runtime_and_hardens_container() -> None:
    runner = DockerRunner()
    backend = DockerBackend(settings(), runner)
    await backend.preflight()
    lease = await backend.prepare()
    result = await backend.execute(
        lease, SandboxRequest(language="python", code="print(42)")
    )
    await backend.dispose(lease)
    args = next(args for args, _ in runner.calls if args[:2] == ["docker", "run"])
    for option in (
        "--runtime",
        "kata-qemu",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--pids-limit",
        "--memory",
        "--memory-swap",
        "--tmpfs",
    ):
        assert option in args
    assert result.stdout == "42\n" and result.truncated
    assert runner.calls[-1][0][:3] == ["docker", "rm", "--force"]
    with pytest.raises(SandboxError, match="runtime_unavailable"):
        await DockerBackend(settings(), DockerRunner("runc")).preflight()


@pytest.mark.asyncio
async def test_docker_timeout_still_allows_forced_cleanup() -> None:
    runner = DockerRunner(timeout=True)
    backend = DockerBackend(settings(), runner)
    lease = await backend.prepare()
    assert (
        await backend.execute(lease, SandboxRequest(language="bash", code="sleep 99"))
    ).timed_out
    await backend.dispose(lease)
    assert runner.calls[-1][0][:3] == ["docker", "rm", "--force"]


class KubeRunner:
    def __init__(self, policy=True, extra_policy=False):
        self.calls = []
        self.policy = policy
        self.extra_policy = extra_policy
        self.manifest = None

    async def run(self, args, *, timeout, output_limit=65536, input_data=None):
        self.calls.append(list(args))
        if input_data:
            self.manifest = json.loads(input_data)
            return CommandResult(0, "created", "")
        if "runtimeclass" in args:
            return CommandResult(0, json.dumps({"handler": "kata-qemu"}), "")
        if (
            "namespace" in args
            and "networkpolicy" not in args
            and "pods" not in args
            and "get" in args
            and "fred-sandbox" in args
            and "-o" in args
            and args[1] == "get"
        ):
            return CommandResult(
                0,
                json.dumps(
                    {
                        "metadata": {
                            "labels": {
                                "pod-security.kubernetes.io/enforce": "restricted"
                            }
                        }
                    }
                ),
                "",
            )
        if "networkpolicies" in args:
            spec = {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]}
            if not self.policy:
                spec["egress"] = [{}]
            items = [{"metadata": {"name": "fred-sandbox-deny-all"}, "spec": spec}]
            if self.extra_policy:
                items.append({"metadata": {"name": "allow-egress"}, "spec": {}})
            return CommandResult(0, json.dumps({"items": items}), "")
        if "pods" in args:
            return CommandResult(
                0,
                json.dumps(
                    {
                        "items": [
                            {
                                "metadata": {"name": "fred-sbx-pod"},
                                "status": {
                                    "conditions": [{"type": "Ready", "status": "True"}]
                                },
                            }
                        ]
                    }
                ),
                "",
            )
        if "exec" in args:
            return CommandResult(0, "ok\n", "")
        return CommandResult(0, "", "")


@pytest.mark.asyncio
async def test_kubernetes_preflight_manifest_and_single_use_lifecycle() -> None:
    runner = KubeRunner()
    backend = KubernetesBackend(settings("kubernetes"), runner)
    await backend.preflight()
    lease = await backend.prepare()
    result = await backend.execute(
        lease, SandboxRequest(language="bash", code="echo ok")
    )
    await backend.dispose(lease)
    job = runner.manifest
    assert job["kind"] == "Job"
    assert job["spec"]["ttlSecondsAfterFinished"] == 60
    pod = job["spec"]["template"]["spec"]
    assert pod["runtimeClassName"] == "kata-qemu"
    assert pod["automountServiceAccountToken"] is False
    assert not pod["hostNetwork"]
    container = pod["containers"][0]
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
    assert job["spec"]["activeDeadlineSeconds"] > 3600
    assert result.stdout == "ok\n"
    assert "delete" in runner.calls[-1]
    assert "--wait=true" in runner.calls[-1]


@pytest.mark.asyncio
async def test_kubernetes_rejects_permissive_policy() -> None:
    backend = KubernetesBackend(settings("kubernetes"), KubeRunner(policy=False))
    with pytest.raises(SandboxError, match="policy_unavailable"):
        await backend.preflight()


@pytest.mark.asyncio
async def test_kubernetes_rejects_additional_network_policy() -> None:
    backend = KubernetesBackend(settings("kubernetes"), KubeRunner(extra_policy=True))
    with pytest.raises(SandboxError, match="policy_unavailable"):
        await backend.preflight()


class AgentRunner(KubeRunner):
    def __init__(
        self,
        *,
        bad_image=False,
        wait_fails=False,
        bad_pod_env=False,
        template_changes=False,
        ready_replicas=0,
        cold_fallback=False,
    ):
        super().__init__()
        self.bad_image = bad_image
        self.wait_fails = wait_fails
        self.bad_pod_env = bad_pod_env
        self.template_changes = template_changes
        self.ready_replicas = ready_replicas
        self.cold_fallback = cold_fallback
        self.template_reads = 0
        self.claim_name = ""

    async def run(self, args, *, timeout, output_limit=65536, input_data=None):
        if input_data:
            self.claim_name = json.loads(input_data)["metadata"]["name"]
        if "sandboxwarmpool" in args:
            return CommandResult(
                0,
                json.dumps(
                    {
                        "metadata": {"generation": 1},
                        "spec": {
                            "replicas": self.ready_replicas,
                            "sandboxTemplateRef": {"name": "fred-code"},
                            "updateStrategy": {"type": "Recreate"},
                        },
                        "status": {
                            "readyReplicas": self.ready_replicas,
                            "observedGeneration": 1,
                        },
                    }
                ),
                "",
            )
        if "sandboxtemplate" in args:
            self.template_reads += 1
            pod = KubernetesBackend(settings("kubernetes"), self).job_manifest("x")[
                "spec"
            ]["template"]["spec"]
            if self.bad_image:
                pod["containers"][0]["image"] = "unapproved:latest"
            if self.template_changes and self.template_reads > 1:
                pod["containers"][0]["envFrom"] = [
                    {"secretRef": {"name": "platform-secret"}}
                ]
            return CommandResult(
                0,
                json.dumps(
                    {
                        "spec": {
                            "networkPolicyManagement": "Unmanaged",
                            "podTemplate": {"spec": pod},
                        }
                    }
                ),
                "",
            )
        if "wait" in args and self.wait_fails:
            self.calls.append(list(args))
            return CommandResult(1, "", "not ready")
        if "sandboxclaim" in args and "get" in args:
            return CommandResult(
                0,
                json.dumps(
                    {
                        "metadata": {"creationTimestamp": "2026-10-22T00:00:01Z"},
                        "status": {"sandbox": {"name": self.claim_name}},
                    }
                ),
                "",
            )
        if "sandbox" in args and "get" in args:
            launch_type = "cold" if self.cold_fallback else "warm"
            return CommandResult(
                0,
                json.dumps(
                    {
                        "metadata": {
                            "labels": {"agents.x-k8s.io/launch-type": launch_type}
                        }
                    }
                ),
                "",
            )
        if "pod" in args and "get" in args:
            pod_spec = KubernetesBackend(settings("kubernetes"), self).job_manifest(
                "x"
            )["spec"]["template"]["spec"]
            for omitted_false in ("hostNetwork", "hostPID", "hostIPC"):
                pod_spec.pop(omitted_false)
            if self.bad_pod_env:
                pod_spec["containers"][0]["envFrom"] = [
                    {"secretRef": {"name": "platform-secret"}}
                ]
            return CommandResult(
                0,
                json.dumps(
                    {
                        "metadata": {
                            "ownerReferences": [{"name": self.claim_name}],
                            "creationTimestamp": (
                                "2026-10-22T00:00:02Z"
                                if self.cold_fallback
                                else "2026-10-22T00:00:00Z"
                            ),
                        },
                        "spec": pod_spec,
                    }
                ),
                "",
            )
        return await super().run(
            args, timeout=timeout, output_limit=output_limit, input_data=input_data
        )


@pytest.mark.asyncio
async def test_agent_sandbox_claim_lifecycle_and_expiry() -> None:
    runner = AgentRunner()
    backend = AgentSandboxBackend(settings("agent_sandbox"), runner)
    await backend.preflight()
    lease = await backend.prepare()
    result = await backend.execute(
        lease, SandboxRequest(language="bash", code="echo ok")
    )
    await backend.dispose(lease)
    assert runner.manifest["kind"] == "SandboxClaim"
    assert runner.manifest["spec"]["warmPoolRef"]["name"] == "fred-code"
    assert runner.manifest["spec"]["lifecycle"]["shutdownPolicy"] == "DeleteForeground"
    assert "shutdownTime" in runner.manifest["spec"]["lifecycle"]
    assert result.stdout == "ok\n"
    assert "sandboxclaim" in runner.calls[-1]
    assert "--cascade=foreground" in runner.calls[-1]


@pytest.mark.asyncio
async def test_agent_sandbox_rejects_template_mismatch() -> None:
    backend = AgentSandboxBackend(
        settings("agent_sandbox"), AgentRunner(bad_image=True)
    )
    with pytest.raises(SandboxError, match="policy_unavailable"):
        await backend.preflight()


@pytest.mark.asyncio
async def test_agent_sandbox_cleans_failed_claim() -> None:
    runner = AgentRunner(wait_fails=True)
    backend = AgentSandboxBackend(settings("agent_sandbox"), runner)
    with pytest.raises(SandboxError, match="backend_failed"):
        await backend.prepare()
    assert "delete" in runner.calls[-1]


@pytest.mark.asyncio
async def test_agent_sandbox_rechecks_template_before_claim() -> None:
    runner = AgentRunner(template_changes=True)
    backend = AgentSandboxBackend(settings("agent_sandbox"), runner)
    await backend.preflight()
    with pytest.raises(SandboxError, match="policy_unavailable"):
        await backend.prepare()
    assert runner.manifest is None


@pytest.mark.asyncio
async def test_agent_sandbox_rejects_injected_secret_on_claimed_pod() -> None:
    runner = AgentRunner(bad_pod_env=True)
    backend = AgentSandboxBackend(settings("agent_sandbox"), runner)
    with pytest.raises(SandboxError, match="policy_unavailable"):
        await backend.prepare()
    assert "delete" in runner.calls[-1]
    assert "sandboxclaim" in runner.calls[-1]


@pytest.mark.asyncio
async def test_agent_sandbox_ready_mode_rejects_cold_fallback() -> None:
    runner = AgentRunner(ready_replicas=1, cold_fallback=True)
    backend = AgentSandboxBackend(
        settings("agent_sandbox", cold_start_on_miss=False), runner
    )
    with pytest.raises(SandboxError, match="busy"):
        await backend.prepare()
    assert "delete" in runner.calls[-1]


@pytest.mark.asyncio
async def test_agent_sandbox_ready_mode_accepts_preexisting_pod() -> None:
    runner = AgentRunner(ready_replicas=1)
    backend = AgentSandboxBackend(
        settings("agent_sandbox", cold_start_on_miss=False), runner
    )
    lease = await backend.prepare()
    assert lease.target == runner.claim_name
    await backend.dispose(lease)

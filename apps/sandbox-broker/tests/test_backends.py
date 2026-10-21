import json

import pytest
from fred_sdk.contracts.sandbox import SandboxError, SandboxRequest
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
        network_policy_verified=backend == "kubernetes",
        pid_limit_verified=backend == "kubernetes",
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

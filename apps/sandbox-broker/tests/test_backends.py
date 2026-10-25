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


def test_file_revoke_url_accepts_only_trusted_internal_http() -> None:
    mounted = dict(
        mount_provider="rclone_csi",
        file_gateway_url="https://files.example/knowledge-flow/v1/sandbox-mount",
        file_gateway_secret="s" * 32,
        file_storage_class="fred-sandbox-webdav",
    )
    internal = "http://knowledge-flow-backend.fred.svc.cluster.local:8000/knowledge-flow/v1/sandbox-mount"
    assert (
        settings(
            "agent_sandbox", **mounted, file_gateway_revoke_url=internal
        ).file_gateway_revoke_url
        == internal
    )
    with pytest.raises(ValueError, match="revoke URL"):
        settings(
            "agent_sandbox",
            **mounted,
            file_gateway_revoke_url="http://files.example/knowledge-flow/v1/sandbox-mount",
        )


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
            if self.timeout and args[3] != "python":
                raise CommandTimeout
            return CommandResult(0, "42\n", "", truncated=True)
        return CommandResult(0, "", "")


@pytest.mark.asyncio
async def test_docker_file_volume_stays_outside_guest_credentials() -> None:
    class MountRunner(DockerRunner):
        async def run(self, args, *, timeout, output_limit=65536, input_data=None):
            if args[:2] == ["docker", "plugin"]:
                self.calls.append((list(args), input_data))
                return CommandResult(0, "true\n", "")
            return await super().run(
                args, timeout=timeout, output_limit=output_limit, input_data=input_data
            )

    runner = MountRunner()
    backend = DockerBackend(
        settings(
            mount_provider="rclone_docker",
            file_gateway_url="https://files.example/knowledge-flow/v1/sandbox-mount",
            file_gateway_secret="s" * 32,
            docker_volume_plugin="rclone",
        ),
        runner,
    )
    await backend.preflight()
    lease = await backend.prepare("a" * 64)
    volume = next(
        args for args, _ in runner.calls if args[:3] == ["docker", "volume", "create"]
    )
    run = next(args for args, _ in runner.calls if args[:2] == ["docker", "run"])
    assert "--mount" in run and any("dst=/inputs,readonly" in arg for arg in run)
    assert not any("bearer-token" in arg for arg in run)
    assert any("webdav-bearer-token=" in arg for arg in volume)
    await backend.dispose(lease)
    assert runner.calls[-1][0][:3] == ["docker", "volume", "rm"]


@pytest.mark.asyncio
async def test_docker_mounts_operator_approved_skills_volume_read_only() -> None:
    class SkillsRunner(DockerRunner):
        async def run(self, args, *, timeout, output_limit=65536, input_data=None):
            if args[:3] == ["docker", "volume", "inspect"]:
                self.calls.append((list(args), input_data))
                return CommandResult(
                    0,
                    json.dumps(
                        [
                            {
                                "Labels": {"fred.sandbox/skills": "approved"},
                            }
                        ]
                    ),
                    "",
                )
            return await super().run(
                args, timeout=timeout, output_limit=output_limit, input_data=input_data
            )

    runner = SkillsRunner()
    backend = DockerBackend(settings(skills_volume="fred-platform-skills"), runner)
    await backend.preflight()
    lease = await backend.prepare()
    run = next(args for args, _ in runner.calls if args[:2] == ["docker", "run"])
    assert "type=volume,src=fred-platform-skills,dst=/skills,readonly" in run
    await backend.dispose(lease)


@pytest.mark.asyncio
async def test_docker_recovery_removes_managed_workload_and_input_volume() -> None:
    class RecoveryRunner(DockerRunner):
        async def run(self, args, *, timeout, output_limit=65536, input_data=None):
            if args[:2] == ["docker", "ps"]:
                self.calls.append((list(args), input_data))
                return CommandResult(0, "a" * 64 + "\n", "")
            if args[:3] == ["docker", "volume", "ls"]:
                self.calls.append((list(args), input_data))
                return CommandResult(0, "inputs-fred-sbx-" + "b" * 20 + "\n", "")
            return await super().run(
                args, timeout=timeout, output_limit=output_limit, input_data=input_data
            )

    runner = RecoveryRunner()
    await DockerBackend(settings(), runner).recover()
    assert any(args[:3] == ["docker", "rm", "--force"] for args, _ in runner.calls)
    assert any(args[:3] == ["docker", "volume", "rm"] for args, _ in runner.calls)


@pytest.mark.asyncio
async def test_docker_requires_isolated_runtime_and_hardens_container() -> None:
    runner = DockerRunner()
    backend = DockerBackend(settings(), runner)
    await backend.preflight()
    lease = await backend.prepare()
    result = await backend.execute(lease, SandboxRequest(code="python -c 'print(42)'"))
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
    assert any(
        args[3:] == ["/bin/bash", "-c", "python -c 'print(42)'"]
        for args, _ in runner.calls
        if args[:2] == ["docker", "exec"]
    )
    assert runner.calls[-1][0][:3] == ["docker", "rm", "--force"]
    with pytest.raises(SandboxError, match="runtime_unavailable"):
        await DockerBackend(settings(), DockerRunner("runc")).preflight()


@pytest.mark.asyncio
async def test_docker_timeout_still_allows_forced_cleanup() -> None:
    runner = DockerRunner(timeout=True)
    backend = DockerBackend(settings(), runner)
    lease = await backend.prepare()
    assert (await backend.execute(lease, SandboxRequest(code="sleep 99"))).timed_out
    await backend.dispose(lease)
    assert runner.calls[-1][0][:3] == ["docker", "rm", "--force"]


@pytest.mark.asyncio
async def test_docker_rejects_reuse_when_process_cleanup_fails() -> None:
    class FailedCleanupRunner(DockerRunner):
        async def run(self, args, *, timeout, output_limit=65536, input_data=None):
            if args[:2] == ["docker", "exec"] and args[3:5] == ["python", "-c"]:
                if "os.listdir('/proc')" in args[5]:
                    return CommandResult(1, "", "processes remain")
            return await super().run(
                args, timeout=timeout, output_limit=output_limit, input_data=input_data
            )

    runner = FailedCleanupRunner()
    backend = DockerBackend(settings(), runner)
    lease = await backend.prepare()
    with pytest.raises(SandboxError, match="backend_failed"):
        await backend.execute(lease, SandboxRequest(code="echo finished"))
    await backend.dispose(lease)


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
        if "job" in args and "get" in args:
            return CommandResult(0, json.dumps({"metadata": {"uid": "job-uid"}}), "")
        if "pods" in args:
            pod_spec = self.manifest["spec"]["template"]["spec"]
            return CommandResult(
                0,
                json.dumps(
                    {
                        "items": [
                            {
                                "metadata": {
                                    "name": "fred-sbx-pod",
                                    "ownerReferences": [
                                        {
                                            "kind": "Job",
                                            "name": self.manifest["metadata"]["name"],
                                            "uid": "job-uid",
                                            "controller": True,
                                        }
                                    ],
                                },
                                "spec": pod_spec,
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
async def test_kubernetes_mount_creates_private_secret_and_read_only_pvc() -> None:
    class MountRunner(KubeRunner):
        def __init__(self):
            super().__init__()
            self.manifests = []

        async def run(self, args, *, timeout, output_limit=65536, input_data=None):
            if args[:3] == ["kubectl", "get", "storageclass"]:
                return CommandResult(
                    0,
                    json.dumps(
                        {
                            "provisioner": "rclone.csi.veloxpack.io",
                            "parameters": {
                                "csi.storage.k8s.io/node-publish-secret-name": "${pvc.name}",
                                "csi.storage.k8s.io/node-publish-secret-namespace": "fred-sandbox",
                                "remotePath": "/",
                            },
                            "mountOptions": ["dir-cache-time=1s", "vfs-cache-mode=off"],
                        }
                    ),
                    "",
                )
            if "get" in args and "job" in args:
                return CommandResult(
                    0, json.dumps({"metadata": {"uid": "job-uid"}}), ""
                )
            if input_data:
                self.manifests.append(json.loads(input_data))
            return await super().run(
                args, timeout=timeout, output_limit=output_limit, input_data=input_data
            )

    runner = MountRunner()
    backend = KubernetesBackend(
        settings(
            "kubernetes",
            mount_provider="rclone_csi",
            file_gateway_url="https://files.example/knowledge-flow/v1/sandbox-mount",
            file_gateway_secret="s" * 32,
            file_storage_class="fred-sandbox-webdav",
        ),
        runner,
    )
    await backend.preflight()
    lease = await backend.prepare("a" * 64)
    secret, pvc, job = runner.manifests
    assert (
        secret["kind"] == "Secret"
        and secret["metadata"]["name"] == pvc["metadata"]["name"]
    )
    assert "bearer_token" in secret["stringData"]["configData"]
    assert secret["stringData"]["remote"] == secret["metadata"]["name"]
    assert secret["stringData"]["configData"].startswith(
        f"[{secret['metadata']['name']}]\n"
    )
    assert backend.mount is not None
    await backend.mount.create_secret("fred-sbx-second", "b" * 64)
    second_secret = runner.manifests[-1]
    assert second_secret["stringData"]["remote"] != secret["stringData"]["remote"]
    assert job["kind"] == "Job"
    assert any("patch" in args and "secret" in args for args in runner.calls)
    assert any("patch" in args and "pvc" in args for args in runner.calls)
    pod = job["spec"]["template"]["spec"]
    assert pod["containers"][0]["volumeMounts"][-1] == {
        "name": "inputs",
        "mountPath": "/inputs",
        "readOnly": True,
    }
    assert pod["volumes"][-1]["persistentVolumeClaim"]["readOnly"] is True
    await backend.dispose(lease)


@pytest.mark.asyncio
async def test_kubernetes_mounts_only_approved_skill_claim_read_only() -> None:
    class SkillsRunner(KubeRunner):
        async def run(self, args, *, timeout, output_limit=65536, input_data=None):
            if "get" in args and "pvc" in args:
                return CommandResult(
                    0,
                    json.dumps(
                        {
                            "metadata": {"labels": {"fred.sandbox/skills": "approved"}},
                            "status": {"phase": "Bound"},
                            "spec": {"accessModes": ["ReadOnlyMany"]},
                        }
                    ),
                    "",
                )
            return await super().run(
                args, timeout=timeout, output_limit=output_limit, input_data=input_data
            )

    runner = SkillsRunner()
    backend = KubernetesBackend(
        settings("kubernetes", skills_volume="fred-platform-skills"), runner
    )
    await backend.preflight()
    manifest = backend.job_manifest("fred-sbx-test")
    pod = manifest["spec"]["template"]["spec"]
    assert {"name": "skills", "mountPath": "/skills", "readOnly": True} in pod[
        "containers"
    ][0]["volumeMounts"]
    assert {
        "name": "skills",
        "persistentVolumeClaim": {
            "claimName": "fred-platform-skills",
            "readOnly": True,
        },
    } in pod["volumes"]
    with pytest.raises(SandboxError, match="policy_unavailable"):
        await KubernetesBackend(
            settings("kubernetes", skills_volume="unapproved"), KubeRunner()
        ).preflight()


@pytest.mark.asyncio
async def test_kubernetes_preflight_manifest_and_single_use_lifecycle() -> None:
    runner = KubeRunner()
    backend = KubernetesBackend(settings("kubernetes"), runner)
    await backend.preflight()
    lease = await backend.prepare()
    result = await backend.execute(lease, SandboxRequest(code="echo ok"))
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
    assert any(
        args[-4:] == ["--", "/bin/bash", "-c", "echo ok"]
        for args in runner.calls
        if "exec" in args
    )
    assert "delete" in runner.calls[-1]
    assert "--wait=true" in runner.calls[-1]


def test_kubernetes_rejects_admitted_pod_mutations() -> None:
    backend = KubernetesBackend(settings("kubernetes"), KubeRunner())
    name = "fred-sbx-test"
    pod = {
        "metadata": {
            "ownerReferences": [
                {"kind": "Job", "name": name, "uid": "job-uid", "controller": True}
            ]
        },
        "spec": backend.job_manifest(name)["spec"]["template"]["spec"],
    }
    assert backend._is_safe_admitted_pod(pod, name, "job-uid")
    pod["spec"]["containers"][0]["volumeMounts"].append(
        {"name": "credentials", "mountPath": "/secrets"}
    )
    assert not backend._is_safe_admitted_pod(pod, name, "job-uid")


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
        live_replicas=None,
        observed_generation=1,
    ):
        super().__init__()
        self.bad_image = bad_image
        self.wait_fails = wait_fails
        self.bad_pod_env = bad_pod_env
        self.template_changes = template_changes
        self.ready_replicas = ready_replicas
        self.live_replicas = live_replicas
        self.observed_generation = observed_generation
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
                            "readyReplicas": self.live_replicas or 0,
                            "replicas": self.live_replicas or 0,
                            "observedGeneration": self.observed_generation,
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
                        "metadata": {
                            "creationTimestamp": "2026-10-22T00:00:01Z",
                            "uid": "claim-uid",
                        },
                        "status": {"sandbox": {"name": self.claim_name}},
                    }
                ),
                "",
            )
        if "sandbox" in args and "get" in args:
            return CommandResult(
                0,
                json.dumps(
                    {
                        "metadata": {
                            "uid": "sandbox-uid",
                            "ownerReferences": [
                                {
                                    "kind": "SandboxClaim",
                                    "name": self.claim_name,
                                    "uid": "claim-uid",
                                    "controller": True,
                                }
                            ],
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
                            "ownerReferences": [
                                {
                                    "kind": "Sandbox",
                                    "name": self.claim_name,
                                    "uid": "sandbox-uid",
                                    "controller": True,
                                }
                            ],
                            "creationTimestamp": "2026-10-22T00:00:02Z",
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
async def test_agent_sandbox_claim_injects_only_approved_inputs_volume() -> None:
    class MountAgentRunner(AgentRunner):
        def __init__(self):
            super().__init__()
            self.created = []

        async def run(self, args, *, timeout, output_limit=65536, input_data=None):
            if args[:3] == ["kubectl", "get", "storageclass"]:
                return CommandResult(
                    0,
                    json.dumps(
                        {
                            "provisioner": "rclone.csi.veloxpack.io",
                            "parameters": {
                                "csi.storage.k8s.io/node-publish-secret-name": "${pvc.name}",
                                "csi.storage.k8s.io/node-publish-secret-namespace": "fred-sandbox",
                                "remotePath": "/",
                            },
                            "mountOptions": ["dir-cache-time=1s", "vfs-cache-mode=off"],
                        }
                    ),
                    "",
                )
            if input_data:
                item = json.loads(input_data)
                self.created.append(item)
                if item["kind"] == "Secret":
                    return CommandResult(0, "created", "")
            if "sandboxwarmpool" in args:
                return CommandResult(
                    0,
                    json.dumps(
                        {
                            "metadata": {"generation": 1},
                            "spec": {
                                "replicas": 0,
                                "sandboxTemplateRef": {"name": "fred-code-files"},
                                "updateStrategy": {"type": "Recreate"},
                            },
                            "status": {
                                "replicas": 0,
                                "readyReplicas": 0,
                                "observedGeneration": 1,
                            },
                        }
                    ),
                    "",
                )
            if "sandboxtemplate" in args:
                pod = KubernetesBackend(self.mount_settings, self).job_manifest(
                    "placeholder"
                )["spec"]["template"]["spec"]
                pod["volumes"].pop()
                return CommandResult(
                    0,
                    json.dumps(
                        {
                            "spec": {
                                "networkPolicyManagement": "Unmanaged",
                                "volumeClaimTemplatesPolicy": "Allowed",
                                "podTemplate": {"spec": pod},
                            }
                        }
                    ),
                    "",
                )
            if "pod" in args and "get" in args:
                pod = KubernetesBackend(self.mount_settings, self).job_manifest(
                    self.claim_name
                )["spec"]["template"]["spec"]
                pod["volumes"][-1]["persistentVolumeClaim"].pop("readOnly")
                return CommandResult(
                    0,
                    json.dumps(
                        {
                            "metadata": {
                                "ownerReferences": [
                                    {
                                        "kind": "Sandbox",
                                        "name": self.claim_name,
                                        "uid": "sandbox-uid",
                                        "controller": True,
                                    }
                                ]
                            },
                            "spec": pod,
                        }
                    ),
                    "",
                )
            return await super().run(
                args, timeout=timeout, output_limit=output_limit, input_data=input_data
            )

    runner = MountAgentRunner()
    runner.mount_settings = settings(
        "agent_sandbox",
        agent_pool_name="fred-code-files",
        mount_provider="rclone_csi",
        file_gateway_url="https://files.example/knowledge-flow/v1/sandbox-mount",
        file_gateway_secret="s" * 32,
        file_storage_class="fred-sandbox-webdav",
    )
    backend = AgentSandboxBackend(runner.mount_settings, runner)
    lease = await backend.prepare("a" * 64)
    claim = next(item for item in runner.created if item["kind"] == "SandboxClaim")
    assert claim["spec"]["volumeClaimTemplates"][0]["metadata"]["name"] == "inputs"
    assert any("patch" in args and "secret" in args for args in runner.calls)
    assert lease.view_key == "a" * 64
    await backend.dispose(lease)


@pytest.mark.asyncio
async def test_agent_sandbox_skills_claim_uses_approved_read_only_volume() -> None:
    class SkillsAgentRunner(AgentRunner):
        async def run(self, args, *, timeout, output_limit=65536, input_data=None):
            if "get" in args and "pvc" in args:
                return CommandResult(
                    0,
                    json.dumps(
                        {
                            "metadata": {"labels": {"fred.sandbox/skills": "approved"}},
                            "status": {"phase": "Bound"},
                            "spec": {"accessModes": ["ReadWriteMany"]},
                        }
                    ),
                    "",
                )
            if "sandboxtemplate" in args:
                pod = KubernetesBackend(self.skills_settings, self).job_manifest("x")[
                    "spec"
                ]["template"]["spec"]
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
            if "pod" in args and "get" in args:
                pod = KubernetesBackend(self.skills_settings, self).job_manifest("x")[
                    "spec"
                ]["template"]["spec"]
                return CommandResult(
                    0,
                    json.dumps(
                        {
                            "metadata": {
                                "ownerReferences": [
                                    {
                                        "kind": "Sandbox",
                                        "name": self.claim_name,
                                        "uid": "sandbox-uid",
                                        "controller": True,
                                    }
                                ]
                            },
                            "spec": pod,
                        }
                    ),
                    "",
                )
            return await super().run(
                args, timeout=timeout, output_limit=output_limit, input_data=input_data
            )

    runner = SkillsAgentRunner()
    runner.skills_settings = settings(
        "agent_sandbox", skills_volume="fred-platform-skills"
    )
    backend = AgentSandboxBackend(runner.skills_settings, runner)
    lease = await backend.prepare()
    assert lease.target == lease.id
    await backend.dispose(lease)


def test_agent_sandbox_accepts_reordered_claim_volume_without_weakening_validation() -> (
    None
):
    config = settings(
        "agent_sandbox",
        mount_provider="rclone_csi",
        file_gateway_url="https://files.example/knowledge-flow/v1/sandbox-mount",
        file_gateway_secret="s" * 32,
        file_storage_class="fred-sandbox-webdav",
        skills_volume="fred-platform-skills",
    )
    backend = AgentSandboxBackend(config, AgentRunner())
    workload = "fred-sbx-test"
    pod = backend.kubernetes.job_manifest(workload)["spec"]["template"]["spec"]
    pod["volumes"][1]["persistentVolumeClaim"].pop("readOnly")
    pod["volumes"] = [pod["volumes"][0], pod["volumes"][2], pod["volumes"][1]]

    assert backend.kubernetes.is_safe_pod_spec(
        pod, workload_name=workload, sig_claim=True
    )
    pod["volumes"][2]["persistentVolumeClaim"]["claimName"] = "other-claim"
    assert not backend.kubernetes.is_safe_pod_spec(
        pod, workload_name=workload, sig_claim=True
    )


def test_agent_sandbox_rejects_security_drift_in_template_and_pod() -> None:
    backend = AgentSandboxBackend(settings("agent_sandbox"), AgentRunner())
    pod = backend.kubernetes.job_manifest("fred-sbx-test")["spec"]["template"]["spec"]
    assert backend.kubernetes.is_safe_pod_spec(pod, sig_claim=True)
    assert backend.kubernetes.is_safe_pod_spec(
        pod, workload_name="fred-sbx-test", sig_claim=True
    )
    for field, value in (
        ("enableServiceLinks", True),
        ("restartPolicy", "Always"),
    ):
        changed = json.loads(json.dumps(pod))
        changed[field] = value
        assert not backend.kubernetes.is_safe_pod_spec(changed, sig_claim=True)
    changed = json.loads(json.dumps(pod))
    changed["securityContext"]["runAsGroup"] = 0
    assert not backend.kubernetes.is_safe_pod_spec(changed, sig_claim=True)
    changed = json.loads(json.dumps(pod))
    changed["containers"][0]["resources"]["requests"]["memory"] = "1Mi"
    assert not backend.kubernetes.is_safe_pod_spec(changed, sig_claim=True)


@pytest.mark.asyncio
async def test_agent_sandbox_rejects_claimed_pod_without_owner_chain() -> None:
    class MissingOwnerRunner(AgentRunner):
        async def run(self, args, *, timeout, output_limit=65536, input_data=None):
            result = await super().run(
                args, timeout=timeout, output_limit=output_limit, input_data=input_data
            )
            if "sandbox" in args and "get" in args:
                item = json.loads(result.stdout)
                item["metadata"]["ownerReferences"] = []
                return CommandResult(0, json.dumps(item), "")
            return result

    backend = AgentSandboxBackend(settings("agent_sandbox"), MissingOwnerRunner())
    with pytest.raises(SandboxError, match="policy_unavailable"):
        await backend.prepare()


@pytest.mark.asyncio
async def test_agent_sandbox_claim_lifecycle_and_expiry() -> None:
    runner = AgentRunner()
    backend = AgentSandboxBackend(settings("agent_sandbox"), runner)
    await backend.preflight()
    lease = await backend.prepare()
    result = await backend.execute(lease, SandboxRequest(code="echo ok"))
    await backend.renew(lease, 1200)
    await backend.dispose(lease)
    assert runner.manifest["kind"] == "SandboxClaim"
    assert runner.manifest["spec"]["warmPoolRef"]["name"] == "fred-code"
    assert runner.manifest["spec"]["lifecycle"]["shutdownPolicy"] == "DeleteForeground"
    assert "shutdownTime" in runner.manifest["spec"]["lifecycle"]
    assert result.stdout == "ok\n"
    assert any("patch" in args and "sandboxclaim" in args for args in runner.calls)
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
async def test_agent_sandbox_rejects_preloaded_replicas() -> None:
    runner = AgentRunner(ready_replicas=1)
    backend = AgentSandboxBackend(settings("agent_sandbox"), runner)
    with pytest.raises(SandboxError, match="policy_unavailable"):
        await backend.preflight()


@pytest.mark.asyncio
async def test_agent_sandbox_rejects_live_preloaded_pods_during_scale_down() -> None:
    runner = AgentRunner(ready_replicas=0, live_replicas=1)
    backend = AgentSandboxBackend(settings("agent_sandbox"), runner)
    with pytest.raises(SandboxError, match="policy_unavailable"):
        await backend.preflight()


@pytest.mark.asyncio
async def test_agent_sandbox_rejects_stale_zero_pool_status() -> None:
    runner = AgentRunner(ready_replicas=0, observed_generation=0)
    backend = AgentSandboxBackend(settings("agent_sandbox"), runner)
    with pytest.raises(SandboxError, match="policy_unavailable"):
        await backend.preflight()


@pytest.mark.asyncio
async def test_agent_sandbox_accepts_on_demand_claim() -> None:
    runner = AgentRunner(ready_replicas=0)
    backend = AgentSandboxBackend(settings("agent_sandbox"), runner)
    lease = await backend.prepare()
    assert lease.target == runner.claim_name
    await backend.dispose(lease)

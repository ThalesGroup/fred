from fred_runtime.runtime_support.checkpoints import checkpoint_namespace


def test_checkpoint_namespace_prefers_agent_instance_id() -> None:
    assert (
        checkpoint_namespace(
            agent_instance_id="instance-123",
            agent_id="agent.template",
        )
        == "instance-123"
    )


def test_checkpoint_namespace_falls_back_to_agent_id() -> None:
    assert (
        checkpoint_namespace(
            agent_instance_id=None,
            agent_id="agent.template",
        )
        == "agent.template"
    )

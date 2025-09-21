# app/agents/generalist/generalist_expert.py (top of file, after imports)

# Why: the system prompt defines Georges' persona and guardrails.
# Exposing it lets product owners steer tone/scope without code changes.
from app.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints


GENERALIST_TUNING_SPEC = AgentTuning(
    fields=[
        FieldSpec(
            key="prompts.system",          
            type="prompt",
            title="System Prompt",
            description=(
                "Sets Georges’ base persona and boundaries. "
                "Adjust to shift tone/voice or emphasize constraints."
            ),
            required=True,
            default=(
                "You are a friendly generalist expert, skilled at providing guidance on a wide range "
                "of topics without deep specialization.\n"
                "Your role is to respond with clarity, providing accurate and reliable information.\n"
                "When appropriate, highlight elements that could be particularly relevant.\n"
                "In case of graphical representation, render mermaid diagrams code."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True, max_lines=12),
        ),
    ],
    mcp_servers=None,)

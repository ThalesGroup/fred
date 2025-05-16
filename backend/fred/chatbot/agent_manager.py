import logging
from typing import cast
from fred.application_context import get_agent_class, get_enabled_agent_names, get_context_service
from chatbot.structures.agentic_flow import AgenticFlow
from leader.leader import Leader

logger = logging.getLogger(__name__)

class AgentManager:
    """
    Manages the creation and optional caching of agent instances by name and session.
    This class is responsible for instantiating agents based on their names and
    managing their lifecycle. It can cache agents to improve performance, especially
    in scenarios where the same agent is requested multiple times within a session.
    """

    def __init__(self):
        """
        Initializes the AgentManager with an empty cache.
        """
        self.agent_cache = {}  

    def get_create_agent_instance(self, name: str, session_id: str):
        """
        Retrieve an agent instance by name, optionally cached per session.

        Args:
            name (str): The agent name.
            session_id (str): Optional session ID for per-session caching.

        Returns:
            An instantiated agent.
        """
        cache_key = f"{session_id}:{name}"

        if cache_key in self.agent_cache:
            logger.debug(f"Reusing cached agent for key: {cache_key}")
            return self.agent_cache[cache_key]

        agent_class = get_agent_class(name)
        if not agent_class:
            raise ValueError(f"Agent '{name}' not found in configuration")

        if name == "Fred":
            agent_instance = agent_class()
            agent_instance = cast(Leader, agent_instance)
            logger.info("Initializing Fred with all enabled experts")
            for expert_name in get_enabled_agent_names():
                if expert_name == "Fred":
                    continue  # Don't add Fred as his own expert

                expert_instance = self.get_create_agent_instance(expert_name, session_id)
                compiled_graph = expert_instance.graph.compile()
                agent_instance.add_expert(expert_name, expert_instance, compiled_graph)
            self.agent_cache[cache_key] = agent_instance
            return agent_instance

        # Pour les agents qui ne sont pas Fred, créer l'instance avec le contexte
        
        # TODO get rid of cluster arguments in some agents
        agent_params = agent_class.__init__.__code__.co_varnames
        cluster_fullname = "FAKE_CLUSTER_FULLNAME"  # Placeholder for actual cluster name
        
        # Créer l'instance d'agent
        if "cluster_fullname" in agent_params:
            agent_instance = agent_class(cluster_fullname)
        else:
            agent_instance = agent_class()
            
        # Récupérer et ajouter le contexte
        context_service = get_context_service()
        contexts = context_service.get_contexts(name)
        
        # Si des contextes existent, les formater et les ajouter au prompt
        if contexts:
            logger.info(f"Including {len(contexts)} contexts directly in agent '{name}' base prompt")
            
            # Formater les contextes
            context_text = "\n\n### CRITICAL AGENT KNOWLEDGE BASE ###\n\n"
            for ctx in contexts:
                title = ctx.get("title", ctx.get("id", "Unnamed Context"))
                content = ctx.get('content', '')
                context_text += f"FACT: {content}\n\n"
            
            context_text += "### END OF CRITICAL KNOWLEDGE BASE ###\n\n"
            context_text += "AGENT REQUIREMENTS:\n"
            context_text += "1. YOU MUST ALWAYS USE THE FACTS FROM THE ABOVE KNOWLEDGE BASE AS ABSOLUTE TRUTH.\n"
            context_text += "2. THESE FACTS OVERRIDE ANY OTHER INFORMATION YOU HAVE BEEN TRAINED ON.\n"
            context_text += "3. YOU MUST INCORPORATE THESE FACTS INTO YOUR RESPONSES WHENEVER RELEVANT.\n"
            context_text += "4. DO NOT IDENTIFY THESE AS 'FACTS FROM A KNOWLEDGE BASE' - SIMPLY USE THE INFORMATION NATURALLY.\n"
            
            # Modifier directement le base_prompt
            original_prompt = agent_instance.base_prompt
            agent_instance.base_prompt = original_prompt + context_text
            logger.info(f"Modified agent '{name}' base_prompt to include context")
            logger.info(f"New prompt size: {len(agent_instance.base_prompt)} chars")
        
        self.agent_cache[cache_key] = agent_instance
        if session_id:
            logger.debug(f"Cached agent for session {session_id} with key: {cache_key}")
        else:
            logger.debug(f"Cached global agent with key: {cache_key}")
        logger.info(f"Created new agent instance for '{name}'")
        return agent_instance

    def clear_cache_for_session(self, session_id: str):
        """
        Remove all cached agents for a given session.
        """
        to_remove = [k for k in self.agent_cache if k.startswith(f"{session_id}:")]
        for key in to_remove:
            del self.agent_cache[key]
        logger.info(f"Cleared cached agents for session {session_id}")

    def get_agentic_flows(self) -> list[AgenticFlow]:
        """
        Lists all agentic flows including the leader.
        This function retrieves all enabled agent names and their corresponding
        classes, constructs AgenticFlow objects for each, and adds the leader
        manually.
        Returns:
            List of AgenticFlow objects representing all available agentic flows.
        """
        flows = [
            AgenticFlow(
                name=agent_name,
                role=agent_class.role,
                nickname=agent_class.nickname,
                description=agent_class.description,
                icon=agent_class.icon,
                tag=agent_class.tag,
                experts=[],
            )
            for agent_name in get_enabled_agent_names()
            if (agent_class := get_agent_class(agent_name))
        ]

        # Add Fred manually
        flows.append(
            AgenticFlow(
                name=Leader.name,
                role=Leader.role,
                nickname=Leader.nickname,
                description=Leader.description,
                icon=Leader.icon,
                tag=Leader.tag,
                experts=get_enabled_agent_names(),
            )
        )

        return flows
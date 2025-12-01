import logging
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.agents.middleware import TodoListMiddleware, after_agent
from langchain.agents.structured_output import ProviderStrategy, ToolStrategy
from langgraph.graph.state import CompiledStateGraph

from agentic_backend.application_context import get_default_chat_model
from agentic_backend.common.mcp_runtime import MCPRuntime
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_spec import AgentTuning, FieldSpec, UIHints
from agentic_backend.core.agents.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)

# ---------------------------
# Tuning spec (UI-editable)
# ---------------------------
BASIC_REACT_TUNING = AgentTuning(
    role="Define here the high-level role of the MCP agent.",
    description="Define here a detailed description of the MCP agent's purpose and behavior.",
    tags=[],
    fields=[
        FieldSpec(
            key="prompts.system",
            type="prompt",
            title="System Prompt",
            description=(
                "High-level instructions for the agent. "
                "State the mission, how to use the available tools, and constraints."
            ),
            required=True,
            default=(
                "You are an general assistant with tools. Use the available instructions and tools to solve the user's request.\n"
                "If you have tools:\n"
                "- ALWAYS use the tools at your disposal before providing any answer.\n"
                "- Prefer concrete evidence from tool outputs.\n"
                "- Be explicit about which tools you used and why.\n"
                "- When you reference tool results, keep short inline markers (e.g., [tool_name]).\n"
                "Current date: {today}."
            ),
            ui=UIHints(group="Prompts", multiline=True, markdown=True),
        ),
    ],
)


class Kelly(AgentFlow):
    """Simple ReAct agent used for dynamic UI-created agents."""

    tuning = BASIC_REACT_TUNING

    async def async_init(self, runtime_context: RuntimeContext):
        await super().async_init(runtime_context=runtime_context)

        # Initialize MCP runtime
        self.mcp = MCPRuntime(
            agent=self,
        )
        await self.mcp.init()

    async def aclose(self):
        await self.mcp.aclose()

    def get_compiled_graph(self) -> CompiledStateGraph:
        return create_agent(
            model=get_default_chat_model(),
            system_prompt=self.render(self.get_tuned_text("prompts.system") or ""),
            tools=[*self.mcp.get_tools()],
            checkpointer=self.streaming_memory,
            response_format=ProviderStrategy(globalSchema),  # type: ignore
            # middleware=[TodoListMiddleware()],
        )


globalSchema = {
    "type": "object",
    "properties": {
        "enjeuxBesoins": {
            "type": "object",
            "description": "Informations sur le contexte et les missions du projet.",
            "properties": {
                "contexte": {
                    "type": "string",
                    "description": "Contexte du projet.",
                    "maxLength": 300,
                },
                "missions": {
                    "type": "string",
                    "description": "Ensemble des missions et objectifs.",
                    "maxLength": 300,
                },
                "refCahierCharges": {
                    "type": "string",
                    "description": "Nom du fichier duquel les données sont exraites.",
                },
            },
        },
        "cv": {
            "type": "object",
            "description": "Informations sur le CV de l'intervenant Thalès Services Numériques.",
            "properties": {
                "poste": {
                    "type": "string",
                    "description": "L'intitulé du poste rempli par l'intervenant.",
                },
                "formations": {
                    "type": "array",
                    "description": "Les écoles et formations qu'a suivi l'intervenant.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "La date de la de diplôme ou de la formation.",
                            },
                            "nom": {
                                "type": "string",
                                "description": "Le nom de l'établissement ou de la formation.",
                            },
                        },
                    },
                },
                "langues": {
                    "type": "array",
                    "description": "Les langues parlées par l'intervenant.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "langue": {
                                "type": "string",
                                "description": "La langue parlée.",
                            },
                            "maitrise": {
                                "type": "integer",
                                "description": "La maitrise de la langue parlée.",
                            },
                        },
                    },
                },
                "competencesManagement": {
                    "type": "array",
                    "description": "Les compétences en management de l'intervenant.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "competence": {
                                "type": "string",
                                "description": "Le nom de la compétence en management.",
                            },
                            "maitrise": {
                                "type": "integer",
                                "description": "La maitrise de la compétence en management.",
                            },
                        },
                    },
                },
                "competencesInformatique": {
                    "type": "array",
                    "description": "Les compétences informatiques de l'intervenant.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "competence": {
                                "type": "string",
                                "description": "Le nom de la compétence informatique.",
                            },
                            "maitrise": {
                                "type": "integer",
                                "description": "La maitrise de la compétence informatique.",
                            },
                        },
                    },
                },
                "competencesGestionProjet": {
                    "type": "array",
                    "description": "Les compétences en gestion de projet de l'intervenant.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "competence": {
                                "type": "string",
                                "description": "Le nom de la compétence en gestion de projet.",
                            },
                            "maitrise": {
                                "type": "integer",
                                "description": "La maitrise de la compétence en gestion de projet.",
                            },
                        },
                    },
                },
                "experiences": {
                    "type": "array",
                    "description": "Les expériences de l'intervenant.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "entreprise": {
                                "type": "string",
                                "description": "Le nom de l'entreprise.",
                            },
                            "poste": {
                                "type": "string",
                                "description": "Le nom du poste.",
                            },
                            "duree": {
                                "type": "string",
                                "description": "La durée de l'expérience.",
                            },
                            "realisations": {
                                "type": "string",
                                "description": "Description des taches réalisées.",
                            },
                        },
                    },
                },
            },
        },
        "prestationFinanciere": {
            "type": "object",
            "descripion": "Informations sur les prestations financière facturées au client.",
            "properties": {
                "prestations": {
                    "type": "array",
                    "items": {
                        "nom": {
                            "type": "string",
                            "description": "Nom de la prestation.",
                        },
                        "prix": {
                            "type": "integer",
                            "description": "Prix unitaire de la prestation.",
                        },
                        "charge": {
                            "type": "integer",
                            "description": "Charge estimée de a prestation en unités d'oeuvre.",
                        },
                        "prixTotal": {
                            "type": "integer",
                            "description": "Coût total de la prestation.",
                        },
                    },
                },
                "prixTotal": {
                    "type": "integer",
                    "description": "Coût total de toutes les prestations.",
                },
            },
        },
    },
}

enjeuxBesoinsSchema = {
    "type": "object",
    "properties": {
        "contexte": {
            "type": "string",
            "description": "Contexte du projet.",
            "maxLength": 300,
        },
        "missions": {
            "type": "string",
            "description": "Ensemble des missions et objectifs.",
            "maxLength": 300,
        },
        "refCahierCharges": {
            "type": "string",
            "description": "Nom du fichier duquel les données sont exraites.",
        },
    },
}

cvSchema = {
    "type": "object",
    "description": "Le CV de l'intervenant Thalès Services Numériques.",
    "properties": {
        "poste": {
            "type": "string",
            "description": "L'intitulé du poste rempli par l'intervenant.",
        },
        "formations": {
            "type": "array",
            "description": "Les écoles et formations qu'a suivi l'intervenant.",
            "items": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "La date de la de diplôme ou de la formation.",
                    },
                    "nom": {
                        "type": "string",
                        "description": "Le nom de l'établissement ou de la formation.",
                    },
                },
            },
        },
        "langues": {
            "type": "array",
            "description": "Les langues parlées par l'intervenant.",
            "items": {
                "type": "object",
                "properties": {
                    "langue": {"type": "string", "description": "La langue parlée."},
                    "maitrise": {
                        "type": "integer",
                        "description": "La maitrise de la langue parlée.",
                    },
                },
            },
        },
        "competencesManagement": {
            "type": "array",
            "description": "Les compétences en management de l'intervenant.",
            "items": {
                "type": "object",
                "properties": {
                    "competence": {
                        "type": "string",
                        "description": "Le nom de la compétence en management.",
                    },
                    "maitrise": {
                        "type": "integer",
                        "description": "La maitrise de la compétence en management.",
                    },
                },
            },
        },
        "competencesInformatique": {
            "type": "array",
            "description": "Les compétences informatiques de l'intervenant.",
            "items": {
                "type": "object",
                "properties": {
                    "competence": {
                        "type": "string",
                        "description": "Le nom de la compétence informatique.",
                    },
                    "maitrise": {
                        "type": "integer",
                        "description": "La maitrise de la compétence informatique.",
                    },
                },
            },
        },
        "competencesGestionProjet": {
            "type": "array",
            "description": "Les compétences en gestion de projet de l'intervenant.",
            "items": {
                "type": "object",
                "properties": {
                    "competence": {
                        "type": "string",
                        "description": "Le nom de la compétence en gestion de projet.",
                    },
                    "maitrise": {
                        "type": "integer",
                        "description": "La maitrise de la compétence en gestion de projet.",
                    },
                },
            },
        },
        "experiences": {
            "type": "array",
            "description": "Les expériences de l'intervenant.",
            "items": {
                "type": "object",
                "properties": {
                    "entreprise": {
                        "type": "string",
                        "description": "Le nom de l'entreprise.",
                    },
                    "poste": {"type": "string", "description": "Le nom du poste."},
                    "duree": {
                        "type": "string",
                        "description": "La durée de l'expérience.",
                    },
                    "realisations": {
                        "type": "string",
                        "description": "Description des taches réalisées.",
                    },
                },
            },
        },
    },
}

prestationFinanciereSchema = {
    "type": "object",
    "descripion": "Prestations financière facturées au client.",
    "properties": {
        "prestations": {
            "type": "array",
            "items": {
                "nom": {"type": "string", "description": "Nom de la prestation."},
                "prix": {
                    "type": "integer",
                    "description": "Prix unitaire de la prestation.",
                },
                "charge": {
                    "type": "integer",
                    "description": "Charge estimée de a prestation en unités d'oeuvre.",
                },
                "prixTotal": {
                    "type": "integer",
                    "description": "Coût total de la prestation.",
                },
            },
        },
        "prixTotal": {
            "type": "integer",
            "description": "Coût total de toutes les prestations.",
        },
    },
}


"""
@dataclass
class EnjeuxBesoins:
    contexte: str
    missions: list[str]
    refCahierCharges: list[str]



@dataclass
class Formation:
    date: str
    institut: str
@dataclass
class Langue:
    nom: str
    maitrise: int
@dataclass
class Competence:
    nom: str
    maitrise: int
@dataclass
class Experience:
    entreprise: str
    poste: str
    duree: str
    realisations: list[str]
@dataclass
class CV:
    poste: str
    formations: list[Formation]
    langues: list[Langue]
    competencesManagement: list[Competence]
    competencesInformatique: list[Competence]
    competencesGestionProjet: list[Competence]
    experiences: list[Experience]



@dataclass
class Prestation:
    nom: str
    prix: float
    charge: int
    prixTotal: float
@dataclass
class PropositionFinanciere:
    prestations: list[Prestation]
    prixTotal: float
"""

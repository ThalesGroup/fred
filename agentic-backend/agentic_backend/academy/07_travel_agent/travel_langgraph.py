from langgraph.graph import StateGraph, END, START
from typing import TypedDict, List
from langchain_core.messages import AIMessage, HumanMessage

# --- 1️⃣ Définir l'état partagé entre les nœuds
class SimpleState(TypedDict):
    messages: List  # conversation history


# --- 2️⃣ Définir les fonctions (nœuds)
async def start_node(state: SimpleState) -> SimpleState:
    """Simule une requête utilisateur"""
    print("➡️  User envoie un message.")
    return {
        "messages": [HumanMessage(content="Hello agent !")]
    }


async def hardcoded_response_node(state: SimpleState) -> SimpleState:
    """Node qui retourne une réponse fixe sans appeler de modèle"""
    print("🤖 Génération de la réponse (sans LLM)...")
    response_text = "Bonjour humain, je suis un agent LangGraph sans modèle !"
    
    # On ajoute un message assistant manuellement
    messages = state["messages"] + [AIMessage(content=response_text)]
    
    return {"messages": messages}


# --- 3️⃣ Construire le graphe
graph = StateGraph(SimpleState)

graph.add_node("start", start_node)
graph.add_node("hardcoded_response", hardcoded_response_node)

graph.add_edge(START, "start")
graph.add_edge("start", "hardcoded_response")
graph.add_edge("hardcoded_response", END)

app = graph.compile()


# --- 4️⃣ Exécuter le graphe
import asyncio

async def main():
    final_state = await app.ainvoke({})
    print("\n✅ Sortie finale du graphe :")
    for msg in final_state["messages"]:
        print(f"[{msg.type}] {msg.content}")

asyncio.run(main())

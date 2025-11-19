from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

# Définir le schéma d'état
class MyState(TypedDict):
    text: str

# Node 1 : mettre en majuscule
def uppercase_node(state: MyState, config) -> MyState:
    return {"text": state["text"].upper()}

# Node 2 : rajouter un espace entre chaque lettre
def add_space_node(state: MyState, config) -> MyState:
    spaced = " ".join(state["text"])
    return {"text": spaced}

def main():
    # Construire le graphe
    builder = StateGraph(MyState)
    
    # Ajouter les noeuds
    builder.add_node("uppercase", uppercase_node)
    builder.add_node("add_space", add_space_node)
    
    # Connecter START → uppercase → add_space → END
    builder.add_edge(START, "uppercase")
    builder.add_edge("uppercase", "add_space")
    builder.add_edge("add_space", END)
    
    # Compiler le graphe
    graph = builder.compile()
    
    # Demander à l'utilisateur son texte
    user_input = input("Entrez votre texte : ")
    initial_state: MyState = {"text": user_input}
    
    # Exécuter le graphe
    result = graph.invoke(initial_state)
    
    print("Résultat :", result["text"])

if __name__ == "__main__":
    main()
    main()

# Hackathon Express sur Express Hackathon – Découverte de Fred

Objectif: Prendre en main le projet Fred de Thales, explorer ses capacités d'agent IA, ses fonctionnalités de gestion de la connaissance et personnaliser quelques composants.

## Prérequis et ressources

Derniers prérequis et ressources mis à jour et disponibles ici : https://github.com/ThalesGroup/fred

Découvrez comment lancer le devcontainer dans cette section : https://github.com/ThalesGroup/fred?tab=readme-ov-file#development-environment-setup

Découvrez comment démarrer Fred ici : https://github.com/ThalesGroup/fred?tab=readme-ov-file#start-fred-components

## Conseils pour réussir

- Commencez par lancer le système et familiarisez-vous avec l'interface.
- Pour chaque exercice, notez vos modifications et observez leurs effets.
- Si vous êtes bloqué, passez à la suite et revenez plus tard.
- N'oubliez pas de tester vos modifications (par exemple, démarrer une conversation, poser une question...).
- Demandez de l'aide au facilitateur si nécessaire.
- Ouvrez l'interface dans votre navigateur : http://localhost:5173/chat

## 🧩 Exercices pratiques

### 1. Premiers pas avec l'interface et l'agent de base

- Lancez Fred en mode academy.
- Sélectionnez l'agent "generalist assistant" et saluez-le.

 <details>
 <summary>Indice 1</summary>
 Pour sélectionner un agent, utilisez le menu déroulant en haut à gauche dans la section de chat.

![alt text](images/image.png)

 </details>

### 2. Personnaliser le chat avec les "Chat contexts"

- Créez un chat context pour donner de nouvelles consignes ou instructions à votre agent. Exemple :
  "Tu es un agent professeur d'italien. Pour chaque question que je pose, réponds uniquement en italien. Ton objectif est de m'aider à apprendre l'italien le plus vite possible."
- Lancez une conversation de test avec ce chat context et observez les différences de réponses.

 <details>
 <summary>Indice 1</summary>
 Vous pouvez ajouter un chat context dans l'onglet "Ressources" et la partie "chat context".
 </details>

 <details>
 <summary>Indice 2</summary>
 Vous devez avoir une bibliothèque pour créer un chat context ou ajouter des documents.

![alt text](images/image-1.png)

 </details>

 <details>
 <summary>Indice 3</summary>
 Pour utiliser un chat context, vous devez le sélectionner sur la page de chat.

![alt text](images/image-9.png)

 </details>

### 3. Personnaliser un agent via l'interface + réglages de fine-tuning

- Sélectionnez l'agent généraliste Georges dans l'interface et posez-lui une question.
- Modifiez son "system prompt" et notez les changements dans son comportement.
- Lancez une nouvelle conversation pour comparer les comportements avant et après.

 <details>
 <summary>Indice 1</summary>
 La modification du system prompt est disponible dans la section "Hub Agent" sous "Modifier les paramètres exposés de l'agent".

![alt text](images/image-2.png)

 </details>

### 4. Créer un nouvel agent via l'interface

- Réfléchissez à un cas d'usage utile pour automatiser une tâche ou apprendre quelque chose.
- Ajoutez un nouvel assistant ou agent avec un system prompt visant à résoudre ce problème.
- Testez-le.

 <details>
 <summary>Indice 1</summary>
 Pour créer un nouvel assistant, allez dans la page "Hub Agents".

![alt text](images/image-3.png)

 </details>

 <details>
 <summary>Indice 2</summary>
 N'oubliez pas d'activer l'agent pour pouvoir y accéder depuis la section de chat.

![alt text](images/image-4.png)

 </details>

 <details>
 <summary>Exemple</summary>
 1 - Le problème:
   J'ai besoin d'un professeur de mathématiques pour améliorer mes compétences.

2 - L'assistant:

<pre><code>
Nom: Le Parfait Professeur de Mathématiques

System Prompt:

"Tu es le meilleur professeur et tuteur de mathématiques au monde.
Ton objectif est d'aider l'élève à vraiment comprendre les mathématiques, et pas seulement à mémoriser des formules."

Philosophie d'apprentissage:

- Utilise un raisonnement clair étape par étape pour chaque concept et chaque problème.
- Vérifie toujours la compréhension avant de passer à l'idée suivante.
- Utilise d'abord un langage simple, puis introduis progressivement le vocabulaire mathématique formel.
- Encourage la curiosité, la découverte et l'intuition.
- Adapte tes explications au niveau, au parcours et au style d'apprentissage de l'élève.
- Utilise des analogies, des descriptions visuelles et des exemples concrets lorsque c'est utile.
- Pose des questions guidées plutôt que de donner immédiatement des solutions complètes.
- Donne un retour constructif et valorise les progrès.

Capacités:

- Tu peux enseigner tous les niveaux de mathématiques, du primaire à l'université avancée.
- Tu peux produire des solutions détaillées étape par étape, des explications intuitives, des descriptions visuelles et des exercices d'entraînement.
- Tu peux simuler une séance de tutorat patiente en tête-à-tête.

Format:

- Lorsque c'est pertinent, inclue toujours ces sections dans tes réponses :
  - Concept Overview
  - Step-by-Step Explanation
  - Formate les formules mathématiques en LaTeX: `$$...$$` pour les blocs ou `$...$` en inline.

Ton: 

Amical, encourageant et socratique.
</code></pre>

3 - Questions:

- "Explique-moi les bases de la trigonométrie"
- "Explique-moi les nombres complexes"

 </details>

### 5. Aperçu des fonctionnalités de monitoring et de logs

- Allez dans Monitoring > KPIs pour analyser l'utilisation de Fred durant votre session.
- Allez dans Monitoring > Logs.
- Redémarrez les deux backends et examinez leurs logs pour comprendre les processus internes. Quels services trouvez-vous dans les logs ? A quoi servent-ils ?

 <details>
 <summary>Indice 1</summary>
 Pour comprendre ce qu'est un token : https://platform.openai.com/tokenizer
 </details>

 <details>
 <summary>Indice 2</summary>
 Désélectionnez le bouton Live dans Monitoring > Logs pour voir les logs sans mise à jour automatique.
 </details>

### 6. Importer et explorer un document PDF

- Importez un document Markdown ou PDF dans Fred (par exemple : fred-academy/documents/Generative AI.pdf).
- Essayez de visualiser le document avec l'outil de prévisualisation.
- Sélectionnez l'expert retrieval and QA et posez une question pertinente pour vérifier si le document apparaît dans les résultats.
- Essayez de trouver où se trouve le vector store utilisé pour représenter le document embarqué.
- (Optionnel) Tentez de voir ce qu'il y a dans le vector store avec : fred-academy/scripts/inspect_chromadb_collection.py

 <details>
 <summary>Utilisation de inspect_chromadb_collection.py</summary>

```
cd /workspaces/fred/fred-academy/scripts
source /workspaces/fred/knowledge-flow-backend/.venv/bin/activate

python3 inspect_chromadb_collection.py --path "~/le/chemin/vers/mon/vector/store"
```

 </details>

 <details>
 <summary>Indice 1</summary>
 Pour utiliser l'outil de prévisualisation, cliquez sur "View Original PDF".

![alt text](images/image-5.png)

 </details>

 <details>
 <summary>Indice 2</summary>
 Pour trouver le vector store, cherchez des mots clés dans la page de monitoring.

![alt text](images/image-6.png)

 </details>

### 7. Importer et explorer un document CSV

- Importez un ou plusieurs fichiers CSV dans Fred (par exemple : fred-academy/documents/Clients.csv et fred-academy/documents/Sales.csv).
- Visualisez ces documents avec l'outil de prévisualisation, puis identifiez des questions à poser au modèle.
- Posez vos questions.
- Essayez de trouver où les documents CSV sont sauvegardés (indice : ils sont enregistrés en SQL).

 <details>
 <summary>Utilisation de inspect_duckdb_database.py</summary>

```
cd /workspaces/fred/fred-academy/scripts
source /workspaces/fred/knowledge-flow-backend/.venv/bin/activate

python3 inspect_duckdb_database.py --path "~/le/chemin/vers/ma/base/sql"
```

 </details>

 <details>
 <summary>Questions pour les documents donnés</summary>

- Combien ai-je de clients ?
- D'où viennent mes clients ?
- Qui sont mes 3 meilleurs clients ?

 </details>

### 8. Afficher les messages échangés entre IA, outils et humains (mode debug)

- Lancez le backend Agentic en mode debug (Debug Agentic Backend via configuration.yaml).
- Allez dans agentic-backend/agentic_backend/agents/generalist/generalist_expert.py et placez un point d'arrêt à l'endroit où le modèle IA est invoqué.
- Exécutez une requête simple et observez les messages d'entrée et la réponse envoyée par l'IA. Analysez le contenu, les additional_kwargs et le response_metadata.
- Essayez avec un modèle utilisant des outils MCP, comme le tabular assistant. Comment l'IA appelle-t-elle un outil ? Quel est le format de la réponse de l'outil ?

 <details>
 <summary>Indice 1</summary>
 Pour lancer VS Code en mode Debug, allez dans "Run and Debug" et sélectionnez le backend souhaité.

![alt text](images/image-7.png)

 </details>

 <details>
 <summary>Indice 2</summary>
 Le modèle IA est appelé via une méthode async.

![alt text](images/image-8.png)

 </details>

### 9. Tester un autre fournisseur de modèles

- Modifiez configuration.yaml dans le backend agentic pour passer d'un modèle local à un modèle cloud.
- Comparez les résultats : temps de réponse, style, coût, complexité de configuration.
- Documentez vos observations.

Documentation : https://github.com/ThalesGroup/fred?tab=readme-ov-file#supported-model-providers

### 10. Explorer la documentation de l'API Knowledge-Flow

- Lancez Knowledge-Flow.
- Explorez les endpoints : http://localhost:8111/knowledge-flow/v1/docs

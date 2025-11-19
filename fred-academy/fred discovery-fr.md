# Hackathon Express sur Express Hackathon – Découverte de Fred

Objectif: Prendre en main le projet Fred de Thales, explorer ses capacités d'agent IA, ses fonctionnalités de gestion de la connaissance et personnaliser quelques composants.

  - [Prérequis](#prérequis)
    - [Ressources](#ressources)
  - [Conseils pour réussir](#conseils-pour-réussir)
  - [🧩 Exercices pratiques](#-exercices-pratiques)
    - [1. Premiers pas avec l'interface et l'agent de base](#1-premiers-pas-avec-linterface-et-lagent-de-base)
    - [2. Personnaliser le chat avec les "contextes de conversations"](#2-personnaliser-le-chat-avec-les-contextes-de-conversations)
    - [3. Personnaliser un agent via l'interface + réglages de fine-tuning](#3-personnaliser-un-agent-via-linterface--réglages-de-fine-tuning)
    - [4. Créer un nouvel agent via l'interface](#4-créer-un-nouvel-agent-via-linterface)
    - [5. Aperçu des fonctionnalités de supervision et de logs](#5-aperçu-des-fonctionnalités-de-supervision-et-de-logs)
    - [6. Importer et explorer un document PDF](#6-importer-et-explorer-un-document-pdf)
    - [7. Importer et explorer un document CSV](#7-importer-et-explorer-un-document-csv)
    - [8. Afficher les messages échangés entre IA, outils et humains (mode debug)](#8-afficher-les-messages-échangés-entre-ia-outils-et-humains-mode-debug)
    - [9. Tester un autre fournisseur de modèles](#9-tester-un-autre-fournisseur-de-modèles)
    - [10. Explorer la documentation de l'API Knowledge-Flow](#10-explorer-la-documentation-de-lapi-knowledge-flow)



## Prérequis

Avoir l'ensemble des composants de Fred _up and running_ !

### Ressources

- Découvrez [ici](../README.md) des informations génériques sur Fred, son architecture, ses composants, etc.
- Découvrez comment lancer le Dev Container dans cette section [ici](../README.md#option-1-recommended-let-the-dev-container-do-it-for-you)
- Découvrez comment démarrer les différents composants de Fred [ici](../README.md#start-fred-components)

## Conseils pour réussir

- Familiarisez-vous avec l'interface graphique de Fred !
- Pour chaque exercice, notez vos modifications et observez leurs effets
- Si vous êtes bloqué, laissez de côté le point bloquant, passez à la suite (les exercices sont indépendants !) et revenez-y plus tard
- N'oubliez pas de tester vos modifications via des interactions avec l'interface graphiqu de Fred (par exemple, démarrer une conversation, poser une question...)
- Demandez de l'aide au facilitateur si nécessaire
- Ouvrez [l'interface graphique de Fred](http://localhost:5173) dans votre navigateur !
- Configurez l'interface en français (Modifiez ce paramètre dans votre "Profil")

## 🧩 Exercices pratiques

### 1. Premiers pas avec l'interface et l'agent de base

- Lancez Fred et rendez-vous sur l'interface graphique [ici](http://localhost:5173) !
- Rendez-vous dans la page dédiée aux discussions
- Sélectionnez Georges, l'agent géneraliste, et saluez-le.

<details>
<summary>Indice 1</summary>

Lancez la commande pour démarrer le backend agentique:

```bash
make run
```

</details>

<details>

<summary>Indice 2</summary>

Pour sélectionner un agent, utilisez le menu déroulant en haut à gauche dans la section de chat.

![alt text](images/image.png)

</details>

### 2. Personnaliser le chat avec les "contextes de conversations"

- Créez un contexte de conversation pour donner de nouvelles consignes ou instructions à votre agent.

  Par exemple : "_Tu es un agent professeur d'italien. Pour chaque question que je pose, réponds uniquement en italien. Ton objectif est de m'aider à apprendre l'italien le plus vite possible._"

- Lancez une conversation de test avec ce contexte de conversation et observez les différences de réponses.

<details>
<summary>Indice 1</summary>

Vous pouvez ajouter un contexte de conversation via la page `Ressources` > onglet `contextes de conversation`.

</details>

<details>
<summary>Indice 2</summary>

Vous devez avoir une bibliothèque pour créer un contexte de conversation ou ajouter des documents.

![alt text](images/image-1.png)

</details>

<details>
<summary>Indice 3</summary>

Pour utiliser un contexte de conversation, vous devez le sélectionner sur la page de chat.

![alt text](images/image-9.png)

</details>

### 3. Personnaliser un agent via l'interface + réglages de fine-tuning

- Sélectionnez l'agent généraliste "Georges" dans l'interface et posez-lui une question.
- Modifiez son "_system prompt_" et notez les changements dans son comportement.
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
<br>
<b>1. Le problème:</b> J'ai besoin d'un professeur de mathématiques pour améliorer mes compétences.
<br>

<b>2. L'assistant:</b>

- **Nom**: Le Parfait Professeur de Mathématiques
- **System Prompt:**

<pre><code>
  Tu es le meilleur professeur et tuteur de mathématiques au monde.
  Ton objectif est d'aider l'élève à vraiment comprendre les mathématiques, et pas seulement à mémoriser des formules.

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

<b>3 - Questions:</b>

- "Explique-moi les bases de la trigonométrie"
- "Explique-moi les nombres complexes"

</details>

### 5. Aperçu des fonctionnalités de supervision et de logs

- Allez dans Supervision > KPIs pour analyser l'utilisation de Fred durant votre session.
- Allez dans Supervision > Logs.
- Redémarrez les deux backends et examinez leurs logs pour comprendre les processus internes. Quels services trouvez-vous dans les logs ? A quoi servent-ils ?

<details>
<summary>Indice 1</summary>
 Pour comprendre ce qu'est un token : https://platform.openai.com/tokenizer
</details>

<details>
<summary>Indice 2</summary>
 Désélectionnez le bouton Live dans Supervision > Logs pour voir les logs sans mise à jour automatique.
</details>

### 6. Importer et explorer un document PDF

- Importez un document Markdown ou PDF dans Fred (par exemple : `fred-academy/documents/Generative AI.pdf`).
- Essayez de visualiser le document avec l'outil de prévisualisation.
- Sélectionnez l'expert retrieval and QA et posez une question pertinente pour vérifier si le document apparaît dans les résultats.
- Essayez de trouver où se trouve le vector store utilisé pour représenter le document embarqué.
- (Optionnel) Tentez de voir ce qu'il y a dans le vector store avec : `fred-academy/scripts/inspect_chromadb_collection.py`

<details>
<summary>Utilisation de <code>inspect_chromadb_collection.py</code></summary>

```bash
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
 Pour trouver le vector store, cherchez des mots clés dans la page de supervision.

![alt text](images/image-6.png)

</details>

### 7. Importer et explorer un document CSV

- Importez un ou plusieurs fichiers CSV dans Fred (par exemple : `fred-academy/documents/Clients.csv` et `fred-academy/documents/Sales.csv`).
- Visualisez ces documents avec l'outil de prévisualisation, puis identifiez des questions à poser au modèle.
- Posez vos questions.
- Essayez de trouver où les documents CSV sont sauvegardés (indice : ils sont enregistrés en SQL).

<details>
<summary>Utilisation de <code>inspect_duckdb_database.py</code></summary>

```bash
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

- Lancez le backend Agentique en mode debug (**Debug Agentic Backend** via `configuration.yaml`).
- Allez dans `agentic-backend/agentic_backend/agents/generalist/generalist_expert.py` et placez un point d'arrêt à l'endroit où le modèle d'IA est invoqué.
- Exécutez une requête simple et observez les messages d'entrée et la réponse envoyée par l'IA. Analysez le `content`, les `additional_kwargs` et le `response_metadata`.
- Essayez avec un modèle utilisant des outils MCP, comme le tabular assistant. Comment l'IA appelle-t-elle un outil ? Quel est le format de la réponse de l'outil ?

<details>
<summary>Indice 1</summary>
 Pour lancer VS Code en mode Debug, allez dans <code>Run and Debug</code> et sélectionnez le backend souhaité.

![alt text](images/image-7.png)

</details>

<details>
<summary>Indice 2</summary>
 Le modèle d'IA est appelé via une méthode <code>async</code>.

![alt text](images/image-8.png)

</details>

### 9. Tester un autre fournisseur de modèles

- Modifiez `configuration.yaml` dans le backend agentic pour passer d'un modèle cloud à un modèle local (via le serveur d'inférence Ollama par exemple, si vous avez une carte graphique adaptée à disposition).
- Comparez les résultats : temps de réponse, style, coût, complexité de configuration.
- Documentez vos observations.

Documentation disponible [ici](../README.md#supported-model-providers) !

### 10. Explorer la documentation de l'API Knowledge-Flow

- Lancez Knowledge-Flow.
- Explorez les endpoints : http://localhost:8111/knowledge-flow/v1/docs

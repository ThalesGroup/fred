# Hackathon express – Découverte de Fred

Durée : ~1 heure  
Objectif : Prendre en main le projet **Fred** de Thales, explorer ses capacités d’agents IA, de gestion de connaissances, et personnaliser quelques composants.

## Pré-requis

- Machine avec Docker ou capacité à lancer localement (voir doc)
- Accès au repo : https://github.com/ThalesGroup/fred
- Node.js + Python selon « Getting Started ». :contentReference[oaicite:3]{index=3}
- Idéalement un navigateur récent, accès web.

## Supports & ressources

- Documentation « Getting Started » pour Fred : https://fredk8.dev/docs/guides/getting-started/ :contentReference[oaicite:4]{index=4}
- Architecture & design de Fred (papier) : «Fred: A Modular Multi-Agent AI Assistant for Kubernetes» :contentReference[oaicite:5]{index=5}
- Repo GitHub : https://github.com/ThalesGroup/fred
- Correction / solution rapide (sera partagée en toggle sous chaque énoncé)

## Conseils pour réussir

- Commencez par lancer le système, familiarisez-vous avec l’UI.
- Pour chaque exercice, notez ce que vous modifiez, ce que vous observez comme effet.
- Si un exercice vous bloque > passez au suivant, revenez après.
- N’oubliez pas de tester votre modification (ex. lancer conversation, poser question…)
- Posez des questions à l’animateur si nécessaire!

## Comment lancer FRED ?

### Lancer Fred via le devcontainer

1 - Cloner le repo Fred avec :

```
git clone https://github.com/ThalesGroup/fred
```

2 - Vérifier que vous avez toutes les dépendances nécessaires

<details>
  <summary>First, make sure you have all the requirements installed</summary>

| Tool         | Type                       | Version                                                                                             | Install hint                                                                                |
| ------------ | -------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Pyenv        | Python installer           | latest                                                                                              | [Pyenv installation instructions](https://github.com/pyenv/pyenv#installation)              |
| Python       | Programming language       | 3.12.8                                                                                              | Use `pyenv install 3.12.8`                                                                  |
| python3-venv | Python venv module/package | matching                                                                                            | Bundled with Python 3 on most systems; otherwise `apt install python3-venv` (Debian/Ubuntu) |
| nvm          | Node installer             | latest                                                                                              | [nvm installation instructions](https://github.com/nvm-sh/nvm#installing-and-updating)      |
| Node.js      | Programming language       | 22.13.0                                                                                             | Use `nvm install 22.13.0`                                                                   |
| Make         | Utility                    | system                                                                                              | Install via system package manager (e.g., `apt install make`, `brew install make`)          |
| yq           | Utility                    | system                                                                                              | Install via system package manager                                                          |
| SQLite       | Local RDBMS engine         | ≥ 3.35.0                                                                                            | Install via system package manager                                                          |
| Pandoc       | 2.9.2.1                    | [Pandoc installation instructions](https://pandoc.org/installing.html)                              | For DOCX document ingestion                                                                 |
| LibreOffice  | Headless doc converter     | [LibreOffice installation instructions](https://www.libreoffice.org/download/download-libreoffice/) | For PPTX conversion into PDF                                                                |

</details>

3 - Ouvrir le devcontainer sur dans votre vscode

3.a - ouvrir le dossier fred dans vscode

3.b - créer le dossier .fred à la racine de votre machine

```
cd ~
mkdir .fred
```

3.c - appuyer sur la touche f1 puis "Dev Containers: Build and Open in Container"

4 - Lancer les 3 services : le frontend, knowledge-flow et agentic-backend

4.a - frontend:

```
cd frontend
make run
```

4.b - knowledge-flow:

```
cd knowledge-flow-backend
make run
```

4.c - agentic-backend

```
cd agentic-backend
make run              # or make run-academy to run the academy FRED
```

note : utiliser un terminal par service

5 - ouvrir l'ui en suivant ce lien : http://localhost:5173/chat

## 🧩 Exercices pratiques

### 1. Prise en main de l'UI et utilisation d'un agent basique

- Lancer Fred en mode academy
- Sélectionner l'agent "llm_responder", poser lui une question.

### 2. Personnalisation du chat avec « chat profiles »

- Créez un profil de chat (par exemple : "Tu es un agent professeur d'italien, à chaque question que je vais te poser tu pourras seulement me répondre en italien. Ton object est de me faire apprendre l'italien le plus rapidement possible.").
- Lancez une conversation test en utilisant ce profil et évaluez en quoi la réponse diffère.

### 3. Personnalisation d’un agent via l’UI + réglages de fine-tuning

- Sélectionnez l'agent généraliste, nommé "Georges" dans l’UI de Fred et posez lui une question.
- Modifiez son prompt system et identifier les changements dans son comportement.
- Lancez une noucelle conversation et comparez le comportement de l'agent avant et après modification.

### 4. Ajout d'un template de réponse dans "Agent > Assets"

- Ajoutez ce template dans la partie assets managements de l'agent que vous souhaitez tester.

```

```

- Testez et notez les différences avec et sans le modèle de réponse.

### 5. Monitoring / Logs

- Allez sur la page "Monitoring > Kpis".
- Analyser l'utilisation de Fred depuis le début de votre session.
- Allez sur la page "Monitoring > Logs".
- Relancez les 2 backends et parcourez leurs logs respectifs pour mieux comprendre les services internes au backend.

### 6. Upload d’un document pdf & exploration

- Importez un document, Markdown ou PDF, dans Fred.
- Vérifiez que les objets associés sont créés : aperçu (preview), conversion depuis markdown/pdf, objets de métadonnées.
- Si un moteur vectoriel (par exemple ChromaDB) est configuré, explorez les embeddings générés.
- Posez une requête pertinente et vérifiez si le document apparaît dans les résultats.

### 7. Upload d’un document csv & exploration

- Importez un document csv dans Fred.
- Vérifiez que les objets associés sont créés : aperçu (preview), conversion et ajout dans la base de données SQL.
- Si une base de données est configurée, explorez la ou les tables créée(s).
- Posez une requête pertinente et vérifiez si le document apparaît dans les résultats.

### 8. Affichage des messages entre l'IA, le tools et l'humain en mode debug

- Activez le mode debug d'agentic backend.
- Lancez une ou deux requêtes simples et observez le flux de traitement : agent → modèle → base vecteur → réponse.
- Identifiez des points intéressants dans l'agent sélectionné pour afficher les messages transmis.
- Lisez les informations transmises entre les composants de Fred.

### 9. Test d'un autre fournisseur de modèle

- Changez explicitement le fichier configuration.yaml dans agentic-backendpour comparer entre un modèle “local” vs “cloud”.
- Comparez les résultats : temps de réponse, style de réponse, coûts éventuels, complexité de la configuration.
- Documentez vos observations.

### 10. Exploration de la documentation api de knowledge-flow

- Lancez knowledge-flow
- Explorez les endpoints à cet url : http://localhost:8111/knowledge-flow/v1/docs

# Guide d'onboarding — Claude Code & Stratégie de branches Fred

**Destinataires** : Claire · Arnaud (organisation d'équipe) · Simon (backend, aide à l'installation)

**Objectif** : apprendre à poser des questions à Claude Code sur le dépôt Fred pour
suivre l'avancement, comprendre qui fait quoi, et naviguer la documentation sans
avoir besoin d'accéder à Jira ou de connaître le code.

---

## Partie 1 — Stratégie de branches (Simon + Dimitri)

> La référence complète en anglais est [`BRANCH_STRATEGY.md`](BRANCH_STRATEGY.md).
> Cette section en résume les points essentiels pour l'équipe.

### Le modèle adopté

Fred utilise un modèle de **branches de release long-terme**, identifiées par des
noms d'oiseaux. La branche `swift` est la branche d'intégration courante.

```
swift  (branche d'intégration long-terme — release 1.x)
  │
  ├── feat/mon-feature     ← branch depuis swift, PR → swift
  ├── fix/mon-bug          ← branch depuis swift, PR → swift
  │
  ├─── tag v1.0.0          ← release officielle (tag git sur swift)
  ├─── tag v1.1.0
  ├─── tag v1.2.0
  └─── ...

Plus tard, quand la release 2.x commence :

falcon  (branche release 2.x — née d'un tag swift)
  │
  ├── feat/nouvelle-feature  ← branch depuis falcon, PR → falcon
  └── ...
```

À terme : **une branche par release maintenue** (`swift` pour 1.x, `falcon` pour
2.x, etc.). Les corrections de sécurité sur une ancienne release se font via une
branche depuis le tag concerné, puis un tag de patch.

### Pourquoi ce modèle ?

L'ancien modèle `main` + `develop` imposait une double intégration (merge dans
`develop`, puis re-merge dans `main` pour chaque release), ce qui créait des
conflits récurrents et des divergences difficiles à tracer. Le modèle long-terme
est plus simple : une seule branche d'intégration, les tags portent l'historique
des releases.

### Workflow quotidien pour les développeurs

```bash
# 1. Mettre swift à jour
git checkout swift
git pull origin swift

# 2. Créer sa branche de feature depuis swift
git checkout -b feat/ma-feature

# 3. Travailler, committer normalement
git commit -m "ma feature"

# 4. Pousser et ouvrir une PR vers swift
git push origin feat/ma-feature
# → ouvrir une Pull Request sur GitHub, base = swift

# 5. Après merge de la PR, supprimer la branche locale
git branch -d feat/ma-feature
```

### Créer une release (tag)

```bash
git checkout swift
git pull origin swift
git tag v1.2.0
git push origin v1.2.0
```

### Nommer les branches de feature

| Type                           | Préfixe     | Exemple                    |
| ------------------------------ | ----------- | -------------------------- |
| Nouvelle fonctionnalité        | `feat/`     | `feat/mcp-tri-state`       |
| Correction de bug              | `fix/`      | `fix/prompt-crash`         |
| Refactoring                    | `refactor/` | `refactor/agent-app-split` |
| Documentation                  | `docs/`     | `docs/operating-modes`     |
| Correction urgente sur release | `hotfix/`   | `hotfix/v1.2.1-auth`       |

---

## Partie 2 — Installation de l'environnement

### Prérequis

- **Git** installé (`git --version` dans un terminal pour vérifier)
- Un compte GitHub avec accès au dépôt Fred
- **VS Code** — télécharger sur [code.visualstudio.com](https://code.visualstudio.com)

### Étape 1 — Cloner le dépôt

Ouvrir un terminal et taper :

```bash
git clone https://github.com/<organisation>/fred.git
cd fred
git checkout swift
```

> **Simon** : si Claire n'a pas Git configuré, la commande `git config --global
user.name "Claire Dupont"` puis `git config --global user.email "claire@..."` est
> nécessaire une seule fois.

### Étape 2 — Installer l'extension Claude Code dans VS Code

1. Ouvrir VS Code
2. Cliquer sur l'icône **Extensions** dans la barre latérale gauche (ou `Ctrl+Shift+X`)
3. Chercher **"Claude Code"** (éditeur : Anthropic)
4. Cliquer **Install**
5. Recharger VS Code si demandé

### Étape 3 — Se connecter à Claude Code

Au premier lancement, Claude Code demande une connexion. Deux options :

- **Compte Claude** (claude.ai) — recommandé pour commencer
- **Clé API Anthropic** — pour un usage professionnel (demander à Dimitri)

### Étape 4 — Ouvrir le dépôt dans VS Code

```
Fichier → Ouvrir le dossier → sélectionner le dossier fred/
```

Le dépôt est maintenant chargé. VS Code affiche l'arborescence des fichiers à gauche.

### Étape 5 — Ouvrir le panneau Claude Code

- Cliquer sur l'icône Claude dans la barre latérale (logo Anthropic)
- Ou `Ctrl+Shift+P` → taper "Claude Code" → sélectionner "Open Claude Code"

Un panneau de chat s'ouvre. C'est ici que l'on pose les questions.

---

## Partie 3 — Utiliser Claude Code pour suivre le projet (Claire · Arnaud)

### Comment ça fonctionne

Claude Code lit l'ensemble du dépôt — code, documentation, backlogs, RFCs — et
répond aux questions en langage naturel. Il n'invente pas : il cite les fichiers
sources dont il tire ses réponses. Si une information n'est pas dans le dépôt,
il le dit.

Le fichier de départ est [`docs/STATUS.md`](STATUS.md) — c'est le tableau de bord
du projet, mis à jour à chaque session de travail.

### Questions types à poser

Copier-coller ces questions dans le panneau Claude Code pour commencer :

---

**Suivi d'équipe**

```
Qui travaille sur quoi en ce moment ?
```

```
Qu'est-ce que Simon est en train de faire ?
```

```
Qu'est-ce qui a été livré cette semaine ?
```

```
Qu'est-ce qui bloque Félix en ce moment ?
```

---

**Fonctionnalités et backlog**

```
Où est suivie la fonctionnalité de sécurité des prompts ?
```

```
Quel est l'état de la fonctionnalité de mémoire multi-agent ?
```

```
Qu'est-ce que CTRLP-03 et quel est son état d'avancement ?
```

```
Quelle est la prochaine priorité pour Dimitri ?
```

---

**Tests et qualité**

```
Quels tests couvrent la fonctionnalité de configuration MCP ?
```

```
Quels fichiers de test sont liés à la sécurité des prompts ?
```

```
Comment lancer les tests du projet ?
```

---

**Architecture et documentation**

```
Quelle est la différence entre le mode standalone et le mode full-stack ?
```

```
Comment fonctionne l'authentification dans Fred ?
```

```
Où est documentée la stratégie de branches ?
```

---

**Planification**

```
Quelles tâches sont planifiées pour les prochains jours ?
```

```
Qu'est-ce qui doit être fait avant que Félix puisse commencer la phase CHAT-03 ?
```

```
Résume le plan de sprint actuel en 5 points.
```

---

### Conseils pour de meilleures réponses

| À faire                                                | À éviter                                                   |
| ------------------------------------------------------ | ---------------------------------------------------------- |
| Questions précises : _"Qu'est-ce que fait Simon ?"_    | Questions trop vagues : _"Tout va bien ?"_                 |
| Utiliser les noms des personnes, features, ou fichiers | Abréviations inconnues sans contexte                       |
| Demander _"où est-ce documenté ?"_ pour naviguer       | Supposer que Claude connaît le contexte extérieur au dépôt |
| Reformuler si la réponse semble incomplète             |                                                            |

### Astuce : naviguer vers un fichier depuis une réponse

Quand Claude mentionne un fichier (ex. `docs/STATUS.md`), il crée souvent un lien
cliquable. Un clic ouvre le fichier directement dans l'éditeur. Plus besoin de
chercher manuellement dans l'arborescence.

---

## Partie 4 — La boucle de feedback (pour tous)

**La qualité des réponses dépend de la qualité de la documentation.**

Si Claude répond de façon vague ou incomplète, ce n'est pas un bug — c'est un
signal : l'information n'est pas encore dans le dépôt, ou elle n'est pas assez
structurée. C'est utile comme feedback.

**Que faire quand une réponse est insuffisante :**

1. Noter la question posée
2. La signaler à Dimitri ou à la personne concernée
3. La documentation sera mise à jour dans la foulée
4. La même question donnera une meilleure réponse la prochaine fois

C'est volontaire : au lieu de maintenir un Jira en parallèle du code, toute
l'information vit dans le dépôt et Claude sert d'interface de consultation.

---

## Partie 5 — Fichiers de référence utiles

| Fichier                                                  | Contenu                                                                | Usage quotidien                       |
| -------------------------------------------------------- | ---------------------------------------------------------------------- | ------------------------------------- |
| [`docs/STATUS.md`](STATUS.md)                            | Tableau de bord : en cours, livré cette semaine, bloqué, feature→tests | Première entrée pour Claire et Arnaud |
| [`docs/WORKPLAN.md`](WORKPLAN.md)                        | Sprint détaillé : qui fait quoi, dans quel ordre                       | Vue complète du sprint                |
| [`docs/backlog/BACKLOG.md`](backlog/BACKLOG.md)          | Toutes les phases de migration, items `[x]`/`[ ]`                      | Suivi de l'avancement global          |
| [`docs/platform/OPERATING_MODES.md`](OPERATING_MODES.md) | Standalone vs full-stack : quand utiliser quoi                         | Référence déploiement                 |
| [`docs/README.md`](../README.md)                         | Index de toute la documentation                                        | Navigation générale                   |

---

## Aide et questions

- **Problème d'installation VS Code / Claude Code** → contacter Simon, Florian, ou Dimitri
- **Accès au dépôt GitHub** → contacter Dimitri
- **Question sur une feature ou un item de backlog** → poser directement à Claude Code,
  puis escalader à Dimitri si la réponse est insuffisante

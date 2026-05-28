# Spec — Chat Message Rendering (CHAT-05)

**Status:** active — reference document  
**Author:** Dimitri Tombroff  
**Date:** 2026-05-21  
**Backlog ref:** `docs/swift/backlog/CHAT-UI-BACKLOG.md §5`  
**Parent RFC:** `docs/swift/rfc/CHAT-UI-REFONTE-RFC.md`

---

## 1. Contexte et périmètre

### 1.1 Stack de rendu

| Couche             | Paquet                             | Rôle                                                            |
| ------------------ | ---------------------------------- | --------------------------------------------------------------- |
| Rendu markdown     | `react-markdown`                   | Parser + composants React                                       |
| Extensions syntaxe | `remark-gfm`                       | Tables, task-lists, strikethrough                               |
| Math inline/bloc   | `remark-math`                      | Transforme `$…$` et `$$…$$` en nœuds hast                       |
| Rendu math         | `rehype-katex` + `katex`           | Compile les nœuds math en HTML KaTeX                            |
| Directives         | `remark-directive`                 | Active la syntaxe `:::details[…]`                               |
| Citations          | plugin interne `rehypeCitations`   | Transforme `[N]` en `<sup data-n>` avant sanitisation           |
| Sanitisation       | `rehype-sanitize`                  | Nettoie le HTML produit ; schéma étendu pour KaTeX et citations |
| Code coloré        | `react-syntax-highlighter` (Prism) | Coloration syntaxique dans `CodeBlock`                          |
| Diagrammes         | `mermaid`                          | Rendu SVG côté client dans `MermaidBlock`                       |

Le design system est atomic : tokens CSS dans `frontend/src/styles/`, composants organisés en `atoms → molecules → organisms → pages` sous `frontend/src/rework/components/`.

### 1.2 Périmètre

Ce document couvre :

- les règles CSS qui gouvernent la présentation des messages assistant ;
- les décisions de comportement (éléments supprimés, plugins activés) ;
- les principes de formatage du contenu (prompt système).

### 1.3 Ce que ce doc ne couvre pas

- Architecture des composants de la page chat (`ManagedChatPage`, `ChatMessagesArea`, `ConversationThread`) — voir CHAT-UI-REFONTE-RFC.md.
- Transport SSE et gestion d'état (`useChatSse`) — voir RUNTIME-EXECUTION-CONTRACT.md.
- Thèmes couleur (dark/light) — voir `colors-semantic-dark.css` / `colors-semantic-light.css`.
- L'algorithme de détection des fences ouverts pendant le streaming — voir `CHAT-09`
  / `STREAMING-RENDER-GUARD-RFC.md`. Ce document décrit le rendu visible, pas le parseur.

---

## 2. Décisions de présentation (CSS)

### 2.1 Largeur de lecture

**Règle :** `.root` du `MarkdownRenderer` applique `max-width: var(--content-prose-max-width)`.  
**Valeur :** `--content-prose-max-width: min(680px, 68ch)` — défini dans `frontend/src/styles/spacings.css`.  
**Pourquoi :** ~65–75 caractères par ligne correspond au confort de lecture établi par la typographie. Le `min()` plafonne dur à 680 px quelle que soit la taille de police, tout en restant responsive sur écrans étroits via `68ch`.

> Cette contrainte est posée sur `.root` uniquement, pas sur la `.lane` ni la bulle contenante. Le layout de la page reste pleine largeur ; seul le texte de la réponse est contraint.

### 2.2 Rythme vertical

**Règle :** pattern _lobotomized owl_ — `.root > * + * { margin-top: var(--spacing-m) }`.  
**Valeur :** `--spacing-m = 16px` entre blocs consécutifs.  
**Pourquoi :** un seul point de contrôle pour l'espacement ; les composants enfants ne posent pas de `margin` externe, ce qui évite les doubles marges. Les marges individuelles des éléments sont remises à 0 par `.root > * { margin: 0 }`.

Overrides :

| Contexte                                           | Token           | Valeur |
| -------------------------------------------------- | --------------- | ------ |
| Avant h1/h2/h3                                     | `--spacing-l`   | 24 px  |
| Avant h4/h5/h6                                     | `--spacing-l`   | 24 px  |
| Après h1/h2/h3 (rapproche le titre de son contenu) | `--spacing-xs`  | 8 px   |
| Après h4/h5/h6                                     | `--spacing-2xs` | 4 px   |

### 2.3 Hiérarchie typographique

Valeurs lues dans `MarkdownRenderer.module.css` :

| Balise    | `font`                                        | Poids  |
| --------- | --------------------------------------------- | ------ |
| `h1`      | `400 1.4rem / 1.33 var(--font-family-base)`   | normal |
| `h2`      | `400 1.2rem / 1.33 var(--font-family-base)`   | normal |
| `h3`      | `400 1.05rem / 1.4 var(--font-family-base)`   | normal |
| `h4`–`h6` | `var(--font-title-medium)` = `500 1rem / 1.5` | medium |

**Décisions :**

- Pas de `border-bottom` ni de filet sous les titres. La délimitation est assurée par le seul espacement vertical (§ 2.2).
- Poids `400` sur h1–h3 : les titres dans un message assistant ne doivent pas rivaliser avec l'interface principale.

### 2.4 Blocs de code (`CodeBlock`)

**Structure :** `<div.block>` contenant un header (label langue + bouton Copy) et le rendu `SyntaxHighlighter`.  
**Décisions :**

| Règle                  | Valeur                                               |
| ---------------------- | ---------------------------------------------------- |
| Bordure                | `0.5px solid var(--outline-muted)`                   |
| Border-radius          | `var(--radius-s)` = 8 px                             |
| Margin externe (block) | `var(--spacing-s)` = 12 px en haut et en bas         |
| Séparateur header/code | `border-bottom: 0.5px solid var(--outline-muted)`    |
| Fond du code           | `var(--surface-container-lowest)`                    |
| Overflow               | `overflow-x: auto` sur le `<pre>` via `customStyle`  |
| Font mono              | `"Geist Mono", "Fira Code", ui-monospace, monospace` |
| Taille de fonte        | `0.875rem`, line-height `1.6`                        |

Le `<pre>` wrapper de ReactMarkdown est remplacé par un fragment (`<>{children}</>`) afin que `<div.block>` soit enfant direct de `.root` et respecte le rythme vertical de § 2.2.

**Comportement streaming (CHAT-09) :**

- si un fence backtick non-Mermaid est encore ouvert pendant le streaming,
  `MarkdownRenderer` n'essaie pas de lancer la coloration syntaxique finale
- à la place, il affiche immédiatement un `CodeBlock` en mode streaming,
  avec le code brut en cours de génération et le label de langue détecté
- cette même prévisualisation `CodeBlock` est aussi utilisée pour ` ```mermaid `
  tant que le fence n'est pas fermé
- dès que le fence se ferme, le bloc repasse par le pipeline markdown normal et
  les fences non-Mermaid rendent leur version finale avec `react-syntax-highlighter`

### 2.5 Diagrammes Mermaid (`MermaidBlock`)

**Décision :** traitement visuel identique à `CodeBlock` — même `.block`, même `.header`, même bordure. Les deux composants partagent le même vocabulaire CSS pour la cohérence.

Spécificités Mermaid :

| Règle              | Valeur                                                                      |
| ------------------ | --------------------------------------------------------------------------- |
| Corps du diagramme | `display: flex; justify-content: center; overflow-x: auto`                  |
| Fond du corps      | `var(--surface-container-low)`                                              |
| SVG                | `max-width: 100%; height: auto; display: block`                             |
| Thème              | `"dark"` si `useIsDark()`, sinon `"default"`                                |
| Rendu              | asynchrone via `mermaid.render()` ; état loading affiché jusqu'à résolution |

**Comportement streaming (CHAT-09) :**

- si un fence Mermaid est encore ouvert pendant le streaming, `MarkdownRenderer`
  n'essaie pas de rendre un SVG incomplet
- à la place, il affiche immédiatement un `CodeBlock` en mode streaming,
  label `mermaid`, avec le code Mermaid brut en cours de génération
- dès que le fence se ferme, le bloc repasse par le pipeline markdown normal et
  `MermaidBlock` rend le SVG final

Le `diagramId` est dérivé de `useId()` pour garantir l'unicité sur une page avec plusieurs diagrammes.

### 2.6 Math KaTeX

**Décision :** le CSS KaTeX (`katex/dist/katex.min.css`) est importé globalement dans le point d'entrée de l'application, pas dans le module MarkdownRenderer. Raison : KaTeX génère des éléments avec des classes globales (`.katex`, `.katex-display`, etc.) ; un import scope-isolé par CSS module casserait la mise en page.

Override appliqué dans `MarkdownRenderer.module.css` :

```
.root :global(.katex-display) {
  overflow-x: auto;
  overflow-y: hidden;
  padding-bottom: var(--spacing-2xs);
}
```

**Pourquoi :** les formules larges débordent horizontalement sans `overflow-x: auto`. Le `padding-bottom` évite que les descentes KaTeX soient coupées par le scroll.

**Comportement streaming (CHAT-09) :**

- si un bloc `$$` est encore ouvert pendant le streaming, `MarkdownRenderer`
  n'essaie pas de rendre un nœud KaTeX incomplet
- à la place, il affiche immédiatement un `CodeBlock` en mode streaming,
  label `math`, avec la source brute en cours de génération
- dès que le délimiteur `$$` de fermeture arrive, le bloc repasse par le
  pipeline markdown normal et KaTeX rend la formule finale

### 2.7 Tables GFM

**Décision :** `display: block; overflow-x: auto; width: max-content; max-width: 100%` sur `<table>`.  
**Pourquoi :** les tables larges sont courantes dans les réponses agentiques (résultats SQL, comparatifs). `display: block` débloque le scroll horizontal sans casser le layout flex ou grid parent.

Mise en forme des cellules : bordure `0.5px`, padding `8px × 12px`, fond alterné sur les lignes paires via `var(--surface-container-lowest)`.

### 2.8 Collapsibles (`:::details`)

**Décision :** les directives `:::details[Titre]…:::` sont transformées en éléments natifs `<details><summary>` via le plugin interne `remarkDetailsDirective` (pipe après `remark-directive`). Pas de composant React dédié — le navigateur gère l'expand/collapse nativement.

Styling : bordure `0.5px`, `border-radius: var(--radius-s)`, fond `var(--surface-container-low)`. L'indicateur de pliage est un `▶` CSS rotatif sur `details[open]`.

**Comportement streaming (CHAT-09) :**

- si un bloc `:::details` (ou autre directive supportée par le garde) est encore
  ouvert pendant le streaming, `MarkdownRenderer` n'essaie pas de construire un
  `<details>` natif partiel
- à la place, il affiche immédiatement un `CodeBlock` en mode streaming,
  labellé avec le nom de directive, contenant la source brute en cours
- dès que `:::` de fermeture arrive, le bloc repasse par le pipeline markdown
  normal et le rendu natif `<details><summary>` prend le relais

### 2.9 Éléments supprimés

| Élément                 | Décision                                                      | Raison                                                                                                                                  |
| ----------------------- | ------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `<hr>` (markdown `---`) | Supprimé — `hr: () => null` dans les composants ReactMarkdown | Les séparateurs horizontaux sont du bruit visuel dans un contexte de chat. Les sections sont délimitées par les titres et l'espacement. |

---

## 3. Décisions de contenu (prompt système)

### 3.1 Principes de formatage

Ces principes gouvernent ce que les agents doivent produire pour être bien rendus par ce stack :

- **Prose par défaut.** Le markdown est utilisé quand il apporte une clarté réelle, pas pour habiller une réponse ordinaire.
- **Formatage parcimonieux.** Les listes à puces seulement pour des éléments parallèles de même nature. Les titres seulement quand la réponse contient plusieurs sections distinctes.
- **Pas de remplissage.** Ni ouvertures creuses ("Bien sûr ! Voici…"), ni résumés systématiques en fin de réponse.
- **Longueur calibrée.** Une réponse courte à une question courte ; une réponse longue seulement si la complexité le justifie.
- **Citations.** Les références aux sources utilisent la syntaxe `[N]` qui est transformée en badges cliquables par `rehypeCitations`.

### 3.2 Localisation dans le projet

Le prompt système de l'agent de référence (`fred.github.assistant`) vit dans :

```
apps/fred-agents/fred_agents/general_assistant.py  (constante _SYSTEM_PROMPT)
```

Les autres agents ont leur propre prompt dans leurs fichiers respectifs sous `apps/fred-agents/fred_agents/`. Le prompt est exposé comme champ `prompts.system` (type `prompt`) dans le formulaire de configuration de l'agent, ce qui permet à un administrateur de l'override depuis l'interface sans modifier le code.

---

## 4. Fichiers concernés

Tous les chemins sont relatifs à la racine du dépôt.

| Fichier                                                                                        | Rôle                                                                                  |
| ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `frontend/src/rework/components/shared/molecules/MarkdownRenderer/MarkdownRenderer.tsx`        | Composant principal — plugins, overrides ReactMarkdown                                |
| `frontend/src/rework/components/shared/molecules/MarkdownRenderer/MarkdownRenderer.module.css` | CSS du rendu : largeur de lecture, rythme vertical, typographie, tables, collapsibles |
| `frontend/src/rework/components/shared/molecules/CodeBlock/CodeBlock.tsx`                      | Bloc de code coloré avec header lang/copy                                             |
| `frontend/src/rework/components/shared/molecules/CodeBlock/CodeBlock.module.css`               | CSS du bloc de code                                                                   |
| `frontend/src/rework/components/shared/molecules/MermaidBlock/MermaidBlock.tsx`                | Rendu Mermaid SVG avec header et états loading/error                                  |
| `frontend/src/rework/components/shared/molecules/MermaidBlock/MermaidBlock.module.css`         | CSS identique au CodeBlock (header + corps)                                           |
| `frontend/src/rework/components/shared/molecules/MarkdownRenderer/streamingGuard.ts`           | Garde de streaming : séparation `stableMarkdown` / `pendingFence`                     |
| `frontend/src/rework/components/shared/molecules/MarkdownRenderer/streamingGuard.test.ts`      | Tests unitaires du garde de streaming                                                 |
| `frontend/src/rework/components/shared/atoms/SourceBadge/SourceBadge.tsx`                      | Badge citation cliquable rendu par `rehypeCitations`                                  |
| `frontend/src/styles/spacings.css`                                                             | Token `--content-prose-max-width` et `--spacing-*`                                    |
| `frontend/src/styles/typography.css`                                                           | Tokens `--font-*`                                                                     |
| `frontend/src/styles/radius.css`                                                               | Token `--radius-s` = 8 px (utilisé par CodeBlock et MermaidBlock)                     |
| `apps/fred-agents/fred_agents/general_assistant.py`                                            | Prompt système de l'agent de référence (`_SYSTEM_PROMPT`)                             |

---

## 5. Critères d'acceptation / non-régression

La checklist suivante doit passer après toute modification touchant au rendu des messages.

- [ ] **Largeur prose** : en DevTools (élément `.root`), `max-width` résolu = `min(680px, 68ch)`. À 16 px de font-size par défaut, `68ch ≈ 680 px` donc le plafond est atteint sur un écran desktop standard.
- [ ] **Densité de texte** : à 100 % de zoom, une ligne de prose tient ~68–72 caractères (vérifiable avec une règle dans DevTools).
- [ ] **Titres sans filet** : aucune `border-bottom` visible sous h1, h2, h3. La délimitation est assurée par le seul espacement.
- [ ] **Rythme vertical** : deux paragraphes consécutifs sont séparés de 16 px (`--spacing-m`). Un titre précédé d'un paragraphe est séparé de 24 px (`--spacing-l`).
- [ ] **Blocs de code** : le header affiche le label langue + bouton Copy. Le bouton change en "✓ Copied" pendant 2 s. Le contenu scrolle horizontalement sans casser le layout.
- [ ] **Code streaming** : avant fermeture d'un fence ` ```python ` (ou autre langage non-Mermaid), l'UI affiche un `CodeBlock` de prévisualisation avec le code brut en cours, sans coloration finale cassée ni fuite du fence brut dans la prose.
- [ ] **Mermaid** : le diagramme du test assistant (`graph TD`) se rend en SVG. En mode dark, le thème Mermaid bascule. L'état de chargement ("Rendering diagram…") est visible pendant le rendu asynchrone.
- [ ] **Mermaid streaming** : avant fermeture d'un fence ` ```mermaid `, l'UI affiche un `CodeBlock` de prévisualisation labellé `mermaid` avec le code brut en cours, sans `Diagram error` ni bulle vide.
- [ ] **Formules KaTeX** : `$x = \frac{-b}{2a}$` est rendu inline sans caractères bruts. `$$\sum_{k=1}^{n} k$$` est rendu en display math, scrollable horizontalement si la formule dépasse la largeur.
- [ ] **Math streaming** : avant fermeture d'un bloc `$$`, l'UI affiche un `CodeBlock` de prévisualisation labellé `math`, sans parse-error KaTeX transitoire.
- [ ] **Tables** : une table GFM s'affiche avec bordures, fond alterné sur les lignes paires, et scroll horizontal si la table dépasse la largeur disponible.
- [ ] **Collapsibles** : `:::details[Titre]…:::` affiche un `<details>` natif fermé par défaut, avec l'indicateur `▶` qui pivote à l'ouverture.
- [ ] **Directive streaming** : avant fermeture d'un bloc `:::details`, l'UI affiche un `CodeBlock` de prévisualisation labellé `details`, puis bascule sur le rendu `<details>` final une fois le bloc complet.
- [ ] **Citations** : `[1]` dans le texte produit un `<SourceBadge>` cliquable si `onSourceClick` est fourni.
- [ ] **Pas de `<hr>`** : markdown contenant `---` ne produit aucun élément visuel dans le rendu.
- [ ] **TypeScript** : `npx tsc --noEmit` passe sans erreur sur le frontend après toute modification.

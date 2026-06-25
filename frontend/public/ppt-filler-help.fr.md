# Remplisseur PowerPoint — comment ça marche

La boîte à outils **Remplisseur PowerPoint** transforme un agent en générateur de
présentations PowerPoint prêtes à envoyer, à votre charte. Vous fournissez **votre
propre** modèle `.pptx` ; l'agent extrait les bonnes valeurs de la conversation (et des
documents joints) et remplit votre modèle à votre place. L'utilisateur reçoit un lien de
téléchargement de la présentation terminée.

Vous gardez la maîtrise du design : le modèle téléversé fait foi. C'est vous qui décidez
où vont les valeurs et comment chacune doit être remplie.

---

## Ce que vous téléversez

Un seul modèle `.pptx`. À l'intérieur, vous marquez les emplacements à remplir avec des
**clés** et vous décrivez chaque clé dans les **notes** de la diapositive concernée.

### 1. Marquez les valeurs avec `{{clé}}`

Dans n'importe quelle zone de texte, écrivez une clé entre doubles accolades :

```
Client : {{nomClient}}
Mission : {{mission}}
```

- Réutilisez la **même clé plusieurs fois sur une diapositive** pour répéter une valeur
  (par exemple un nom dans un en-tête et un pied de page) — chaque occurrence reçoit la
  même valeur.
- La **même clé sur une autre diapositive est indépendante** — elle a sa propre
  description et sa propre valeur.

### 2. Décrivez chaque clé dans les notes

Ouvrez les **notes** de la diapositive (Affichage → Notes) et, pour chaque clé, écrivez
une ligne d'en-tête `{{clé}}:` suivie d'une description libre. La description indique à
l'agent quoi mettre à cet endroit.

```
{{nomClient}}:
Le nom de l'entreprise cliente à qui la proposition est adressée.

{{mission}}:
Un résumé en une phrase de la mission, rédigé pour un public métier.
```

Une ligne n'est un en-tête **que** si elle est composée d'une ou plusieurs clés `{{clé}}`
se terminant par deux-points. Une ligne qui mentionne simplement `{{quelque chose}}` au
milieu d'une phrase est traitée comme du texte de description ordinaire — vous pouvez donc
écrire naturellement.

---

## La notation en détail

### Descriptions sur plusieurs lignes

Une description s'étend de son en-tête jusqu'à l'en-tête suivant (ou la fin des notes) :
elle peut donc occuper plusieurs lignes, y compris des lignes vides :

```
{{contexte}}:
Le contexte métier de la mission.

Mentionnez le secteur du client et les principales contraintes
(réglementaires, techniques, budgétaires).
```

### Une description pour plusieurs clés

Décrivez des clés liées ensemble en les listant, séparées par des virgules, sur la ligne
d'en-tête. Elles reçoivent toutes la même description :

```
{{prenom}}, {{nom}}:
Le nom du consultant, tel qu'il doit apparaître sur la diapositive de couverture.
```

### Conserver de vraies notes du présentateur dans le résultat

Par défaut, vos descriptions `{{clé}}:` sont des **instructions de configuration** et sont
**retirées** de la présentation générée — l'utilisateur ne les voit jamais.

Si vous souhaitez en plus conserver de **vraies notes du présentateur** dans le résultat,
ajoutez une ligne de **tirets (au moins trois)** après vos descriptions. Tout ce qui se
trouve **en dessous** de cette ligne est conservé tel quel dans la présentation générée ;
tout ce qui est au-dessus (les descriptions) est supprimé.

```
{{mission}}:
Un résumé en une phrase de la mission.

---
Note du présentateur : garder cette diapositive sous deux minutes et finir sur le budget.
```

Dans la présentation générée, les notes de cette diapositive ne contiendront que :

```
Note du présentateur : garder cette diapositive sous deux minutes et finir sur le budget.
```

Une ligne de moins de trois tirets (par exemple `--`) n'est **pas** un séparateur et reste
du texte ordinaire.

---

## Retour immédiat

Lorsque vous téléversez un modèle, il est analysé immédiatement et vous voyez, **par
diapositive**, les clés détectées avec leurs descriptions — avant même d'enregistrer
l'agent.

Si quelque chose ne va pas, vous recevez un message clair, numéroté par diapositive :

- **Une clé sans description** — un `{{clé}}` apparaît dans une zone de texte mais n'est
  pas décrit dans les notes de cette diapositive. Ajoutez la description manquante.
- **Une description pour une clé absente** — les notes décrivent un `{{clé}}` qui
  n'apparaît dans aucune zone de texte de cette diapositive. Corrigez la faute de frappe
  ou supprimez la description obsolète.

Vous ne pouvez pas enregistrer l'agent tant que le modèle n'est pas valide : une
configuration cassée n'atteint donc jamais vos utilisateurs.

---

## Bon à savoir

- Seules les **zones de texte** standard sont remplies. Les cellules de tableau et les
  formes groupées ne sont pas encore prises en charge.
- L'agent déduit les **valeurs** à partir de la conversation et de vos descriptions —
  gardez les descriptions précises pour qu'il remplisse la bonne chose.
- Remplacer le modèle le réanalyse ; le schéma correspond toujours au fichier réel.

# Template de PowerPoint — comment ça marche

Cette capacité permet à un agent de remplir un PowerPoint à trous, à partir d'instructions et de fichiers mis à sa disposition. Elle sert lorsque vous avez un format fixe de PowerPoint à reproduire régulièrement en ne changeant que le contenu.

![Deux power point: un d'entrée avec des balises de template, un autre remplis par un agent (résultat)](/ppt-filler/introduction.png)

## Comment créer un template de PowerPoint

Pour que votre agent puisse remplir votre PowerPoint, vous devez identifier chaque zone qu'il devra compléter et lui associer une description.

### 1. Marquez les zones à remplir

Dans une zone de texte, écrivez une **clé** entre doubles accolades à l'endroit où une valeur doit apparaître :

```
{{nom}}
```

Vous pouvez réutiliser la même clé plusieurs fois sur une diapositive pour répéter la même valeur. La même clé sur une autre diapositive est, elle, indépendante.

### 2. Décrivez chaque clé dans les notes

Dans les **notes** de la diapositive (Affichage → Notes), écrivez pour chaque clé une ligne d'en-tête `{{clé}}:` suivie d'une description. Elle indique à l'agent quoi mettre à cet endroit :

```
{{nom}}:
Nom du collaborateur, à trouver dans le CV.
```

Une ligne n'est un en-tête que si elle se compose d'une ou plusieurs clés `{{clé}}` terminées par deux-points. Une clé citée au milieu d'une phrase reste du texte ordinaire — vous pouvez donc écrire naturellement.

![Une diapositive avec des clés entre doubles accolades dans ses zones de texte, et les notes de la diapositive décrivant chaque clé.](/ppt-filler/template.png)

## Utilisation avancée

### Description multi-ligne

Une description s'étend de son en-tête jusqu'à l'en-tête suivant (ou la fin des notes) : elle peut donc occuper plusieurs lignes, y compris des lignes vides.

```
{{contexte}}:
Le contexte métier de la mission.

Mentionnez le secteur du client et ses principales contraintes.

{{objectifs}}:
Les objectifs de la mission, sous forme de liste à puces.

Trois à cinq points maximum, formulés pour un public métier.
```

### Assigner une description à plusieurs clés

Listez plusieurs clés séparées par des virgules sur la ligne d'en-tête pour leur donner la même description. C'est utile quand une diapositive répète la même structure plusieurs fois — par exemple un CV avec trois sections décrivant les trois dernières expériences, chacune avec un titre et une description :

```
{{titreExperience1}}, {{titreExperience2}}, {{titreExperience3}}:
L'intitulé du poste et l'entreprise, du plus récent au plus ancien.

{{descriptionExperience1}}, {{descriptionExperience2}}, {{descriptionExperience3}}:
Un résumé des missions et réalisations, dans le même ordre que les titres.
```

### Conserver de vraies notes du présentateur

Par défaut, vos descriptions `{{clé}}:` sont des instructions de configuration et sont retirées de la présentation générée. Pour conserver de vraies notes du présentateur, ajoutez une ligne d'au moins **trois tirets** : tout ce qui se trouve en dessous est gardé tel quel dans le résultat.

```
{{mission}}:
Un résumé en une phrase de la mission.

---
Note au présentateur : garder cette diapositive sous deux minutes.
```

## Ajouter des images

Une clé peut aussi être remplie par une **image** plutôt que par du texte. L'agent choisit une image dans un dossier de vos ressources et la place dans votre diapositive.

### 1. Marquez l'emplacement de l'image

Dessinez une forme — un rectangle ou une zone de texte — à l'endroit où l'image doit apparaître, et écrivez-y une `{{clé}}`. La position et la taille de la forme deviennent le cadre de placement de l'image.

```
{{drapeauPays}}
```

### 2. Déclarez-la comme image dans les notes

Sous l'en-tête de la clé dans les notes, ajoutez un bloc de métadonnées : une ligne `- type:` / `- folder:` par réglage, juste sous l'en-tête et avant la description.

```
{{drapeauPays}}:
- type: image
- folder: "images/drapeaux"
Choisissez le drapeau correspondant au pays évoqué.
```

- `type: image` indique à l'agent de placer une image. La valeur par défaut est `text` : les clés ordinaires n'ont donc rien à déclarer.
- `folder:` désigne un dossier de vos ressources importées — votre espace personnel ou celui de votre équipe. Les guillemets sont facultatifs, et les mots-clés comme les valeurs sont insensibles à la casse.

### Proposer plusieurs emplacements d'image

Un en-tête à plusieurs clés partage un même dossier et une même consigne — pratique pour proposer plusieurs emplacements configurés en une fois :

```
{{logo1}}, {{logo2}}, {{logo3}}:
- type: image
- folder: "images/logos-partenaires"
Ajoutez les logos des partenaires mentionnés, du plus important au moins important.
```

Vous pouvez proposer N emplacements d'image et demander à l'agent (dans la description) de n'utiliser que ceux qui conviennent. **Les emplacements d'image inutilisés sont supprimés** — aucune zone vide n'apparaît dans la présentation. (Les clés de texte omises deviennent, elles, du texte vide, comme auparavant.)

### Bon à savoir

- L'image est mise à l'échelle pour **tenir à l'intérieur** du cadre de la forme, en conservant son rapport hauteur/largeur et centrée — sans déformation ni rognage.
- Une clé d'image répétée (la même clé dans plusieurs formes d'une diapositive) reçoit la même image partout, comme les clés de texte répétées.
- Les vraies notes du présentateur situées après le séparateur `---` ne sont pas touchées.
- Le dossier doit être un dossier réel de votre espace. Il est vérifié au moment où vous choisissez le template, puis de nouveau à l'enregistrement.

## Erreurs

Quand vous uploadé un template de PowerPoint, il est analysé immédiatement. Tant qu'une erreur subsiste, l'agent ne peut pas être enregistré. Plusieurs cas peuvent se présenter :

- **Une clé sans description** — une `{{clé}}` apparaît dans une zone de texte mais n'est pas décrite dans la note de la diapositive -> Il faut ajoutez la description manquante dans les notes
- **Une description pour une clé absente** — les notes décrivent une `{{clé}}` qui n'apparaît dans aucune zone de texte de la diapositive -> Corrigez la faute de frappe, supprimez la description obsolète ou ajouter la clé manquante à la diapositive
- **Un mot-clé de métadonnée inconnu** — une ligne de métadonnée utilise un mot-clé autre que `type` ou `folder` -> Corrigez la faute de frappe ; seuls `type` et `folder` sont reconnus
- **Un type inconnu** — la valeur de `type:` n'est ni `text` ni `image` -> Utilisez l'une de ces deux valeurs
- **Une métadonnée en double** — le même mot-clé de métadonnée apparaît deux fois dans le bloc d'une clé -> Supprimez la ligne en double
- **Une image sans dossier** — une clé est de `type: image` mais n'a aucun dossier -> Ajoutez une ligne `- folder: "..."` pointant vers vos ressources
- **Un dossier vide** — une ligne `folder:` est vide -> Renseignez le chemin du dossier
- **Un dossier sur une clé qui n'est pas une image** — un `folder:` est défini sur une clé qui n'est pas une image -> Ajoutez `- type: image`, ou supprimez la ligne de dossier
- **Un dossier introuvable** — le dossier indiqué n'existe pas dans votre espace (personnel ou équipe) -> Corrigez le nom, ou créez le dossier et importez-y des fichiers
- **Une clé d'image à un emplacement invalide** — une clé d'image se trouve à un endroit qui ne peut pas contenir d'image, comme une cellule de tableau -> Déplacez-la dans une zone de texte ou un rectangle

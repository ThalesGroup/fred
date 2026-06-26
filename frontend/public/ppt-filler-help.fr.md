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

<!-- ### Templétiser des images

todo: a ajouter quand la feature sera prète
 -->

## Erreurs

Quand vous uploadé un template de PowerPoint, il est analysé immédiatement. Tant qu'une erreur subsiste, l'agent ne peut pas être enregistré. Deux cas peuvent se présenter :

- **Une clé sans description** — une `{{clé}}` apparaît dans une zone de texte mais n'est pas décrite dans la note de la diapositive -> Il faut ajoutez la description manquante dans les notes
- **Une description pour une clé absente** — les notes décrivent une `{{clé}}` qui n'apparaît dans aucune zone de texte de la diapositive -> Corrigez la faute de frappe, supprimez la description obsolète ou ajouter la clé manquante à la diapositive

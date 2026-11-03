---
title: Créer un thème personnalisé
order: 30
description: Ajouter un thème aux couleurs de votre organisation, sans toucher aux autres.
icon: tune
---

# Créer un thème personnalisé

Un thème personnalisé s'ajoute à Pebble, Cobalt et Cloud : les utilisateurs le
choisissent dans leur profil, et un **Platform admin** peut en faire le thème
par défaut. Il est livré dans une archive ZIP que l'équipe qui déploie
l'application installe avec le frontend.

> Ce guide s'adresse à qui prépare le ZIP. Le déploiement (étape 5) demande un
> accès au stockage de l'archive ; le choix des thèmes proposés (étape 6) se
> fait dans la console d'administration.

## Le contenu de l'archive

```
theme.zip
|-- theme-catalog.json          les thèmes à ajouter
|-- themes/
|   `-- acme/
|       |-- theme-custom.css    couleurs, polices et formes d'Acme
|       `-- images/             icônes et illustrations d'Acme
`-- shared/                     contenu commun à tous les thèmes
    |-- images/                 logos et polices communs
    |-- theme-properties.json
    `-- theme-translations/
```

Un ZIP fait à partir d'un dossier (`zip -r theme.zip mon-theme/`) est accepté :
le dossier englobant est ignoré. Les anciens ZIP plats restent compatibles.
Les noms d'images doivent être uniques entre les dossiers de thème et `shared/images/`.

## 1. Déclarer le thème

`theme-catalog.json` liste les thèmes ajoutés (16 au plus) :

```json
{
  "themes": [
    {
      "id": "acme",
      "label": "Acme",
      "base": "pebble",
      "tabTitle": "Acme Portal",
      "faviconName": "acme-favicon-light",
      "faviconNameDark": "acme-favicon-dark"
    }
  ]
}
```

| Champ             | Rôle                                                                   |
| ----------------- | ---------------------------------------------------------------------- |
| `id`              | Identifiant unique, en minuscules, 32 caractères au plus.              |
| `label`           | Nom affiché dans le profil et l'administration.                        |
| `base`            | `pebble`, `cobalt` ou `cloud` : le thème dont il hérite tout le reste. |
| `tabTitle`        | Optionnel. Titre de l'onglet du navigateur avec ce thème.              |
| `faviconName`     | Optionnel. Icône de l'onglet en mode clair.                            |
| `faviconNameDark` | Optionnel. Icône en mode sombre ; à défaut, celle du mode clair.       |

Les icônes sont des fichiers SVG de `images/`, donnés **sans** l'extension
`.svg`. Sans ces champs, l'onglet garde son titre et son icône habituels. En
revenant à un autre thème, l'onglet reprend aussi les siens.

Gardez le même `id` lors de la mise à jour du ZIP d'un thème. La plateforme enregistre
cet ID dans les préférences de chaque utilisateur, et un redémarrage du
frontend n'en crée pas un nouveau. L'archive refuse les doublons et les ID
réservés à Galet, Cobalt et Nuage. Choisissez un nouvel ID seulement pour un
thème différent.

## 2. Couleurs, polices et formes

`themes/<id>/theme-custom.css` ne contient que les différences avec le thème de base.
Chaque règle cible le thème par son `id` **et** sa base, sans préfixe `html` :

```css
[data-ui-theme="acme"][data-ui-base-theme="pebble"][data-theme="light"] {
  --primary: #0b6e4f;
  --on-primary: #ffffff;
}

[data-ui-theme="acme"][data-ui-base-theme="pebble"][data-theme="dark"] {
  --primary: #ffffff;
  --on-primary: #0b6e4f;
}
```

La base dans le sélecteur fait passer vos règles avant celles du thème livré ;
l'absence de `html` permet aux aperçus de l'administration de les afficher.
Les couleurs demandent toujours les trois attributs, même pour retoucher Pebble,
Cobalt ou Cloud eux-mêmes. Une règle sans `[data-theme]` s'applique aux deux
modes, par exemple pour la police :

```css
@font-face {
  src: url("/images/fonts/MaPolice.ttf") format("truetype");
  font-family: "Ma police";
}

[data-ui-theme="acme"][data-ui-base-theme="pebble"] {
  --font-family-base: "Ma police", Arial, sans-serif;
}
```

## 3. Images propres au thème

Les fichiers de `themes/<id>/images/` sont servis depuis `/images/` à tous, mais seul le CSS de votre thème
les utilise. Pour le fond du chat ou l'avatar de l'agent d'accueil, ciblez
`[data-chat-main]`, `[data-chat-welcome-agent]` ou `[data-chat-agent-icon]`
sous `html[data-ui-theme="<id>"]` : les autres thèmes n'en voient rien.

Les navigateurs gardent les images en cache. Pour en changer une, donnez au
nouveau fichier un **nouveau nom** plutôt que d'écraser l'ancien.

## 4. Ce qui est commun à tous les thèmes

Deux fichiers optionnels de l'archive s'appliquent à **tous** les thèmes, y
compris Pebble, Cobalt et Cloud :

- `shared/theme-properties.json` : nom du site, logos, surnoms des agents, avatars par
  défaut, lien du support ;
- `shared/theme-translations/fr.json` et `en.json` : les textes de l'interface.

Tout texte de l'interface peut être renommé ainsi, et « Agents » par les
surnoms des agents, mais pour toute la plateforme : deux thèmes d'une même
archive ne peuvent pas avoir des textes différents.

Pour un thème qui ne déborde pas sur les autres, laissez-les absents ou neutres,
et portez l'identité du thème par le catalogue et le CSS.

## 5. Installer l'archive

Déposez le ZIP à l'emplacement de stockage configuré pour le frontend, puis
redémarrez le frontend : l'archive n'est lue qu'au démarrage. Les utilisateurs
déjà connectés reçoivent le thème en rechargeant la page.

## 6. Proposer le thème

Dans la console d'administration, la page **Interface utilisateur** montre le
nouveau thème à côté des autres, avec son aperçu clair et sombre. Proposez-le
aux utilisateurs, et choisissez **Définir par défaut** si tout le monde doit
l'avoir tant qu'il n'en a pas choisi d'autre. Voir
[L'administration](/help/fr/features/administration).

## Si le thème n'apparaît pas

- **Aucun thème ajouté n'apparaît** : l'archive a été refusée. Les journaux du
  frontend l'indiquent, par exemple
  `Theme skipped, serving the stock assets: invalid theme-catalog.json`.
  Vérifiez le catalogue : un champ inconnu, un `id` en majuscules ou un nom
  d'icône avec `.svg` suffisent à le refuser.
- **L'onglet garde l'ancienne icône** : le fichier SVG manque dans `images/`, ou
  le navigateur l'a en cache ; changez son nom.
- **Le thème n'est pas dans le profil** : il est peut-être masqué dans
  **Interface utilisateur**.

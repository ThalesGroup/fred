---
title: Administration de la plateforme
order: 60
description: Ce qui dépasse une seule équipe, et pourquoi vous n'y avez sans doute pas accès.
icon: admin_panel_settings
---

# Administration de la plateforme

Certaines décisions dépassent le cadre d'une équipe : quelles équipes existent,
quelles fonctions leur sont ouvertes, qui détient un rôle de plateforme. Elles
vivent dans la **console d'administration**.

> L'accès à ces surfaces est réservé aux rôles de plateforme (voir
> [Équipes et droits](/help/fr/features/teams-and-permissions)) : ne pas les
> voir correspond au fonctionnement attendu. Cette page indique à qui adresser
> une demande.

## Y accéder

**Menu profil** (en bas du panneau de navigation) → **Administration**. Chacun
arrive sur la première page qu'il a le droit de voir ; deux administrateurs
n'accèdent donc pas nécessairement à la même page.

## Ce qu'on y trouve

- **Équipes** — la liste de toutes les équipes, et leur création.
- **Rôles plateforme** — qui détient quel rôle transverse.
- **Utilisateurs** — les comptes de la plateforme.
- **Fonctionnalités** — le catalogue des fonctions et leur ouverture par équipe.
- **Prompt global** — les instructions communes ajoutées en tête des
  instructions de chaque agent.
- **Interface utilisateur** — le thème proposé par défaut et les thèmes
  disponibles pour les utilisateurs.
- **Annonces** — les bandeaux et les patch notes affichés aux utilisateurs.
- **Analytiques** — les indicateurs d'usage à l'échelle de la plateforme.
- **Activité** — les traitements en cours et leur historique.
- **Auto-test** et **Audit du corpus** — les vérifications de bon
  fonctionnement.
- **Données plateforme** — export et import de l'état de la plateforme.

## Le thème de l'interface

Chaque utilisateur choisit son thème (Galet, Cobalt, Nuage…) et son mode clair,
sombre ou système dans **Profil** → **Interface : thème et mode**.

Sur la page **Interface utilisateur**, chaque thème a sa tuile, avec ses trois
couleurs principales. Un **Admin plateforme** y décide :

- des **thèmes proposés** : un thème désactivé disparaît du profil des
  utilisateurs ;
- du **thème par défaut**, avec **Définir par défaut** : celui des
  utilisateurs qui n'ont encore rien choisi. Galet l'est tant que rien n'a été
  changé. Le thème par défaut reste toujours proposé.

Chaque changement est enregistré aussitôt.

Un utilisateur dont le thème n'est plus proposé passe au thème par défaut. Son choix est conservé : il le retrouve si le thème est de nouveau proposé. Choisir
un thème dans son profil, même celui déjà affiché, le garde ensuite si le thème
par défaut change. Si un seul thème est proposé, le
profil n'affiche plus que le mode. Les changements s'appliquent au prochain
chargement de l'application par chaque utilisateur.

## Les annonces

La page **Annonces** permet à un **Admin plateforme** de s'adresser à tous les
utilisateurs. Elle propose deux types d'annonce :

- le **bandeau** : un message court, affiché en haut de l'application tant
  qu'il est actif. Il convient à une information du moment (une maintenance,
  un incident). Plusieurs bandeaux peuvent être actifs en même temps ;
- le **patch note** : un texte plus long, présenté dans une fenêtre quand
  l'utilisateur arrive sur l'application. Il convient à la présentation d'une
  nouvelle version.

Pour en créer une, cliquez sur **Nouvelle annonce**, puis choisissez
**Bandeau** ou **Patch note** : le formulaire correspondant s'ouvre aussitôt.

Les deux types apparaissent dans la même liste. Un patch note s'y affiche dans
un style neutre, sous son titre, avec le nombre d'utilisateurs qui l'ont
masqué.

### Rédiger un patch note

Choisir **Patch note** ouvre l'éditeur. Commencez par le **Titre du patch
note** : du texte simple qui nomme le patch note dans la liste et en haut de la
fenêtre que voient les utilisateurs. Le texte en dessous s'écrit en Markdown
(titres, listes, liens). Titre et texte s'écrivent en français et en anglais :
le sélecteur de langue passe de l'une à l'autre. Chaque langue remplie doit
avoir un titre et un texte. Un aperçu se met à jour à côté du texte pendant la
saisie. Si vous fermez l'éditeur avec des modifications non enregistrées, une
confirmation vous est demandée avant de les perdre.

Sur un patch note inactif, **Enregistrer** le garde sans le montrer aux
utilisateurs : activez-le dans la liste quand il est prêt, ou utilisez
**Enregistrer et activer** pour faire les deux à la fois.

**Aperçu côté utilisateurs** ouvre la fenêtre exacte que verront
les utilisateurs, avec le texte en cours, même s'il n'est pas encore
enregistré. Le même aperçu est disponible depuis la liste. Un aperçu n'a aucun
effet : cocher **Ne plus afficher** dedans n'enregistre rien.

### Un seul patch note actif à la fois

Activer un patch note désactive celui qui l'était. Avant cela, une
confirmation nomme le patch note qui sera désactivé. Les bandeaux ne sont pas
concernés.

Désactiver puis réactiver un patch note le remontre à tout le monde, même à
ceux qui avaient coché **Ne plus afficher**. Le modifier pendant qu'il est actif
ne le remontre pas. Pour annoncer une nouvelle version, créez un nouveau
patch note : il sera présenté à tout le monde. Un patch note activé pendant
qu'un utilisateur travaille lui est présenté à son prochain chargement de
l'application. Les utilisateurs peuvent aussi rouvrir le patch note actif à
tout moment depuis leur menu de profil, sous **Nouveautés**.

### L'historique des activations

En haut de la page, le sélecteur **Annonces** / **Historique** passe de la
liste des annonces à l'historique. L'**Historique** est un tableau des
dernières activations et désactivations, bandeaux et patch notes confondus, les
plus récentes en premier : l'annonce, son type, l'action, la date et l'heure,
et l'administrateur qui l'a faite. Le type d'un bandeau reprend sa couleur.
Un clic sur le titre d'une colonne trie le tableau. Les filtres **Tout**,
**Activations** et **Désactivations** au-dessus du tableau n'affichent qu'un
type d'action ; votre choix est gardé pour la prochaine fois. Une
désactivation automatique (quand un autre patch note est activé) y figure au
nom de l'administrateur qui a fait l'activation. L'historique reste
consultable après la suppression d'une annonce.

## Qui ouvre les fonctions à votre équipe

L'ouverture d'une fonction relève d'un **Admin plateforme** ou d'un
**Gestionnaire de fonctionnalités**, jamais d'un administrateur d'équipe. C'est
pourquoi une fonction peut apparaître comme non autorisée dans la configuration
d'un agent : personne dans votre équipe ne peut l'ouvrir, la demande doit être
adressée à la plateforme.

Lorsqu'une fonction déjà utilisée par un agent est refermée, cet agent est
**suspendu** jusqu'à son rétablissement.

## Deux pages d'usage, à ne pas confondre

- **L'usage de votre équipe** — la page **Usage** de l'équipe : la consommation
  dans le temps, par agent et par modèle, plus votre part personnelle. La vue
  d'ensemble de l'équipe demande un rôle **Admin**, **Éditeur** ou
  **Analyste** ; un simple Membre ne voit que sa propre consommation.
- **L'usage de la plateforme** — la page **Analytiques** de la console, à
  l'échelle de tous les utilisateurs. Elle demande le rôle **Observateur
  plateforme**.

Les deux pages ne font donc pas double emploi : leurs périmètres et leurs
conditions d'accès diffèrent.

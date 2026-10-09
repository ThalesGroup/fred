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
- **Prompts plateforme** — deux onglets : le **prompt système plateforme**,
  les instructions communes ajoutées en tête des instructions de chaque
  agent, et l'**assistant de création**, qui aide à préparer un agent depuis
  son formulaire. Pour l'assistant, vous pouvez adapter ses instructions puis
  les rétablir à tout moment (gardez-y le texte `{language}`, remplacé par la
  langue de l'utilisateur), et choisir le modèle qu'il utilise ; par défaut, le
  modèle par défaut de la plateforme. Le réglage **Raisonnement** à côté
  laisse ce modèle réfléchir avant de répondre quand il en est capable. Il
  est désactivé par défaut : dans nos essais, il rendait les propositions
  plus lentes et plus coûteuses sans les améliorer nettement ; nous
  recommandons donc un modèle intermédiaire sans raisonnement. Selon le modèle,
  c'est un interrupteur ou un choix de niveaux de Désactivé à Élevé ; plus le
  niveau est élevé, plus il réfléchit longtemps. Quand le raisonnement tarde,
  l'assistant interroge aussi le même modèle sans raisonnement et garde la
  première proposition prête, ce qui consomme plus de tokens. Ce choix ne
  change pas le modèle des agents qu'il prépare. Si les instructions par défaut changent après votre
  personnalisation, un avertissement l'indique et permet de les consulter.
  Toute personne pouvant modifier les agents d'une équipe peut lire ces
  instructions et le modèle choisi : n'y mettez jamais d'information
  confidentielle.
- **Interface utilisateur** — le thème proposé par défaut et les thèmes
  disponibles pour les utilisateurs.
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

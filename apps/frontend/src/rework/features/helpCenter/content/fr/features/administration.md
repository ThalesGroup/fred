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
- **Annonces** — les bandeaux et les patch notes affichés aux utilisateurs.
- **Marketplaces** — qui peut publier des agents dans la marketplace, et
  combien.
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
profil n'affiche plus que le mode. Les changements s'appliquent aussitôt pour
l'administrateur, et pour les autres utilisateurs à leur retour sur
l'application ou dans la minute.

Pour ajouter un thème aux couleurs de votre organisation, voir
[Créer un thème personnalisé](/help/fr/guides/custom-theme).

## Marketplaces

Sur la page **Marketplaces**, un **Admin plateforme** décide dans quelles
équipes les éditeurs peuvent publier des agents dans la marketplace (voir
[Les agents](/help/fr/features/agents#la-marketplace-des-agents)) :

- une ligne **Activation de la publication** : **Désactivé** ou **Activé**,
  et combien d'agents une équipe peut publier (5 sauf changement). Toutes les
  équipes la suivent, y compris celles créées plus tard ;
- pour chaque équipe, **Désactivée**, **Défaut** ou **Activée**. Son
  **Nombre d'agents max** suit la valeur par défaut ; **Personnaliser** lui en
  donne un propre, avec un retour possible au défaut.

Désactiver la publication pour une équipe retire ses agents publiés de la
marketplace ; la confirmation annonce d'abord combien. Baisser le nombre
d'agents max garde les agents déjà publiés mais bloque les nouvelles
publications.

## Qui ouvre les fonctions à votre équipe

L'ouverture d'une fonction relève d'un **Admin plateforme** ou d'un
**Gestionnaire de fonctionnalités**, jamais d'un administrateur d'équipe. C'est
pourquoi une fonction peut apparaître comme non autorisée dans la configuration
d'un agent : personne dans votre équipe ne peut l'ouvrir, la demande doit être
adressée à la plateforme.

Lorsqu'une fonction déjà utilisée par un agent est refermée, cet agent est
**suspendu** jusqu'à son rétablissement.

## La page Analytiques

La page **Analytiques** montre l'usage de la plateforme sur la période choisie
(7 ou 30 jours, 3 ou 12 mois glissants, un mois, vos propres dates ; les flèches
passent à la période précédente ou suivante). Chaque chiffre se compare à la
période précédente de même durée.

Ses onglets : **Vue d'ensemble**, **Adoption** (qui a accès, qui vient, qui
envoie des messages, et si les nouveaux reviennent), **Usage**, **Équipes**,
**Agents et outils**, **Qualité et coût** (réponses en échec, tokens, coût
estimé en euros et empreinte) et **Technique** (stockage, recherche web,
longueur des instructions). Chaque indicateur a une courte explication
derrière son icône d'information.

**Périmètre** limite la page à quelques équipes, ou revient à **Toute la
plateforme**. Certains chiffres ne sont pas rattachés à une équipe et
l'indiquent quand des équipes sont sélectionnées.

**Filtre utilisateurs** limite tous les chiffres aux personnes dont les
attributs de compte correspondent à des conditions, construites comme une
règle d'accès à la plateforme (par exemple « organisation est égal à … »).
Seuls les attributs que la règle d'accès enregistre sont proposés, avec leur
dernière valeur connue. Avant d'appliquer, le filtre affiche combien de
personnes correspondent et combien sont « sans donnée » : celles qui ne se
sont pas connectées depuis que la règle utilise cet attribut. Quelques
chiffres de configuration (agents existants, membres des équipes, stockage)
ne sont pas filtrés ; l'icône d'information du filtre les liste.

Le bouton **Jours comptés** (roue crantée) choisit si les week-ends et les jours
fériés français comptent. Par défaut, ils sont exclus de tous les chiffres et de
l'export ; ce choix est gardé pour vous.

**Exporter** télécharge la période et le périmètre affichés dans un
classeur, avec les mêmes chiffres et explications. Il ne contient ni noms, ni
adresses e-mail, ni messages.

## Les analytiques d'une équipe

La page **Analytiques** d'une équipe (dans ses réglages) montre à un
**Admin** de l'équipe les mêmes analytiques que la page **Analytiques**,
limitées à son équipe : les mêmes onglets sauf **Technique**, les mêmes
périodes et comparaisons, les coûts en euros. Il n'y a pas de choix de
périmètre : la page montre toujours l'équipe sélectionnée. Les chiffres qui
n'ont de sens qu'entre équipes (équipes actives, part des conversations en
équipe, tableau des équipes) n'y figurent pas ; l'onglet **Équipes** montre
les membres de l'équipe, combien sont actifs et leur part.

**Exporter** télécharge le classeur de l'équipe seule. Il ne dit rien
des autres équipes de la plateforme.

Le dernier onglet, **Ma consommation**, montre votre propre consommation de
tokens, par agent et par modèle, avec son empreinte et son coût estimé. Les
Éditeurs, Analystes et Membres de l'équipe ne voient que cette partie
personnelle, sous le nom **Ma consommation** dans les réglages de l'équipe, et
dans votre espace personnel elle s'accompagne de vos skills.

## Deux pages d'usage, à ne pas confondre

- **L'usage de votre équipe** — la page **Analytiques** de l'équipe, réservée
  aux **Admins** de l'équipe pour sa partie équipe.
- **L'usage de la plateforme** — la page **Analytiques** de la console, à
  l'échelle de tous les utilisateurs ou des équipes choisies. Elle demande le
  rôle **Observateur plateforme**.

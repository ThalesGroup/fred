---
title: Les agents
order: 10
description: Créer un agent depuis un modèle, l'instruire, lui donner des fonctions.
icon: smart_toy
---

# Les agents

Un **agent** est un assistant IA configuré pour un usage précis. La page
**Agents** de votre équipe les rassemble.

> Créer ou modifier un agent demande le rôle **Éditeur**. Le rôle **Admin**
> seul ne le permet pas : les deux rôles sont indépendants, pas les échelons
> d'une même échelle (voir
> [Équipes et droits](/help/fr/features/teams-and-permissions)).

## D'un modèle à votre agent

Vous partez d'un **modèle** fourni par la plateforme — par exemple un modèle
capable de chercher dans des documents. Vous obtenez votre propre agent, qui
appartient à votre équipe et que vous réglez librement. C'est toujours à un
agent de votre équipe que vous parlez.

## Les quatre réglages

- **Les instructions** — les consignes de fond : son rôle, son ton, ses limites.
  C'est le réglage déterminant ; les autres le complètent.
- **Les prompts attachés** — des prompts de la bibliothèque qui complètent ces
  instructions (voir [Les prompts](/help/fr/features/prompts)).
- **Les ressources** — les bibliothèques de documents que l'agent peut
  consulter. Sans rattachement, il ne voit aucun document.
- **Les fonctions** — ce qu'il sait faire au-delà de répondre.

## Se faire aider par l'assistant de création

Écrire de bonnes instructions (le « prompt système ») demande de l'habitude.
Une fois le modèle d'agent choisi, le bouton **Assistant**, en haut
du formulaire de l'agent, vous aide à démarrer, pour un nouvel agent comme pour
un agent existant :

1. Décrivez avec vos mots ce que l'agent doit faire : son rôle, sa mission, à
   qui il s'adresse, son ton, ce qu'il ne doit pas faire. Quelques phrases
   suffisent.
2. Cliquez sur **Proposer**. Après quelques secondes, l'assistant propose un
   nom, un rôle, une courte description, des instructions et les capacités qui
   semblent utiles à cet agent. Quand l'agent peut le proposer, le
   **Raisonnement** figure toujours en tête des capacités.
3. Relisez les propositions. Tout est coché : décochez ce que vous ne voulez
   pas. Si rien ne convient, modifiez votre description et redemandez.
4. Cliquez sur **Appliquer** : seuls les éléments cochés sont remplis. Les
   capacités cochées remplacent la sélection actuelle. Le **Raisonnement**
   coché est proposé dans le chat et activé au début de chaque conversation.

Si un élément coché doit remplacer quelque chose que vous aviez déjà écrit,
l'assistant vous demande d'abord de confirmer. Rien n'est enregistré tant que
vous n'enregistrez pas l'agent : vous pouvez encore tout modifier.

## Ce qu'un agent sait faire en plus de répondre

L'onglet **Capacités** décide de ce que l'agent a le droit de faire : chercher
dans les documents de l'équipe, exploiter une pièce jointe, rédiger un document
Word, remplir une présentation PowerPoint, produire une page web, prendre le
temps de raisonner par étapes…

Deux façons de choisir, via l'interrupteur **Avancé** en haut de l'onglet :

- **Simple** (par défaut, et recommandé) — vous activez des **packs** : des
  ensembles qui vont naturellement ensemble. Un clic sur la carte active tout
  ce qu'il faut.
- **Avancé** — vous activez chaque fonction une par une, avec ses options.

Le mode Simple couvre les usages courants. Le mode Avancé reste accessible à
tout moment.

> Dépliez un pack (**Capacités incluses**) pour voir son détail. Ce que fait
> chaque capacité, ses limites et un exemple d'emploi figurent sur la page
> [Les capacités](/help/fr/features/capabilities). **La liste affichée par
> l'interface fait foi** : elle évolue avec la plateforme, et chaque
> déploiement n'ouvre pas les mêmes capacités.

### N'activez que ce dont l'agent a besoin

Activer tous les packs « au cas où » est un réflexe courant, et c'est le
réglage qui produit les agents les moins fiables.

**L'agent choisit seul parmi ce que vous lui donnez.** À chaque message, il
décide quelle fonction employer. Plus la liste est longue, plus il risque de
prendre la mauvaise route, et plus la réponse est lente. Un agent qui dispose
des trois fonctions utiles à sa mission est plus prévisible qu'un agent qui en
a douze.

**Certaines fonctions coûtent cher.** L'extraction exhaustive, par exemple, lit
le document entier : elle est lente et demande une confirmation avant chaque
usage. Sur un agent qui n'en a pas besoin, elle ne sert qu'à être déclenchée
par erreur.

**Les fonctions modifient l'interface de conversation.** Le pack **Pièces
jointes** ajoute un trombone, la production de documents ouvre un panneau
latéral, **Documents de l'équipe** peut afficher un sélecteur de bibliothèque. Un agent
sur-équipé présente à ses utilisateurs des commandes qui ne servent pas à son
usage.

S'y ajoute une question de robustesse : un agent est **suspendu** dès qu'une
des fonctions dont il dépend est retirée à l'équipe. Moins il en dépend, moins
il y est exposé.

La méthode qui fonctionne part de l'usage : formulez en une phrase ce que
l'agent doit savoir faire, activez le strict nécessaire, puis complétez si un
manque apparaît à l'usage. Il est toujours plus simple d'ajouter une capacité
que de diagnostiquer un agent qui en a trop.

### Les trois états d'une fonction

À côté du nom de chaque pack, une rangée de pastilles donne l'état d'ensemble :

- **Activée** (pastille pleine) — active sur cet agent.
- **Disponible, non activée** (cercle vide) — votre équipe y a droit, mais elle
  n'est pas active ici. Vous pouvez l'activer.
- **Non autorisée** (pastille rouge) — la plateforme ne l'a pas ouverte à votre
  équipe. Le pack fonctionne quand même avec le reste ; demandez son ouverture
  si vous en avez besoin (voir
  [Administration](/help/fr/features/administration)).

## Dupliquer, copier, suspendre, supprimer

- **Dupliquer** — repartir d'un agent existant pour en faire une variante dans
  la même équipe. Tout est repris, y compris ses fichiers comme un modèle
  PowerPoint.
- **Copier dans…** — donner une copie de l'agent à une autre équipe ou à votre
  espace personnel. Voir ci-dessous.
- **Suspendu** — un agent suspendu reste visible mais inutilisable. C'est
  qu'une fonction dont il dépend a été désactivée, que l'accès de l'équipe y a
  été retiré, ou que sa configuration n'est plus valide. Voir
  [Problèmes courants](/help/fr/troubleshooting/common-problems).
- **Supprimer** — la suppression est définitive.

## Copier un agent dans une autre équipe

Le menu **⋮** de la carte d'un agent propose **Copier dans…**. Vous choisissez
un ou plusieurs espaces : votre espace personnel et les équipes où vous êtes
**Éditeur**. Il faut aussi être Éditeur de l'équipe de l'agent.

Chaque équipe reçoit son propre agent, indépendant de l'original : les
modifications de l'un ne touchent pas l'autre. Tous les éditeurs de l'équipe
peuvent l'utiliser et le régler aussitôt. Si le nom est déjà pris, la copie
est numérotée, par exemple `Analyste (copie 1)`.

**Ce qui est repris** : le nom, la description, les instructions et les
réglages de l'agent.

**Ce qui est remis à zéro** : les choix propres à l'équipe d'origine — une
bibliothèque, un dossier ou des documents choisis. La capacité reste activée,
mais elle porte désormais sur les ressources de la nouvelle équipe. Un agent
qui lisait le wiki de son équipe lira celui de l'équipe qui reçoit la copie.

**Ce qui est recréé** : les fichiers de configuration, comme un modèle
PowerPoint, sont déposés à nouveau dans la nouvelle équipe, comme si un
éditeur l'avait fait lui-même. Si le modèle va chercher ses images dans des
dossiers que la nouvelle équipe n'a pas, ces champs image restent vides : un
message vous indique les dossiers à créer, puis le modèle à redéposer.

**Ce qui n'est jamais copié** : les conversations et les fichiers produits par
l'agent.

Avant de valider, la fenêtre signale les équipes qui ne pourront pas tout
recevoir :

- **Template d'agent non activé** — l'équipe n'a pas accès au modèle de cet
  agent. Elle ne peut pas être choisie.
- **Capacités manquantes** — l'équipe n'a pas toutes les capacités de l'agent
  (survolez le message pour la liste). Vous pouvez copier quand même : l'agent
  y fonctionnera sans elles, avec ses instructions intactes. Pour les obtenir,
  demandez leur ouverture (voir
  [Administration](/help/fr/features/administration)).

## La marketplace des agents

La **marketplace** (**Marketplace → Agents** dans la barre latérale) réunit
les agents que des équipes ont choisi de partager avec toute l'organisation.
Chacun peut la parcourir, y chercher, ouvrir la fiche d'un agent, l'aimer et
en importer une copie. La recherche porte aussi sur le nom des équipes. Pour
ne voir que les agents d'une équipe, cliquez sur son nom en haut d'une carte ;
retirez le filtre avec la croix de l'étiquette **Équipe** sous la recherche.

### Qui peut publier

Tout **Éditeur** de l'équipe peut publier, une fois la publication activée pour
elle par l'administrateur de la plateforme (voir
[Équipes et droits](/help/fr/features/teams-and-permissions)). Un
Éditeur trouve **Publier sur la marketplace** dans le menu **⋮** de la carte
d'un agent. L'action est grisée, avec la raison, quand :

- l'équipe est **privée** — seules les équipes publiques publient ;
- l'équipe a atteint le **nombre d'agents publiés** que l'administrateur de la
  plateforme lui accorde ;
- l'agent repose sur un type d'agent réservé aux administrateurs de la
  plateforme.

Les agents de votre espace personnel ne sont jamais publiés.

### Ce que la publication partage

Publier partage un **instantané** de l'agent : son nom, sa description, ses
instructions et ses réglages, ainsi qu'une copie de ses fichiers de
configuration, comme un modèle PowerPoint. Toute l'organisation peut lire
cette configuration : relisez-la avant de valider. Une fenêtre vous le
rappelle et vous demande de cocher **J'ai compris**.

Les choix propres à votre équipe ne sont **pas** partagés : les bibliothèques,
dossiers et documents choisis pour l'agent restent en dehors de l'instantané.

### Publié, puis Modifié

Une fois publié, la carte affiche **Publié** en bas, avec ses j'aime et ses
imports. Votre équipe continue d'utiliser et de modifier l'agent comme
d'habitude. Après une modification, les éditeurs et l'admin de l'équipe voient
**Modifié, non republié** : la marketplace montre encore la version
précédente. Un Éditeur qui enregistre une modification se voit
proposer de le republier aussitôt ; **Ignorer** laisse la version précédente
en ligne.

### Retrait de la marketplace

Un Éditeur ou l'admin de l'équipe peut retirer un agent avec **Retirer de la
marketplace** dans le menu **⋮**. Il reste dans l'équipe, inchangé.

L'agent est aussi retiré **automatiquement** quand :

- il est désactivé, suspendu ou supprimé ;
- l'équipe devient privée ;
- l'administrateur de la plateforme désactive la publication pour l'équipe ;
- un administrateur de la plateforme le retire, éventuellement avec un
  message.

Après un retrait automatique, la carte affiche **Retiré de la marketplace**.
Cliquez dessus pour voir pourquoi, quand, et le message de l'administrateur
s'il y en a un. Les éditeurs et l'admin de l'équipe peuvent **Masquer** cette
mention pour toute l'équipe. Publier l'agent à nouveau le remet dans la
marketplace.

### Les j'aime

Cliquez sur le cœur d'une carte de la marketplace pour aimer un agent, même
un agent de votre équipe ; cliquez à nouveau pour retirer votre j'aime. La
carte affiche le total. La fiche de l'agent indique aussi combien de j'aime il
a reçus **depuis sa dernière mise à jour** : vous savez ainsi si la version
actuelle est celle qui a plu. Les j'aime et les imports sont conservés quand
un agent est retiré puis publié à nouveau.

### Importer une copie

**Importer** (sur la carte ou dans la fiche de l'agent) copie l'agent dans
votre espace personnel ou dans les équipes où vous êtes **Éditeur**. L'équipe
qui l'a publié n'est pas proposée. Avant de valider, chaque équipe indique ce
que l'agent y perdrait, par exemple une capacité dont elle ne dispose pas ;
une équipe sans accès au type d'agent ne peut pas être choisie.

**Votre copie est indépendante** : les mises à jour faites ensuite par
l'équipe qui publie ne lui parviennent pas, et vos modifications ne leur
parviennent pas non plus. Si le nom est déjà pris, la copie est numérotée,
par exemple `Analyste (copie 1)`.

Une fois l'import fait, la fenêtre liste, pour chaque équipe, ce qu'il faut y
régler à nouveau : les bibliothèques, documents et dossiers que l'agent doit
utiliser, et ce qu'une capacité vous demande de refaire.

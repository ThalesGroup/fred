---
name: graph
description: Créer ou corriger des diagrammes, graphiques et comparaisons visuelles à partir de faits sources ou de données vérifiées, en choisissant une représentation et un rendu pris en charge par les outils disponibles.
license: Apache-2.0
metadata:
  fred-argument-hint: "[objectif, source ou données] [contraintes]"
  author: Fred contributors
  provenance: Original Fred procedure, French edition.
---

# Visualisation

Identifiez la question à laquelle le visuel doit répondre, ainsi que les faits
fournis ou les résultats réels d'outils qui l'étayent. Demandez les relations,
dates ou valeurs essentielles qui manquent ; présentez explicitement un plan
hypothétique comme tel. Préservez le sens voulu lorsque vous corrigez un visuel.
Préférez une courte liste ou un tableau lorsqu'ils répondent plus clairement.

## Choisir une représentation

| Ce dont le lecteur a besoin | Représentation utile |
| --- | --- |
| Étapes, décisions ou dépendances | Logigramme (flowchart) |
| Interactions ordonnées, états ou relations structurelles | Diagramme de séquence, d'états, de classes ou entité-association |
| Hiérarchie, jalons ou planning | Carte mentale, frise chronologique ou diagramme de Gantt |
| Historique Git ou scores d'expérience utilisateur fournis | Graphe Git ou parcours utilisateur |
| Comparaisons ou classements de catégories | Barres horizontales triées ou tableau compact |
| Évolution dans le temps | Courbe chronologique, périodes manquantes visibles |
| Distribution numérique | Histogramme aux classes indiquées ou quantiles vérifiés |
| Deux variables numériques | Nuage de points ; une association n'établit pas une cause |
| Parts d'un même total vérifié | Tableau ou barres empilées ; un camembert pour quelques parts positives |
| Valeurs exactes ou quelques observations | Tableau légendé |

## Utiliser un rendu disponible

- Pour un rendu Mermaid, lisez d'abord la [référence de syntaxe et de livraison Mermaid](references/mermaid.md).
  Elle couvre les familles de diagrammes ci-dessus et la syntaxe prise en charge
  par le chat. Renvoyez dans le chat un bloc Mermaid complet et délimité, en
  suivant cette référence.
- Avec un outil de tracé, de présentation ou de rendu HTML, utilisez ses formats
  documentés et son résultat réel. Un outil limité à HTML/CSS peut produire des
  barres statiques légendées avec leurs valeurs. N'utilisez scripts,
  bibliothèques ou syntaxe de diagramme que si cet outil les prend explicitement
  en charge. Inspectez le livrable quand une relecture est possible.
- Sans moteur de rendu adapté, fournissez un tableau Markdown ou un plan textuel
  utile et expliquez la limite. Demandez les données manquantes au lieu d'inventer
  des mesures ; n'annoncez un fichier généré que si un outil disponible l'a produit.

La référence Mermaid ne sert qu'au rendu Mermaid. Les autres formats suivent le
contrat de leur outil ; installer des dépendances sort du cadre de cette procédure.

## Garder un résultat fidèle et lisible

Les barres partent de zéro, y compris pour des valeurs négatives. Signalez les
axes tronqués des courbes et nuages de points ; utilisez des échelles identiques
pour des panneaux comparables, des trous visibles et un dénominateur explicite
pour les parts. Évitez les doubles axes et les effets 3D.
Ne montrez estimations ou incertitude que si des données ou un calcul les étayent.

Utilisez un titre descriptif, des libellés et une courte explication dans la
langue de l'utilisateur. Indiquez unités, période, source et exclusions
importantes. Assurez un contraste suffisant et distinguez les séries par des
libellés ou des formes, pas seulement par la couleur. Fournissez les valeurs clés
ou un tableau accessible pour que le résultat se comprenne sans le voir. Vérifiez
valeurs, totaux, ordre et relations par rapport à la source avant de présenter.

---
title: Évaluer un agent
order: 20
description: Mesurer la qualité d'un agent, plutôt que s'en faire une impression.
icon: reviews
---

# Évaluer un agent

Comment savoir si un agent répond bien — et s'il s'améliore quand vous ajustez
sa configuration ? En le mesurant, plutôt qu'en s'en remettant à une impression
formée sur quelques questions.

> L’evaluator autonome doit être déployé, enregistré dans Fred et activé pour
> votre équipe. S’il manque dans **Apps**, contactez votre administrateur.

## 1. Créer l'évaluation

Sélectionnez votre équipe, ouvrez **Apps**, puis l’application evaluator
enregistrée. Créez-y une **évaluation** : un nom et ses cas. C’est une définition
réutilisable et versionnée — la créer ne lance aucune exécution. Les évaluations
ne se trouvent plus dans les réglages de l’équipe.

Un bon jeu de cas ressemble à ce que vos collègues demanderont vraiment, y
compris les questions auxquelles l'agent **ne devrait pas** savoir répondre :
c'est ainsi que l'on repère les réponses inventées.

## 2. La lancer

Déclenchez une **exécution** sur l'agent visé. Elle parcourt chaque cas et
mesure les réponses.

## 3. Lire et ajuster

Chaque cas ressort réussi, échoué ou ignoré. Parcourez les échecs pour
comprendre _pourquoi_ : instructions trop vagues, corpus incomplet, question
ambiguë. Ajustez un seul paramètre à la fois, relancez, comparez.

C'est ce cycle **mesurer → ajuster → remesurer** qui fait progresser un agent —
et c'est particulièrement utile avant de le partager largement, ou après une
modification importante.

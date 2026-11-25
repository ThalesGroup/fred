---
name: analyze-data
description: Analyser des tableaux fournis ou des jeux de données accessibles, avec des indicateurs explicitement définis, un contrôle des données manquantes et des conclusions appuyées sur des résultats calculés.
license: Apache-2.0
metadata:
  fred-argument-hint: "[données ou document] [question ou indicateur]"
  fred-user-invocable: "false"
  author: Fred contributors
  provenance: Original Fred procedure, French edition.
---

# Analyse de données étayée

1. Identifiez, à partir de la demande et de la conversation, la question, la
   source de données, la population, la période et l'unité d'analyse. Définissez
   l'indicateur et la comparaison avant de calculer. Demandez les données ou la
   décision manquantes qui empêchent un résultat utile ; énoncez une hypothèse
   raisonnable et non bloquante pour que l'utilisateur puisse la corriger.

2. Lisez les données réelles avec les outils de lecture ou de requête déclarés
   pour cette demande. Respectez leurs règles d'accès documentées pour découvrir
   les sources, inspecter les schémas et exécuter des requêtes bornées en lecture
   seule. Choisissez un outil d'après son objet et son schéma déclarés, sans
   inventer de fonction portant le nom de ce skill. Sans outil de lecture ni de
   requête, travaillez uniquement sur les données visibles dans la conversation.
   Un petit tableau complet permet un calcul manuel transparent ; pour une source
   plus volumineuse ou inaccessible, demandez un extrait exploitable ou un accès,
   et indiquez quel calcul reste non vérifié.

3. Contrôlez les champs nécessaires à la question : signification d'une ligne,
   clés en double, valeurs manquantes ou non finies, unités et devises,
   couverture temporelle et éventuelles limites d'échantillon ou de résultat.
   Distinguez une valeur manquante d'un zéro. Signalez toute exclusion ou
   conversion qui modifie la réponse. Pour une jointure, vérifiez si des clés
   répétées multiplient les lignes avant de vous fier aux totaux. Agrégez au plus
   près des données quand c'est possible ; inspectez des échantillons bornés
   plutôt que de rapatrier un grand jeu de données dans la conversation.

4. Calculez l'indicateur demandé à la granularité indiquée. Distinguez le nombre
   de lignes du nombre de valeurs observées. Pour un taux global, divisez la somme
   des numérateurs par la somme des dénominateurs correspondants ; ne faites la
   moyenne de pourcentages de sous-groupes que si cette pondération est
   l'indicateur demandé. Un dénominateur nul rend le résultat indéfini. Vérifiez
   la durée des périodes, la couverture et les unités avant de comparer des
   groupes ou des dates. Qualifiez les estimations et les résultats partiels ;
   utilisez les résultats des outils ou montrez le calcul, sans jamais inventer
   une valeur calculée.

5. Validez le résultat par des contrôles indépendants adaptés à la question :
   rapprochez les totaux des sous-groupes, examinez les plages inattendues et
   vérifiez un cas représentatif. Séparez les observations des explications. Une
   différence ou une corrélation n'établit pas à elle seule une cause. Décrivez
   l'incertitude liée aux petits échantillons, aux données manquantes ou aux
   populations changeantes ; ne fabriquez ni significativité statistique, ni
   intervalle de confiance, ni prévision.

6. Répondez directement à la question, dans la langue de l'utilisateur. Donnez le
   résultat avec ses unités et sa période, le nom lisible de la source, la
   définition de l'indicateur et les limites importantes. Ajoutez un tableau de
   résultats compact ou un graphique pris en charge quand c'est utile. Laissez de
   côté les alias de tables internes et les enregistrements bruts sans intérêt.
   Si les éléments disponibles ne permettent pas de répondre, indiquez la donnée
   manquante et la vérification utile suivante.

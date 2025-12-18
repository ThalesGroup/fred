# Jeu de documents métier fictifs (défense / industrie)

Ce corpus est **volontairement réduit mais crédible**, conçu pour démontrer la valeur d’un **agent GraphRAG** (Neo4j + Graphiti) dans Fred.

---

## Document 1 – Spécification Système (SYS-SPEC-RADAR.md)

### 1. Objet
Le système **RADAR-X** est un sous-système de surveillance destiné à la détection et au suivi de cibles aériennes à moyenne portée.

### 2. Exigences système

#### SYS-REQ-01 – Détection de cibles
Le système RADAR-X doit détecter des cibles aériennes jusqu’à une distance minimale de **120 km**.

#### SYS-REQ-02 – Suivi de cibles
Le système doit assurer le suivi simultané d’au moins **50 cibles**.

#### SYS-REQ-03 – Continuité de service
Le système doit garantir une disponibilité opérationnelle de **99,5 %**.

#### SYS-REQ-04 – Sécurité fonctionnelle
Le système doit éviter toute perte de détection non signalée pouvant conduire à une situation dangereuse.

---

## Document 2 – Spécification Fonctionnelle (FUNC-SPEC-RADAR.md)

### 1. Fonctions principales

#### FUNC-01 – Acquisition du signal radar
Responsable de la réception et du pré-traitement du signal brut.

#### FUNC-02 – Traitement du signal
Analyse du signal afin d’extraire les cibles potentielles.

#### FUNC-03 – Suivi de cibles
Maintien de la trajectoire et de l’identification des cibles détectées.

### 2. Allocation des exigences
- SYS-REQ-01 → FUNC-01, FUNC-02
- SYS-REQ-02 → FUNC-03
- SYS-REQ-04 → FUNC-02, FUNC-03

---

## Document 3 – Spécification Logicielle (SW-SPEC-RADAR.md)

### 1. Composants logiciels

#### SW-COMP-01 – RadarSignalProcessor
Implémente les algorithmes de traitement du signal radar.

#### SW-COMP-02 – TargetTrackingEngine
Implémente les algorithmes de suivi de cibles.

### 2. Allocation fonctions → composants
- FUNC-02 → SW-COMP-01
- FUNC-03 → SW-COMP-02

---

## Document 4 – Analyse de Sécurité (SAFETY-ANALYSIS.md)

### 1. Identification des dangers

#### HAZ-01 – Perte de détection de cible
La perte non détectée d’une cible peut conduire à une situation opérationnelle dangereuse.

### 2. Causes identifiées
- Défaillance de l’algorithme de traitement du signal
- Saturation du moteur de suivi de cibles

### 3. Mesures de mitigation

#### SAF-REQ-01
Le système doit détecter et signaler toute dégradation du traitement du signal radar.

#### SAF-REQ-02
Le système doit déclencher une alerte en cas de saturation du suivi de cibles.

### 4. Allocation
- HAZ-01 → SAF-REQ-01, SAF-REQ-02
- SAF-REQ-01 → SW-COMP-01
- SAF-REQ-02 → SW-COMP-02

---

## Document 5 – Plan de Tests IVVQ (TEST-PLAN-RADAR.md)

### 1. Cas de tests

#### TC-01 – Validation de la portée de détection
Vérifie que la portée minimale de 120 km est atteinte.

- Couvre : SYS-REQ-01
- Composant : SW-COMP-01

#### TC-02 – Test de perte de signal
Simule une dégradation du traitement du signal.

- Couvre : SAF-REQ-01
- Composant : SW-COMP-01

#### TC-03 – Test de saturation du suivi
Simule une charge maximale de cibles.

- Couvre : SAF-REQ-02
- Composant : SW-COMP-02

---

## Lecture GraphRAG attendue (exemple)

Exemples de relations exploitables dans Neo4j :

- SYS-REQ-04 → SAF-REQ-01
- SAF-REQ-01 → SW-COMP-01
- SW-COMP-01 → TC-02

👉 Permet à l’agent de répondre à :
> « Quels risques et quels tests sont impactés si je modifie l’algorithme RadarSignalProcessor ? »

---

## Remarque
Ce corpus est volontairement simple mais **structurellement réaliste**. Il peut être enrichi progressivement (versions, anomalies, REX) sans changer le modèle graphe.



---

# Extension du corpus – Version réaliste pour démo GraphRAG

Cette section enrichit le corpus initial afin d’atteindre une **densité réaliste** (≈30–40 chunks, graphe non trivial) sans tomber dans l’artificiel.

---

## Document 6 – Exigences système étendues (SYS-SPEC-RADAR-V2.md)

### SYS-REQ-05 – Latence de détection
Le système doit détecter et qualifier une cible en moins de **2 secondes** après acquisition du signal.

### SYS-REQ-06 – Dégradation contrôlée
En cas de défaillance partielle, le système doit maintenir une capacité minimale de détection dégradée.

### SYS-REQ-07 – Journalisation
Le système doit journaliser toute anomalie critique liée à la détection ou au suivi.

### SYS-REQ-08 – Redondance logicielle
Les fonctions critiques doivent disposer d’un mécanisme de redondance logicielle.

---

## Document 7 – Analyse de risques étendue (SAFETY-ANALYSIS-V2.md)

### HAZ-02 – Retard de détection
Un retard excessif dans la détection peut empêcher la réaction opérationnelle.

- Cause principale : surcharge du traitement du signal
- Gravité : Élevée

### HAZ-03 – Données de suivi incohérentes
Des trajectoires incohérentes peuvent induire une mauvaise décision opérateur.

- Cause principale : divergence algorithmique du moteur de suivi
- Gravité : Moyenne

### SAF-REQ-03
Le système doit détecter toute latence anormale du traitement du signal.

### SAF-REQ-04
Le système doit invalider toute trajectoire incohérente détectée.

Allocations :
- HAZ-02 → SAF-REQ-03 → SW-COMP-01
- HAZ-03 → SAF-REQ-04 → SW-COMP-02

---

## Document 8 – Gestion des anomalies (ANOMALIES-RADAR.md)

### ANOM-01 – Saturation en environnement dense
- Composant : SW-COMP-02
- Impact : Perte partielle de suivi
- Lié à : HAZ-03
- Correctif proposé : limitation dynamique du nombre de cibles suivies

### ANOM-02 – Faux négatifs intermittents
- Composant : SW-COMP-01
- Impact : Perte de détection temporaire
- Lié à : HAZ-01, HAZ-02
- Correctif proposé : recalibrage adaptatif

---

## Document 9 – Change Request (CR-012.md)

### Objet
Optimisation de l’algorithme **RadarSignalProcessor** afin de réduire la latence.

### Motivation
- Non-conformité partielle à SYS-REQ-05
- Lien avec ANOM-02

### Impacts identifiés
- SW-COMP-01
- SAF-REQ-01
- SAF-REQ-03
- TC-02

---

## Document 10 – Plan de tests étendu (TEST-PLAN-RADAR-V2.md)

### TC-04 – Test de latence maximale
- Vérifie SYS-REQ-05
- Composant : SW-COMP-01

### TC-05 – Test de redondance logicielle
- Vérifie SYS-REQ-08
- Composant : SW-COMP-01, SW-COMP-02

### TC-06 – Test de cohérence des trajectoires
- Vérifie SAF-REQ-04
- Composant : SW-COMP-02

---

## Résultat attendu pour la démo

### Volumétrie estimée
- Documents : 10
- Exigences (SYS + SAF) : ~20
- Fonctions : 3
- Composants : 2
- Hazards : 3
- Tests : 6
- Anomalies / CR : 3

➡️ **≈30–45 chunks** selon la stratégie de découpe
➡️ **Graphe dense**, exploitable pour :
- analyse d’impact
- justification sécurité
- traçabilité certification

### Question de démo idéale
> « Quels risques, exigences sécurité et tests sont impactés par la CR-012 sur RadarSignalProcessor, et pourquoi ? »

Ce corpus est désormais suffisamment riche pour démontrer **une supériorité nette d’un agent GraphRAG** par rapport à un RAG vectoriel classique.
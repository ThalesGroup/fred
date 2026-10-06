# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Business requests the evaluation sends, varied in shape and language."""

PROMPTS: dict[str, str] = {
    "cyber_2027": (
        "Prépare une présentation de 8 slides sur la stratégie cybersécurité 2027 du groupe : "
        "contexte de la menace, nos quatre priorités, la feuille de route par semestre, le budget "
        "et les indicateurs de succès."
    ),
    "quarterly_review": (
        "Build a Q3 2026 business review for the executive committee: revenue 412 M€ (+6%), "
        "EBIT margin 11.4%, order intake 530 M€, backlog 2.1 B€, headcount 3 850. Cover highlights, "
        "the KPIs, what went wrong, and the Q4 outlook. About 7 slides."
    ),
    "kickoff": (
        "Fais-moi le deck de lancement du projet ATLAS (migration du SI achats vers le cloud) : "
        "objectifs, périmètre, planning en 5 jalons de janvier à octobre 2027, l'équipe (sponsor "
        "Claire Martin, chef de projet Hugo Lefèvre, architecte Nadia Benali, PO Marc Duval), "
        "gouvernance et prochaines étapes."
    ),
    "options_comparison": (
        "Create a short deck comparing two options for our new CRM: Option A buy Salesforce, "
        "Option B extend our in-house tool. Compare cost, time to deploy, risks and fit, then "
        "give a recommendation."
    ),
    "committee_agenda": (
        "Prépare le support du comité de direction du 14 novembre : un ordre du jour en 6 points "
        "(résultats du mois, point RH, sécurité des sites, projet ATLAS, investissements 2027, "
        "questions diverses), puis une slide par point et une conclusion avec les décisions attendues."
    ),
    "pitch_4": (
        "A 4-slide pitch for our new predictive maintenance offer for rail operators: the "
        "problem, our solution, the proof (pilot with 30% fewer breakdowns), and the call to action."
    ),
    "training_12": (
        "Crée un support de formation de 12 slides sur les bonnes pratiques de gestion des mots "
        "de passe et du phishing pour l'ensemble des collaborateurs, avec un quiz final."
    ),
    "many_items": (
        "Make a presentation listing our 9 regional sites with, for each one, its city, its "
        "headcount and its main activity: Toulouse 1200 avionics, Brest 640 naval systems, "
        "Valence 480 navigation, Élancourt 2100 defence, Cholet 520 radio, Vendôme 310 optronics, "
        "Massy 870 software, Sophia 450 space, Bordeaux 390 training. Put all 9 sites on one slide "
        "as cards, then a summary."
    ),
    "process_onboarding": (
        "Présentation de 6 slides sur notre nouveau processus d'onboarding en 7 étapes, de la "
        "signature du contrat à la fin de la période d'essai, avec les acteurs de chaque étape."
    ),
    "esg_report": (
        "Prepare a 9-slide ESG update: our three commitments, CO2 emissions down 18% since 2022, "
        "40% women in management target, supplier audit figures (220 audits, 95% compliant), a "
        "quote from the CEO, and the 2030 timeline."
    ),
    # Two countries with figures, domains, dated initiatives and challenges:
    # the plan that sent `heading2` columns and repeated one slide four times.
    "country_comparison": (
        "Prépare une présentation de 10 slides sur nos implantations en Espagne et en Italie. "
        "Espagne : 45 ans d'implantation, 2 800 experts, 9 sites ; domaines défense, spatial et "
        "cybersécurité ; initiatives : centre cyber à Madrid (2024), contrat radar naval (2025), "
        "usine de Séville (2027) ; défis : recrutement d'ingénieurs et coûts de l'énergie. "
        "Italie : 30 ans d'implantation, 1 900 experts, 6 sites ; domaines spatial, transport et "
        "identité numérique ; initiatives : satellite de Turin (2024), signalisation ferroviaire "
        "(2026) ; défis : souveraineté des données et délais d'export. Une section par pays, puis "
        "une comparaison des deux pays et une conclusion."
    ),
    # Tabular content (design.md D14): offers × criteria, a schedule.
    "offers_table": (
        "Make a 4-slide deck comparing three cloud offers for our data platform: AWS, Azure "
        "and OVHcloud. Put the comparison in a table: monthly price (38 k€, 41 k€, 29 k€), SLA "
        "(99.99%, 99.95%, 99.9%), data location (Frankfurt, Paris, Roubaix), support (24/7, 24/7, "
        "business hours) and SecNumCloud (no, no, yes). Then give our recommendation."
    ),
    "schedule_table": (
        "Prépare la présentation du plan de formation du premier trimestre 2027 : une slide "
        "d'introduction, puis le planning sous forme de tableau avec 8 sessions (date, thème, "
        "formateur, lieu) que tu inventes de façon réaliste, puis une slide sur la logistique."
    ),
}

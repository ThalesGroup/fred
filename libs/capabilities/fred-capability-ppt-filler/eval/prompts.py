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
    # The real session's request (no comparison asked): its first deck held
    # five bullets slides on five different template slides.
    "thales_spain_italy": (
        "Prépare une présentation exposant les activités de Thales en Espagne et en Italie."
    ),
    # Tabular content: offers × criteria, a schedule.
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
    # Chartable data: figures over time, and shares of a whole.
    "sales_charts": (
        "Build a 5-slide sales review with charts: revenue per quarter in 2025 and 2026 "
        "(2025: 12, 15, 14, 18 M€; 2026: 14, 17, 19, 22 M€), and the 2026 split by region "
        "(Europe 45%, Americas 30%, Asia 18%, Africa 7%). End with the outlook."
    ),
    "market_shares": (
        "Prépare 4 slides sur nos parts de marché : un graphique de l'évolution de nos ventes "
        "mensuelles de janvier à juin (120, 135, 128, 150, 162, 171 unités) et un graphique des "
        "parts de marché (nous 34 %, concurrent A 28 %, concurrent B 21 %, autres 17 %)."
    ),
    # Storytelling: the 2026-10-14 repro (mixed measures, crammed subtitle), made-up
    # data allowed, no titles, figures typed by the user.
    "story_group_profile": (
        "Présente le groupe au comité : 45 ans d'histoire, 2 800 salariés, 9 sites, et la "
        "répartition des effectifs (Italie 1 200, France 1 000, Espagne 600). 5 slides."
    ),
    "story_illustrative": (
        "Fais un deck de 4 slides pour présenter notre futur tableau de bord commercial, avec "
        "des données indicatives fictives pour les graphiques."
    ),
    "story_no_titles": (
        "Make a 4-slide deck on our hiring plan, without any slide titles: Italy 80 hires, "
        "France 40, Spain 20, total budget 6.2 M€."
    ),
    "story_user_figures": (
        "On a fait 12,5 % de croissance et 3,2 M€ de chiffre d'affaires cette année, avec 14 "
        "nouveaux clients. Prépare 3 slides de bilan."
    ),
    # One prompt per chart type beyond categories over time and shares.
    "chart_stacked_bar": (
        "Make a 3-slide budget review: the 2026 budget per department split into staff, "
        "tools and travel (in k€): Customer Success 420, 80, 35; Research and Development "
        "910, 260, 40; Sales and Marketing 530, 120, 150; General Administration 300, 60, 10."
    ),
    "chart_radar": (
        "Compare les trois offres d'hébergement sur six critères notés sur 10 (prix, "
        "sécurité, support, performance, réversibilité, conformité) : Offre A 7, 8, 6, 9, 5, 8 ; "
        "Offre B 9, 6, 7, 6, 8, 6 ; Offre C 5, 9, 8, 7, 7, 9. 3 slides."
    ),
    "chart_scatter": (
        "Show how price relates to units sold for our ten products, in 3 slides: Alpha 12 € "
        "1 450 units, Beta 18 € 1 120, Gamma 25 € 980, Delta 9 € 1 800, Epsilon 30 € 640, Zeta "
        "15 € 1 300, Eta 22 € 900, Theta 40 € 420, Iota 35 € 500, Kappa 28 € 760."
    ),
    "chart_bubble": (
        "Prépare 3 slides sur nos marchés : croissance annuelle, part de marché et chiffre "
        "d'affaires : France 4 %, 32 %, 120 M€ ; Allemagne 6 %, 18 %, 85 M€ ; Espagne 9 %, 12 %, "
        "40 M€ ; Italie 3 %, 22 %, 60 M€ ; Pologne 12 %, 8 %, 25 M€."
    ),
    # Related measures side by side: two charts, then a 2 × 2 grid (on a template
    # whose example slides hold several charts).
    "charts_pair": (
        "Prépare 3 slides sur nos régions : côte à côte, le chiffre d'affaires 2026 par région "
        "(Europe 45, Amériques 30, Asie 18 M€) et la marge par région (Europe 11 %, Amériques "
        "12 %, Asie 9 %)."
    ),
    "charts_grid": (
        "Build a 3-slide KPI review showing four indicators over the four quarters of 2026 on "
        "one slide: revenue 12, 15, 17, 21 M€; margin 8, 9, 9, 11 %; customers 120, 135, 150, "
        "170; churn 4, 3.5, 3.2, 3 %."
    ),
    # Emphasis the user implies (intent fields), and key messages shown on request.
    "intent_record_quarter": (
        "Make 3 slides on our 2026 sales by quarter: Q1 12, Q2 15, Q3 24, Q4 17 M€. Q3 is "
        "our record quarter."
    ),
    "intent_total_row": (
        "Prépare 3 slides sur le budget 2026 par poste, en tableau : salaires 4,2 M€, "
        "locaux 1,1 M€, outils 0,6 M€, déplacements 0,3 M€ ; la dernière ligne est le total, "
        "6,2 M€."
    ),
    "intent_trends": (
        "Build 3 slides for the board: revenue 48 M€ (up), costs 31 M€ (down), headcount "
        "320 (stable)."
    ),
    "intent_key_messages": (
        "Fais 3 slides sur nos ventes 2026 (Q1 12, Q2 15, Q3 24, Q4 17 M€) et affiche les "
        "messages clés sur les slides."
    ),
}

# The chart type each chart prompt calls for, measured as "expected type chosen".
EXPECTED_CHART_TYPES: dict[str, str] = {
    "chart_stacked_bar": "stacked_bar",
    "chart_radar": "radar",
    "chart_scatter": "scatter",
    "chart_bubble": "bubble",
}

# A second user turn per prompt, asking to change the delivered deck: an
# insert, a field on the last slide, a removal or a title.
EDITS: dict[str, str] = {
    "cyber_2027": (
        "Ajoute une slide de chiffres clés juste après la couverture, avec trois chiffres sur la menace."
    ),
    "quarterly_review": (
        "Put our contact on the last slide: finance@acme.com, +33 1 23 45 67 89."
    ),
    "kickoff": (
        "Ajoute sur la dernière slide le contact du chef de projet : hugo.lefevre@acme.fr, 06 12 34 56 78."
    ),
    "options_comparison": (
        "Add a slide with the key figures of each option (cost, months to deploy) just before the "
        "recommendation."
    ),
    "committee_agenda": (
        "Le point « questions diverses » est annulé : retire-le de l'ordre du jour et supprime sa slide."
    ),
    "pitch_4": "Add our contact on the last slide: sales@acme.com, +33 1 98 76 54 32.",
    "training_12": (
        "Change le titre de la première slide en « Cybersécurité : les bons réflexes »."
    ),
    "many_items": (
        "Add a key-figures slide right after the cover: total headcount, number of sites, largest site."
    ),
    "process_onboarding": "Ajoute à la fin une slide contact RH : rh@acme.fr, poste 4521.",
    "esg_report": (
        "Add a slide right after the cover with three key figures: -18% CO2, 220 audits, 95% compliant."
    ),
    "country_comparison": (
        "Ajoute une slide de chiffres clés pour chaque pays, juste après la section de ce pays."
    ),
    "thales_spain_italy": "Ajoute une slide de chiffres clés par pays.",
    "offers_table": (
        "Put this contact on the last slide: cloud-team@acme.com, +33 1 11 22 33 44."
    ),
    "schedule_table": (
        "Mets ce contact sur la dernière slide : formation@acme.fr, 01 44 55 66 77."
    ),
    "sales_charts": "Q4 2026 was 23 M€, not 22: fix the chart.",
    "market_shares": "Les ventes de juin sont de 175 unités, pas 171 : corrige le graphique.",
    "story_group_profile": "Ajoute une slide de conclusion avec la décision attendue.",
    "story_illustrative": "Remplace le graphique de la slide 3 par un camembert.",
    "story_no_titles": "Add a closing slide, still without a title.",
    "story_user_figures": "Le chiffre d'affaires est de 3,4 M€, pas 3,2 : corrige-le.",
    "chart_stacked_bar": "Travel for Sales and Marketing is 130 k€, not 150: fix the chart.",
    "chart_radar": "L'offre B a 7 en sécurité, pas 6 : corrige le graphique.",
    "chart_scatter": "Theta sold 450 units, not 420: fix the chart.",
    "chart_bubble": "La Pologne fait 30 M€, pas 25 : corrige le graphique.",
    "charts_pair": "La marge des Amériques est de 14 %, pas 12 : corrige le second graphique.",
    "charts_grid": "Q4 churn was 2.8 %, not 3: fix that chart.",
    "intent_record_quarter": "Sort the quarters from the largest to the smallest.",
    "intent_total_row": "Mets en avant la ligne des salaires dans le tableau.",
    "intent_trends": "Headcount actually went up: fix it.",
    "intent_key_messages": "Raccourcis le message clé de la slide du graphique.",
}

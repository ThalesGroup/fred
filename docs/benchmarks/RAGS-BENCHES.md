# Tests RAG — 2026-04-28

## Corpus
| Lib | Contenu |
|-----|---------|
| CIR | 3 DOCX (dossiers techniques R&D) |
| Process | 8 MD (fiches outils Thales : outils.md, my-thales.md, workday.md, imputation-jtime.md…) |
| CV | 1 PDF |

---

## Semantic vs Hybrid

| | Semantic | Hybrid (BM25 + vectoriel RRF) |
|--|---------|-------------------------------|
| Scores | cosinus 0.0–1.0, resserrés | RRF 0.0–0.5, plus étalés |
| Terme générique ("outils") sans scoping | ✅ Reste dans les libs pertinentes | ⚠️ Bruit inter-lib (CIR 0.5) |
| Terme technique ("deep learning EEG") sans scoping | ❌ CIR à 0.70 ≈ CV — indifférenciable | ✅ CIR écrasé à 0.09 |
| Nom propre ("BidGPT") sans scoping | ✅ Correct, chunks cosinus légèrement meilleurs | ✅ Score 1.0, CIR marginal |
| Avec scoping sur la bonne lib | Manque des docs | ✅ Découvre plus de docs |

**Hybrid est le bon défaut.** Le seul cas défavorable (terme générique sans scoping) est contournable avec scoping.

---

## Résultats des tests

| # | Question | Policy | Scope | Top hits | Verdict |
|---|----------|--------|-------|----------|---------|
| 6 | outils Thales liste globale | hybrid | aucun | CIR 0.50❌, outils 0.50, my-thales 0.31 | 2/5 slots = bruit CIR |
| 7 | outils Thales CIS TSN S3NS | hybrid | Process | mycv 0.50, outils 0.50×3, imputation-jtime 0.25 🆕 | imputation-jtime découvert |
| 8 | outils Thales CIS TSN S3NS | semantic | aucun | outils 0.82×4, my-thales 0.80 | 5/5 pertinents, zéro bruit |
| 9 | BidGPT | hybrid | aucun | CIR×5 même doc 0.50–0.39 | 5/5 ✅ réponse bonne |
| 10 | BidGPT | semantic | aucun | CIR×5 même doc 0.71–0.69 | 5/5 ✅ réponse légèrement plus riche |
| 11 | deep learning EEG | hybrid | aucun | CV 1.0🏆, CV 0.52, CV 0.19, CIR 0.09, CIR 0.08 | BM25 écrase les CIR — réponse excellente |
| 12 | deep learning EEG | semantic | aucun | CV 0.79, CV 0.77, CIR 0.70❌×3 | CIR ≈ CV — réponse appauvrie |

---

## Observations
- **'mycv'** (test 7, tag Process) = fichier `mycv.md` dans Process, pas le CV d'Alexis.
- **Score RRF 1.0** = doc #1 dans BM25 ET vectoriel simultanément — signal très fort.
- **'Research engineer'** = titre du doc CV dans le store.

## Points ouverts
- [ ] **imputation-jtime** (test 7) : valider la pertinence du contenu pour les questions outils
- [ ] Passer les logs en DEBUG après investigation

# Baseline: manual listing check against Safety Gate (Study 2)

- Date: 2026-11-09
- Tester: Product Owner (acting as marketplace product-safety analyst)
- Issue: #15 (S0-7)
- Data: `evals/baseline/study2_results_2026-11-09.csv`
- Answer key: `evals/baseline/answer_key_2026-11-08.DO_NOT_OPEN_BEFORE_TEST.json` (opened after the test)

## Question

How long does it take a marketplace employee to check one product listing against all known dangerous
products by hand, how accurate is the result, and how sure is the employee?

## Method

- 10 listings with a German title, an EAN if the seller showed one, and a photo. 5 are real dangerous
  products taken from Safety Gate alerts (title translated, alert ID removed), 5 are safe products of the
  same kind from Amazon Berkeley Objects.
- Tool: the public Safety Gate search (https://ec.europa.eu/safety-gate-alerts/screen/search) only.
  No web search, no AI, no reverse image search.
- Blind setup: photos were downloaded to neutral file names (L01 to L10) and the source URL column was
  removed from the worksheet before testing.
- Decision per listing: `match`, `similar`, `clear` or `unsure`. Time cap: 8 minutes.
- L01 was a practice round and is excluded from the results.

## Results (L02 to L10, n = 9)

| Measure | Result |
|---------|--------|
| Correct decisions | **7 of 9 (78 %)** |
| Dangerous products found (catch rate) | **4 of 5 (80 %)**: L02, L06, L07, L10 found with the correct case number; L03 missed |
| Safe products cleared | 3 of 4; L09 left `unsure` (would go to escalation) |
| Wrong `match` decisions | 0 |
| Time per listing, recorded cases (n = 6) | median **10.2 min**, mean 11.2 min, range 1.2 to 29.0 min |
| Listings over the 8-minute cap | 4 of 6 timed listings |
| Confidence | 5 for every confirmed match; 1 for both `unsure` cases |

Time was not recorded for the three `clear` listings L04, L05 and L08; they are excluded from the time
statistics.

## What made the work hard

1. **Full listing titles never work.** The German listing title returned 0 results in all 7 recorded
   searches, with and without a category filter. Alerts store brand, product type and model in separate,
   mostly English fields.
2. **The barcode cannot be searched.** In L02 the alert contains exactly the listing's EAN, but searching
   the EAN returned 0 results. The most precise identifier is only usable after the alert is already found.
3. **Results depend on a unique brand.** With a rare brand (PandaEar, Tertio) the match took 1 to 3
   minutes. With a common term (`AFF` + category: 207 results, `IPL`: 171 results, `Halskette`: 45
   results) it took 10 to 29 minutes.
4. **Photo comparison alone is not enough for a human.** In L03 (a real alert) and L09 (a safe product)
   the tester found look-alike alerts but could not decide from the photos; confidence 1 in both.
5. **Confirmation needs the full alert.** Every match was confirmed only after opening the alert and
   comparing barcode, model number or photos field by field.

## What this means for Recall Radar

| Pain point | Recall Radar feature (PRD) | Target to beat |
|-----------|----------------------------|----------------|
| Title search fails; alerts in other languages | Cross-language semantic search (B4) | Catch rate > 80 % |
| Barcode not searchable | Exact-key matching on EAN, brand + model (B4) | EAN hits found in < 1 s |
| Look-alikes undecidable by eye | Image similarity with a score + side-by-side evidence (B4, C1) | No `unsure` without evidence |
| ~10 minutes per listing | Automatic check on upload (B1) | p95 ≤ 10 s per listing |

## Extrapolation (illustration only)

At the measured median of about 10 minutes per listing, checking 1,000 new listings per day by hand would
take about 170 analyst hours per day, roughly 21 full-time analysts. This is why marketplaces check only
random samples today (DSA Art. 31), and why known dangerous products remain online.

## Limitations

- Small sample (9 listings) and a single tester who also designed the study; results show the size of
  the problem, not precise rates.
- The tester knew that about half of the listings were dangerous.
- Search terms and times were not recorded for L04, L05 and L08; L01 (practice) was run after L02.
- A first title-only search round was done before the protocol was followed; it is included in the
  recorded times where it happened inside a timed listing.

## Next measurement

The same 10 listings are run through Recall Radar once screening (B1, B4) works. The difference in time,
catch rate and confidence is reported in the v1.0 release notes.

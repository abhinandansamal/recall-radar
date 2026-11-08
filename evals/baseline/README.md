# Manual baseline study ("before" measurement)

## Study 1 (2026-11-08): alert -> ABO catalogue. Stopped.

Worksheet: `manual_baseline_2026-11-08.csv`, alerts: `alerts_2026-11-08.json`.
Observation by the analyst: searching ABO by alert name, category and model returned unrelated
products or "No match found" for most alerts. Reason: ABO contains Amazon's own catalogue, so real
Safety Gate products are (almost) never in it; also ABO product types (e.g. `BEAUTY`) differ from
Safety Gate categories (e.g. "Cosmetics"). Conclusion: wrong direction for the product. Kept as
evidence for the design change (see `docs/data/data-sources.md`, "Direction change").

## Study 2 (2026-11-08): listing -> Safety Gate check. Current.

Question measured: **how long does it take a marketplace employee to check one product listing
against all known dangerous products, by hand, and how sure are they?**

Files:
- `listing_checks_2026-11-08.csv`: 10 listings (title in German, EAN if shown, photo link) + columns to fill
- `answer_key_2026-11-08.DO_NOT_OPEN_BEFORE_TEST.json`: the truth (5 are real dangerous products
  from Safety Gate, 5 are safe ABO products of the same kind). Open only after the test.

### Tool (the same one an analyst has)
Safety Gate public search: https://ec.europa.eu/safety-gate-alerts/screen/search
(keyword search, filters for category, country, date; results show photos).

### Steps per listing (cap: 8 minutes)
1. Start the stopwatch. Open the `photo_url`, read the title and EAN.
2. Search the Safety Gate portal: EAN, brand, model, product words in German **and** English
   (the portal is mostly English), use the category filter.
3. Open promising results and compare photos.
4. Decide: `match` (same product is a known dangerous product), `similar` (needs a closer look),
   `clear` (no known dangerous product), `unsure`.
5. Stop the stopwatch; fill the row (search terms, number of results viewed, case number if found,
   confidence 1-5, what was hard).

Do L01 once untimed to learn the portal, then time all 10. Total about 1 to 1.5 hours.

### Afterwards
Open the answer key, mark right/wrong, and send the worksheet. Report: `evals/reports/baseline.md`
(minutes per listing, accuracy, confidence, pain points, extrapolation to a catalogue).

# Data profile: Safety Gate alerts in bronze (2026-11-14)

- Table: `rr_dev.bronze.sg_alerts_raw` (full history, 1,124 weekly reports since 2005, EN + DE)
- Run by: SQL Editor, Serverless Starter Warehouse, 2026-11-14
- Purpose: input for the silver design (US-010): which rules, formats and versions silver must handle
- Rule: silver rules come from these measured facts, not from assumptions

## Q1: Schema inferred by Auto Loader

```sql
DESCRIBE TABLE rr_dev.bronze.sg_alerts_raw;
```

| Column | Type |
|--------|------|
| URLrecall, barcode, batchNumber, brand, caseNumber, category, companyRecallCode, countryOfOrigin, danger, description, level, measures, name, notifyingCountry, onlineTrader, order, pictures, product, productionDates, publicationDate, reference, riskType, type, type_numberOfModel | string |
| lang | string (from the `lang=` folder) |
| _rescued_data, _source_file, _report_reference, _batch_id, _licence | string |
| _ingested_at | timestamp |

**Findings**
- All business fields are `string` (bronze keeps text as text, `inferColumnTypes = false`).
- `pictures` is a **string**, not an array: the nested `<picture>` list is stored as text. Silver must parse it (format to be checked, see Q8).
- The same 24 fields exist across 20 years; the EC generates all reports from one current schema.

## Q2: Empty fields per language

```sql
SELECT lang, count(*) AS rows_total,
       count_if(coalesce(trim(barcode), '') = '')            AS no_barcode,
       count_if(coalesce(trim(brand), '') = '')              AS no_brand,
       count_if(coalesce(trim(type_numberOfModel), '') = '') AS no_model,
       count_if(coalesce(trim(product), '') = '')            AS no_product,
       count_if(pictures IS NULL)                            AS no_pictures,
       count_if(coalesce(trim(caseNumber), '') = '')         AS no_case_number,
       count_if(_rescued_data IS NOT NULL)                   AS rows_with_rescued_data
FROM rr_dev.bronze.sg_alerts_raw GROUP BY lang ORDER BY lang;
```

| lang | rows_total | no_barcode | no_brand | no_model | no_product | no_pictures | no_case_number | rows_with_rescued_data |
|------|-----------:|-----------:|---------:|---------:|-----------:|------------:|---------------:|-----------------------:|
| de | 47,780 | 34,337 | 6,715 | 9,397 | 1,385 | 5,056 | 0 | 0 |
| en | 47,780 | 34,337 | 6,715 | 9,397 | 1,373 | 5,056 | 0 | 0 |

**Findings**
- **72 % of alerts have no barcode.** Exact GTIN matching covers at most 28 % of alerts; brand + model (14 % / 20 % empty) and similarity search carry the rest.
- 10.6 % have no pictures: image matching is not available for those.
- `caseNumber` is never empty: it can be the business key.
- No rescued data: no unknown fields in 20 years of reports.
- EN and DE agree except `product` (1,373 vs 1,385 empty): a few translations are missing.

## Q3: Case-number formats

```sql
SELECT regexp_replace(caseNumber, '[0-9]', '9') AS case_format, count(*) AS n, min(caseNumber) AS example
FROM rr_dev.bronze.sg_alerts_raw GROUP BY 1 ORDER BY n DESC LIMIT 20;
```

| case_format | n | example | Assessment |
|-------------|--:|---------|------------|
| `A99/9999/99` | 30,504 | A11/0001/14 | Valid (RAPEX, 4-digit number) |
| `A99/99999/99` | 26,232 | A11/00001/20 | Valid (RAPEX, 5-digit number) |
| `9999/99` | 20,832 | 0001/05 | Valid (2005–2010 numbering) |
| `SR/99999/99` | 15,832 | SR/00001/25 | Valid (Safety Gate, since 2025) |
| `INFO/99999/99` | 1,366 | INFO/00001/19 | Valid (information notification) |
| `OR/99999/99` | 586 | OR/00001/25 | Valid |
| `INFO/9999/99` | 124 | INFO/0031/19 | Valid |
| `999/99` | 58 | 197/05 | Valid (early, 3-digit number) |
| `EM/99999/99` | 8 | EM/00001/22 | Valid |
| `EM/9999/99` | 2 | EM/0002/14 | Valid |
| `9999/999` | 6 | 0522/081 | Typo (3-digit year) |
| `9999/99.` | 2 | 0806/10. | Repairable (trailing dot) |
| `9999/99 – 9999/99` | 2 | 0350/05 – 0352/05 | A range, not one case |
| `9999/99<br></br>` | 2 | 1150/09<br></br> | Repairable (HTML tag) |
| `9999.99` | 2 | 0559.11 | Typo (dot instead of slash) |
| `99 9999/99` | 2 | 49 0357/10 | Typo (prefix) |

**Findings**
- 10 valid formats; their union is one regular expression: `^((A\d{2}|SR|INFO|OR|EM)/\d{4,5}/\d{2}|\d{3,4}/\d{2})$`.
- 16 rows (8 cases × EN/DE) are malformed. Two kinds are repairable without guessing (strip HTML tags, strip a trailing dot); the rest go to quarantine with the reason.

## Q4: Date formats in `publicationDate`

```sql
SELECT regexp_replace(publicationDate, '[0-9]', '9') AS date_format, count(*) AS n, min(publicationDate) AS example
FROM rr_dev.bronze.sg_alerts_raw GROUP BY 1 ORDER BY n DESC LIMIT 20;
```

| date_format | n | example |
|-------------|--:|---------|
| `99-99-9999` | 95,556 | 01-02-2008 |
| (empty) | 4 | |

**Findings**
- One format only: `dd-MM-yyyy`. (The weekly index uses `dd/MM/yyyy`; the alerts do not.)
- 4 rows (2 alerts × EN/DE) have no date: quarantine.

## Q5: Barcode shapes

```sql
SELECT length(regexp_replace(barcode, '[^0-9]', '')) AS digits_only_length,
       barcode RLIKE '[,;/ ]' AS has_separator, count(*) AS n, min(barcode) AS example
FROM rr_dev.bronze.sg_alerts_raw WHERE coalesce(trim(barcode), '') <> ''
GROUP BY 1, 2 ORDER BY n DESC LIMIT 25;
```

| digits | separator | n | example |
|-------:|:---------:|--:|---------|
| 13 | no | 21,224 | `*2500562721163` |
| 12 | no | 1,256 | `'020714005887` |
| 13 | yes | 1,104 | `0 000011 283867` |
| 26 | no | 484 | `02791971059770285785105977` |
| 8 | no | 238 | `...56593835` |
| 10 | no | 176 | `0009380002` |
| 14 | no | 170 | `00159197400534` |
| 11 | no | 158 | `00842136265` |
| 26 | yes | 140 | `1 811281 170547  (on the label)6 947551 985148 (on the packaging)` |
| 39 | no | 114 | `060894055943706089405603890608940572252` |
| 52 | no | 108 | `0076995198671007699520296500769952029720076995204076` |
| 20 | no | 94 | `10581445921002000199` |
| 5 | no | 80 | `*13765*` |
| 6 | no | 66 | `135573` |
| 39 | yes | 64 | `2000000011967; 2000000012032; 2000000012216` |
| 4 | no | 62 | `0257` |
| 12 | yes | 58 | `0 78257582266` |
| 0 | no | 56 | `-` |
| 9 | no | 52 | `000046378` |
| 17 | no | 42 | `04857202000004857` |
| 7 | no | 36 | `*1804001*` |
| 16 | no | 36 | `044–8434482288540` |
| 18 | yes | 32 | `05000400029200, № МО0292` |
| 28 | yes | 32 | `1) 2007080308123, 2) 0070920705538` |
| 52 | yes | 30 | `01958840454350195884045442 01958840695850195884069592` |

**Findings**
- The field is free text: prefixes (`*`, `'`, `...`), spaces inside codes, labels ("on the label"), numbering ("1) … 2) …"), placeholders (`-`), non-Latin text.
- **Several GTINs are often glued together without a separator**: 26, 39 and 52 digits are 2, 3 and 4 EAN-13 codes.
- Valid GTIN lengths are 8, 12, 13 and 14; other lengths (4–7, 9–11, 16–20) are internal article numbers, not GTINs.
- Extraction rule for silver: split on non-digit separators; inside each digit run, accept the run if it is a GTIN with a valid check digit; a run whose length is a multiple of 13 is split into 13-digit pieces only if **every** piece has a valid check digit (otherwise nothing is guessed).

## Q6: The same alert more than once

```sql
SELECT caseNumber, lang, count(*) AS rows, count(DISTINCT _report_reference) AS reports,
       collect_set(_report_reference) AS report_list
FROM rr_dev.bronze.sg_alerts_raw GROUP BY caseNumber, lang HAVING count(*) > 1
ORDER BY rows DESC LIMIT 20;
```

| caseNumber | lang | rows | reports | report_list |
|------------|------|-----:|--------:|-------------|
| SR/01552/26, SR/01553/26, SR/01561/26, SR/01569/26, SR/01616/26 | de/en | 2 | 1 | Report-2026-22 |
| SR/02755/26, SR/02756/26, SR/02759/26, SR/02762/26 | de/en | 2 | 1 | Report-2026-40 |
| 0259/06 | de/en | 2 | 1 | Report-2006-17 |
| 0145/07 | de/en | 2 | 2 | Report-2005-11, Report-2007-6 |

**Findings** (three different causes)
1. **Corrected reports** (2026-22, 2026-40): two files of the same report; the newer file is a new version. This is what SCD2 is for.
2. **Same case twice in one report** (0259/06 in Report-2006-17): a duplicate inside the source file.
3. **Same case in two reports** (0145/07 in 2005-11 and 2007-6): a case number that appears in a report two years earlier than its year suffix; treated as two versions in report order.

Version order for SCD2: `_ingested_at`, then report year and week, then `order` inside the report.

## Q7: Rescued data and risk levels

```sql
SELECT 'rescued' AS what, substr(_rescued_data, 1, 200) AS value, count(*) AS n
FROM rr_dev.bronze.sg_alerts_raw WHERE _rescued_data IS NOT NULL GROUP BY 2
UNION ALL
SELECT 'level', level, count(*) FROM rr_dev.bronze.sg_alerts_raw GROUP BY 2
ORDER BY what, n DESC LIMIT 40;
```

| what | value | n |
|------|-------|--:|
| level | Serious risk | 45,327 |
| level | Ernstes Risiko | 45,327 |
| level | Other risk levels | 1,694 |
| level | Sonstige Risikoniveaus | 1,694 |
| level | Other types of alerts | 759 |
| level | Sonstige Warnungen | 759 |

## Q8: Format of `pictures`

```sql
SELECT pictures FROM rr_dev.bronze.sg_alerts_raw WHERE pictures IS NOT NULL LIMIT 3;
```

| pictures |
|----------|
| `<picture>https://ec.europa.eu/safety-gate-alerts/public/api/notification/image/385875</picture> <picture>…/385876</picture>` |
| `<picture>…/385877</picture> <picture>…/385878</picture>` |
| `<picture>…/385879</picture>` |

**Findings**
- No rescued data (confirms Q2).
- `level` has 3 values, translated per language. Silver maps them to one code: `serious`, `other_risk`, `other_alert`.
- 95 % of alerts are "serious risk".
- the nested list is stored as its raw XML text. Silver extracts the URLs with `regexp_extract_all(pictures, '<picture>([^<]+)</picture>', 1)`; the first URL is the main photo.

## Summary: consequences for silver (US-010)

| Topic | Silver rule |
|-------|-------------|
| Business key | `(case_number, lang)` |
| Case number | Repair HTML tags and trailing dots; validate against the 10 known formats; else quarantine |
| Publication date | Parse `dd-MM-yyyy`; empty → quarantine |
| Risk level | Map 6 texts to 3 codes |
| Pictures | Parse the text into an array of URLs |
| Barcodes | Extract GTIN candidates; keep only valid check digits; invalid candidates → quarantine (identifier only, the alert stays) |
| Brand / model | Normalise for exact matching (lower case, ASCII, no punctuation) |
| Versions | SCD2 over `row_hash`; order by `_ingested_at`, report year/week, `order` |
| Duplicates in one file | Identical rows collapse; different rows become consecutive versions |

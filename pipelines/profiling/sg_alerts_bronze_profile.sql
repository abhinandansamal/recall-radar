-- Profile of rr_dev.bronze.sg_alerts_raw (US-010 input).
-- Run in the Databricks SQL Editor (Serverless Starter Warehouse), one query at a time.
-- Results and findings: docs/data/profiles/sg-alerts-bronze-2026-11-14.md

-- Q1: which columns exist (the schema Auto Loader inferred)
DESCRIBE TABLE rr_dev.bronze.sg_alerts_raw;

-- Q2: how often each important field is empty (per language)
SELECT lang,
       count(*) AS rows_total,
       count_if(coalesce(trim(barcode), '') = '') AS no_barcode,
       count_if(coalesce(trim(brand), '') = '') AS no_brand,
       count_if(coalesce(trim(type_numberOfModel), '') = '') AS no_model,
       count_if(coalesce(trim(product), '') = '') AS no_product,
       count_if(pictures IS NULL) AS no_pictures,
       count_if(coalesce(trim(caseNumber), '') = '') AS no_case_number,
       count_if(_rescued_data IS NOT NULL) AS rows_with_rescued_data
FROM rr_dev.bronze.sg_alerts_raw
GROUP BY lang ORDER BY lang;

-- Q3: case-number formats (every digit replaced by 9, so formats group together)
SELECT regexp_replace(caseNumber, '[0-9]', '9') AS case_format,
       count(*) AS n,
       min(caseNumber) AS example
FROM rr_dev.bronze.sg_alerts_raw
GROUP BY 1 ORDER BY n DESC LIMIT 20;

-- Q4: date formats in publicationDate
SELECT regexp_replace(publicationDate, '[0-9]', '9') AS date_format,
       count(*) AS n,
       min(publicationDate) AS example
FROM rr_dev.bronze.sg_alerts_raw
GROUP BY 1 ORDER BY n DESC LIMIT 20;

-- Q5: barcode shapes: how many digits, and how often several codes share one field
SELECT length(regexp_replace(barcode, '[^0-9]', '')) AS digits_only_length,
       barcode RLIKE '[,;/ ]' AS has_separator,
       count(*) AS n,
       min(barcode) AS example
FROM rr_dev.bronze.sg_alerts_raw
WHERE coalesce(trim(barcode), '') <> ''
GROUP BY 1, 2 ORDER BY n DESC LIMIT 25;

-- Q6: the same alert more than once (corrected reports, or one case in several weeks)
SELECT caseNumber,
       lang,
       count(*) AS rows,
       count(DISTINCT _report_reference) AS reports,
       collect_set(_report_reference) AS report_list
FROM rr_dev.bronze.sg_alerts_raw
GROUP BY caseNumber, lang HAVING count(*) > 1
ORDER BY rows DESC LIMIT 20;

-- Q7: what was rescued (fields the schema did not know), plus the values of risk level
SELECT 'rescued' AS what,
       substr(_rescued_data, 1, 200) AS value,
       count(*) AS n
FROM rr_dev.bronze.sg_alerts_raw
WHERE _rescued_data IS NOT NULL
GROUP BY 2
UNION ALL
SELECT 'level',
       level,
       count(*)
FROM rr_dev.bronze.sg_alerts_raw
GROUP BY 2 ORDER BY what, n DESC LIMIT 40;

-- Q8: what pictures looks like
SELECT pictures
FROM rr_dev.bronze.sg_alerts_raw
WHERE pictures IS NOT NULL LIMIT 3;

# Data sources: availability check (Sprint 0)

- Checked: 2026-11-08, by downloading and parsing the live sources in a browser
- Result: **all three sources are available and usable**; one coverage risk (ABO has no toys), handled below
- Rule: only public data. Labels for evaluation are created by us; the data itself is never hand-made.

## 1. EU Safety Gate alerts (the "dangerous products" side)

| Item | Finding |
|------|---------|
| Access | Public XML, no key: `https://ec.europa.eu/safety-gate-alerts/api/download/weeklyReport/list/xml/en` |
| Index | 1,123 weekly reports, from Report-2005-1 to Report-2026-44 (published 06/11/2026). New report every Friday |
| Detail | One XML per report, linked from the index (`.../weeklyReport/detail/xml/<id>?language=en`) |
| Volume | Last 8 reports: 716 alerts (~90 per week); latest report: 63 alerts, 136 KB |
| Fields | caseNumber, publicationDate, reference (alert URL), category, product, brand, name, type_numberOfModel, batchNumber, barcode, riskType, danger, measures, URLrecall, description, notifyingCountry, countryOfOrigin, type, level, pictures, onlineTrader, companyRecallCode, productionDates |
| Field coverage (716 alerts) | pictures 100 % (avg 3.3 per alert), model 79 %, brand 66 %, barcode 52 %, onlineTrader 44 %, "Serious risk" 99 % |
| Top categories | Toys 170, Electrical appliances 168, Motor vehicles 60, Cosmetics 59, Chemical products 38, Clothing 36, Jewellery 31, Hobby/sports 29, Machinery 23, Protective equipment 23 |
| German | Same reports with `language=de` contain real German text (e.g. "Netzadapter", "Elektrischer Schlag") |
| Images | Picture URLs return the image (tested: `image/png`, 149 KB, HTTP 200) |
| Licence | Commission content reusable with attribution (Decision 2011/833/EU). Photos may belong to third parties: we store link + hash + embedding, not the photo, until the exact terms are confirmed in F03 (ADR) |

Sample alert (Report-2026-44): SR/03143/26, "Power adaptor", model 2430, Electric shock, Serious risk,
notified by France, origin China, sold via AliExpress, measures: recall from end users + removal of the
listing by the online marketplace.

## 2. Amazon Berkeley Objects, ABO (the "marketplace catalogue" side)

| Item | Finding |
|------|---------|
| Access | Public S3, no account: `https://amazon-berkeley-objects.s3.amazonaws.com/` |
| Listings | 147,702 listings in 16 files `listings/metadata/listings_{0..f}.json.gz` (JSON lines) |
| Fields | item_id, item_name, brand, bullet_point, color, model_name, model_number, model_year, product_type, style, main_image_id, other_image_id, item_keywords, country, marketplace, domain_name, node |
| Images | 398,212 images in `images/metadata/images.csv.gz` (image_id, height, width, path); 100 % of sampled listings have a main image |
| German | 15,097 listings have a German (`de_DE`) title |
| Licence | Bucket README + `LICENSE-CC-BY-4.0.txt` (HTTP 200) say **CC BY 4.0**; the old CC BY-NC file is gone (HTTP 404). The AWS registry page and 2022 paper still say CC BY-NC 4.0. Either way fine for a non-commercial portfolio; attribution is required |
| Overlap with Safety Gate categories | Jewellery ~5,500 (rings, earrings, necklaces), lighting & electrical ~2,600 (light bulbs 756, lamps 544, fixtures 544, adapters 140, batteries 207, fans 83, power supplies 69, ...), sporting goods 972, beauty/skin care ~1,000, baby products 263 |
| **Risk** | **No toy product types**, and toys are Safety Gate's #1 category. ABO is mostly Amazon-brand goods, so true "same product" matches with Safety Gate alerts will be rare |

## 3. GPSR legal text (for RAG with citations)

| Item | Finding |
|------|---------|
| Access | EUR-Lex HTML: `https://eur-lex.europa.eu/legal-content/{EN,DE}/TXT/HTML/?uri=CELEX:32023R0988` |
| Content | Full text in English and German; Article 22 = "Specific obligations of providers of online marketplaces related to product safety" / "Besondere Pflichten der Anbieter von Online-Marktplätzen ..." |
| Versions | Consolidated version 02023R0988-20260529 exists (amended by Regulation (EU) 2024/2748) |
| Licence | EUR-Lex content reusable with attribution |

## How the coverage risk is handled (decision for F03 / F06, to be confirmed in an ADR)

1. **Matching gold set from Safety Gate itself (real data, real positives):**
   - image → alert: one photo of an alert is the query, the alert is the target (alerts have ~3.3 photos)
   - cross-language: the German text of an alert is the query, the English alert is the target
2. **ABO as the realistic catalogue and source of hard negatives** in the overlapping categories
   (jewellery, lighting/electrical, beauty, baby, sporting goods): measures false-positive rate.
3. **Human-labelled candidate pairs** (ABO listing vs. top alerts): you label ~200 pairs as
   match / similar / no match, twice, 24 h apart. Only the labels are ours; the data stays public.
4. The README and demo state the limitation honestly: ABO has no toys, so the toy category is
   evaluated on Safety Gate data only.

## Which files we actually use

| Source | We use | We do NOT use | Why |
|--------|--------|---------------|-----|
| Safety Gate | Weekly report index + detail XML (EN and DE), photo URLs | — | Small (≈136 KB per week), complete, official |
| ABO | `listings/metadata/listings_*.json.gz` (= `abo-listings.tar`, 83 MB) and `images/metadata/images.csv.gz`; **only the small images (`images/small/`, max 256 px) of the selected categories**, fetched one by one from S3 | `abo-images-original` (110 GB), `abo-spins` (40 GB), `abo-3dmodels` (154 GB), `abo-benchmark-material` (271 GB), `abo-mvr`, `abo-part-labels` | 256 px is enough for image embeddings and keeps storage, transfer and embedding cost small; 3D and 360° data do not help our use case. Expected subset: ~10-15k listings, a few hundred MB of images |
| GPSR | Regulation (EU) 2023/988, EN + DE HTML from EUR-Lex | — | Legal grounding with article-level citations |

## How the three sources work together

| Role | Source | In the app |
|------|--------|-----------|
| "What is dangerous" (the trigger) | Safety Gate alerts | Each new alert starts a case |
| "What is on sale" (what we search) | ABO catalogue | Text + image + barcode search for matching listings |
| "What we must do, by when" (the rules) | GPSR text | RAG answers with article citations; deadlines and actions in the plain-language result |

Example: alert SR/03109/26 (Samsung-branded USB charger EP-TA200, electric shock, sold on Temu, no barcode).
The app searches the catalogue by model "EP-TA200", by meaning ("USB charger" / "USB-Ladegerät") and by
photo similarity, shows the candidate listings with evidence, cites the GPSR duties for the marketplace,
and asks a reviewer to approve or reject the proposed action.

## Direction change (2026-11-08, after the first manual test)

First design: take each alert and search a catalogue (ABO). Manual test showed almost no real
matches, because ABO is Amazon's own catalogue. New design: take each **listing** and check it
against **all known dangerous products** (Safety Gate history). Measured over the last 2 years
(104 reports, 8,739 alerts): 677 alerts name the marketplace where the product was sold
(Amazon 213, AliExpress 101, SHEIN 61, Temu 42, eBay 32, Wish 26, Allegro 11, Kaufland 6, Otto 4),
and 443 alerts are repeats of the same product (same barcode or brand + model).

New roles:
- Safety Gate = the knowledge base we search (2005-today, EN + DE) and the source of real
  "dangerous listing" test cases (an alert's photo + title in another language, without its ID).
- ABO = the stream of normal, safe listings (and look-alikes of the same kind) to measure false
  alarms and speed of clearing. In production it is replaced by the customer's own catalogue,
  connected through the catalogue MCP connector.
- GPSR = the rules (actions, deadlines, citations).

---
title: "Recall Radar – Product Requirements Document"
subtitle: "Automated detection of dangerous products on online marketplaces under the EU General Product Safety Regulation"
author: "Abhinandan Samal"
date: "8 November 2026 · Version 1.0 (Draft for approval)"
---

# Document control

| Item | Value |
|------|-------|
| Product | Recall Radar (compliance workspace) and RadarMart (demonstration marketplace) |
| Document type | Product Requirements Document (PRD) |
| Owner | Abhinandan Samal (Product Owner) |
| Status | Approved, 09.11.2026 |
| Version | 1.0, 8 November 2026 |
| Scope | What the product solves, for whom, with which features and which measurable value. Technical architecture is documented separately (HLD/LLD, ADRs). |

**Change history**

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 08.11.2026 | First concept: check each Safety Gate alert against a catalogue |
| 0.2 | 08.11.2026 | Discovery finding: manual study showed the demo catalogue rarely contains alerted products. Product extended to check every **listing** against all known dangerous products (two triggers) |
| 1.0 | 08.11.2026 | Complete PRD including the RadarMart demonstration marketplace |

# 1. Executive summary

Online marketplaces in Germany handle more than half of all online retail. Since December 2024 the EU
General Product Safety Regulation (GPSR) makes them responsible for acting quickly against dangerous
products, and since February 2026 Germany can fine breaches. At the same time, the EU's rapid alert
system for dangerous products (Safety Gate) recorded a record number of alerts in 2025, and the
Commission's own web crawler found tens of thousands of already-alerted products still offered online.

Marketplaces cannot solve this with keyword search. Alerts often have no barcode or brand, are written
in another language than the listing, and the same product is re-uploaded under new names by new sellers.

**Recall Radar** checks every new or changed listing, and the whole catalogue whenever a new alert is
published, against all known dangerous products. It compares **photos, meaning across languages and
identifiers**, explains each finding in plain language with evidence and legal citations, and lets a
human approve every action (listing removal, seller notice, buyer recall notice). Every step is
recorded for the authorities.

**RadarMart** is a fully working demonstration marketplace (storefront, seller portal, cart, checkout,
orders) connected to Recall Radar the same way a real marketplace would be, so the complete loop can be
shown end to end: a seller uploads a dangerous product, Recall Radar detects it within seconds, a
reviewer approves, the listing disappears and buyers who already ordered it are notified.

# 2. Problem statement

## 2.1 The problem in one sentence

Online marketplaces must find and remove listings of products that EU authorities have identified as
dangerous, quickly and verifiably, but the manual process is slow, incomplete and cannot keep up with
the volume, the languages and the re-uploads.

## 2.2 Market context (facts)

| Fact | Figure | Source |
|------|--------|--------|
| German e-commerce goods revenue 2025 | €83.1 bn (+3.2 %) | bevh [1] |
| Share sold via online marketplaces | 56 % (€46.2 bn, +4.9 %) | bevh [1] |
| Safety Gate alerts in 2025 | 4,671, the highest since 2003; +13 % vs. 2024, more than double 2022 | European Commission via [2] |
| Most notified categories 2025 | Cosmetics 36 %, toys 16 %, electrical appliances 11 % | [3] |
| Alerts notified by Germany in 2025 | 465 (second-highest) | [4] |
| Already-alerted products found still offered online in 2025 | more than 20,800 (Commission eSurveillance web crawler) | [2] |
| Products from 7 foreign marketplaces failing EU rules (France, 2025, 600+ tested) | 75 %; 46 % also dangerous | [5] |

## 2.3 Legal pressure on marketplaces

- **GPSR Article 22:** marketplaces must register on the Safety Gate portal with a single point of
  contact, run internal product-safety processes, act on authority orders **within two working days**
  and on product-safety notices **within three working days**, and inform consumers about recalls [6][7].
- **DSA Article 31:** after admitting a trader, the marketplace must make reasonable efforts to
  **randomly check official databases** (such as Safety Gate) for products identified as illegal [8].
- **Germany:** since 19 February 2026, the amended Product Safety Act (ProdSG) provides fines of up to
  €10,000, and up to €100,000 for serious breaches, per breach [9].
- **Compliance gap:** in the 2025 EU sweep only 53 % of checked marketplaces were registered on Safety
  Gate, and 66 to 70 % answered authority requests within two working days [10].

## 2.4 Who is affected

| Persona | Role | Pain today |
|---------|------|-----------|
| **Lena, Product-Safety Analyst** (primary user) | Screens alerts and listings | ~90 new alerts every week, a large catalogue, several languages; keyword search misses most cases |
| **Markus, Compliance Reviewer** (approver) | Decides takedowns and notices | Must decide within 2 to 3 working days and later prove why |
| **Compliance Lead / Management** | Owns GPSR compliance | No overview of exposure, response times or open risks; fine risk |
| **Sellers** | List products | Blocked without explanation, or never warned |
| **Buyers** | Buy products | Receive dangerous products that were already known to be dangerous |

# 3. How the manual process works today, and why it fails

## 3.1 How products get onto a marketplace

Most products on marketplaces are offered by independent sellers. The marketplace verifies the
**seller's identity** (DSA Article 30) and runs automatic checks on the **listing data** (required fields,
banned words). It does not physically inspect products, and the law does not oblige it to monitor
everything (DSA Article 8); instead it must check official databases at random (DSA Article 31) [8].
Listings typically go live within minutes.

## 3.2 Challenges of manual work

| Challenge | Evidence |
|-----------|----------|
| **Missing identifiers** | In 716 recent alerts, only 52 % had a barcode and 66 % a brand; photos were present in 100 % (own analysis, Nov 2026) |
| **Alerts describe products, not listings** | Only 677 of 8,739 alerts in the last two years name the marketplace where the product was sold (own analysis) |
| **Language and wording differ** | Alerts come from 30 countries; the same item is a "laser projector" in the alert and a "Party Licht Disco Lampe" in the listing |
| **Re-uploads and look-alikes** | Removed products reappear under new names or sellers [11][12]; 443 of 8,739 alerts are repeats of the same product (own analysis) |
| **Different category systems** | Marketplace product types (e.g. "BEAUTY") do not map to Safety Gate categories (e.g. "Cosmetics") (own manual study) |
| **Volume and deadlines** | ~90 alerts per week, thousands of new listings per day, 2 to 3 working days to act |
| **Proof** | Decisions are scattered across e-mails and spreadsheets; hard to show authorities a complete record |

## 3.3 Discovery evidence (own manual study, 8 Nov 2026)

The Product Owner tried to match real alerts against a marketplace catalogue by hand using name,
category and model search. Most searches returned unrelated products or "no match"; category names did
not match the catalogue's types. This confirmed that keyword search is not a workable method, and led to
the two-trigger design below. A second timed study (10 listings checked by hand against Safety Gate)
establishes the baseline for the value measurement (Section 8).

# 4. Product vision, goals and non-goals

**Vision.** No product that EU authorities have identified as dangerous stays on sale on a marketplace
longer than it takes a reviewer to click "approve".

**Goals**

1. Detect known dangerous products among listings automatically, across photos, languages and identifiers.
2. Cut the time from alert publication (or listing upload) to a reviewed decision from days to minutes.
3. Keep humans in control of every consequential action, with clear, plain-language reasons.
4. Produce a complete, exportable record that demonstrates GPSR and DSA compliance.
5. Be connectable to any marketplace through a standard connector.

**Non-goals**

- No automatic takedown without human approval.
- No legal advice; legal texts are cited for information.
- No laboratory testing or product certification.
- No real marketplace data or real payments in the demonstration (RadarMart uses public data and simulated payment).

# 5. The solution

## 5.1 How it works (user view)

| Step | What happens |
|------|-------------|
| 1. Know | Recall Radar keeps an always-updated knowledge base of all published Safety Gate alerts (since 2005, English and German) and the GPSR text |
| 2. Listen | It receives an event whenever a seller creates or changes a listing, and checks for new alerts every hour |
| 3. Screen | **Trigger A, new or changed listing:** the listing is checked against all known dangerous products. **Trigger B, new alert:** the whole catalogue is checked for that product. A nightly run re-checks everything that changed |
| 4. Explain | Each finding shows the photo comparison, matching details, risk, confidence and the legal duty in plain language, with citations |
| 5. Decide | A reviewer approves or rejects proposed actions (remove listing, inform seller, notify buyers) |
| 6. Act and record | Approved actions are executed in the marketplace; the team is notified; every step is logged |

## 5.2 Result categories

| Result | Meaning | What happens |
|--------|---------|-------------|
| **Match** | Very likely the same product as a known dangerous product | Case opened, team notified, actions proposed for approval |
| **Similar** | Same kind of product with notable resemblance | Case opened for human review, no action proposed until reviewed |
| **Clear** | No known dangerous product found | Recorded; no alert to the team |

## 5.3 Plain-language explanations

Every result answers three questions in simple words for non-experts: **What did we find? Why do we
think so? What must happen, by when?** Example:

> "This listing very likely shows the pacifier clip from EU alert SR/02809/26 (risk: strangulation).
> The photos match closely and the model number PS-001 is identical. Under the EU product safety rules
> the marketplace must remove such offers when ordered by an authority within two working days and
> inform buyers. Suggested actions: remove the listing, notify the seller, notify 3 buyers."

# 6. Product components and features

Priorities follow MoSCoW: **M** = must have for v1.0, **S** = should have (v1.0 if time allows, else
v1.1), **C** = could have (later).

## 6.1 Recall Radar: compliance workspace

### A. Knowledge base and monitoring

| ID | Feature | Prio |
|----|---------|------|
| A1 | Automatic import of all Safety Gate weekly reports and alerts (EN + DE), including photos, risks and measures | M |
| A2 | Hourly check for new alerts; history of updates and withdrawals per alert | M |
| A3 | GPSR legal text (EN + DE), searchable by article | M |
| A4 | Data quality checks on every import, with quarantine of invalid records | M |
| A5 | Monitoring dashboard: last import, new alerts, data quality results | S |

### B. Screening

| ID | Feature | Prio |
|----|---------|------|
| B1 | Listing screening on create/update event (Trigger A), result within seconds | M |
| B2 | Catalogue back-scan when a new alert arrives (Trigger B) | M |
| B3 | Nightly reconciliation of changed listings and changed alerts | M |
| B4 | Matching by photo similarity, text meaning across languages, barcode/model | M |
| B5 | Confidence score and result category (match / similar / clear) | M |
| B6 | Random spot-check campaigns over the existing catalogue (DSA Art. 31) | S |
| B7 | Configurable thresholds per category | S |

### C. Case management and human review

| ID | Feature | Prio |
|----|---------|------|
| C1 | Case per finding with evidence: photos side by side, matched fields, alert details | M |
| C2 | Plain-language explanation with legal citations (EN/DE) | M |
| C3 | Review queue with approve / reject / request-more-information and mandatory reason | M |
| C4 | Deadline timers (2 and 3 working days) and overdue warnings | M |
| C5 | Four-eyes principle: analyst prepares, reviewer approves | S |
| C6 | Comments and history per case | S |

### D. Actions and notifications

| ID | Feature | Prio |
|----|---------|------|
| D1 | Remove listing in the marketplace after approval | M |
| D2 | Seller notice (draft generated, approved, sent) | M |
| D3 | Buyer recall notice to customers who ordered the product (draft, approval, sending) | M |
| D4 | Team notifications via Discord and Gmail (new case, overdue case, daily summary) | M |
| D5 | Undo / reinstate listing with reason | S |

### E. Compliance assistant (chat)

| ID | Feature | Prio |
|----|---------|------|
| E1 | Chat in English and German about cases, alerts and GPSR duties, answers with citations | M |
| E2 | "Explain like I am not a lawyer" answers by default | M |
| E3 | Refuses to give legal advice and to act outside the user's role | M |

### F. Audit, reporting and dashboards

| ID | Feature | Prio |
|----|---------|------|
| F1 | Complete audit log: who did what, when, based on which evidence | M |
| F2 | Export of case records (PDF/CSV) for authorities | S |
| F3 | KPI dashboard: time to detection, time to decision, deadline compliance, false-alarm rate, cost per check | M |

### G. Administration and access

| ID | Feature | Prio |
|----|---------|------|
| G1 | Separate logins and roles: Analyst, Reviewer, Admin | M |
| G2 | User management and role assignment | M |
| G3 | Connector management: marketplace connection, keys, health status | S |
| G4 | English and German user interface | M |

## 6.2 RadarMart: demonstration marketplace

RadarMart is a fictional marketplace built to production standards. It is the place where sellers list
products and buyers shop, so that Recall Radar can be shown working on a live system. Its catalogue is
built from public data (Amazon Berkeley Objects listings, CC BY 4.0) plus re-uploaded products from
Safety Gate alerts.

### H. Storefront (buyers)

| ID | Feature | Prio |
|----|---------|------|
| H1 | Home page, category navigation, product search with filters (EN/DE) | M |
| H2 | Product page with photos, price, description and GPSR information (manufacturer, EU responsible person, warnings) | M |
| H3 | Shopping cart: add, change quantity, remove | M |
| H4 | Checkout with address and **simulated payment** (no real money) | M |
| H5 | Buyer account: registration, login, order history | M |
| H6 | Product safety notice on removed products and recall messages in the buyer's account and by e-mail | M |
| H7 | "Report a safety concern" button on every product page (feeds Recall Radar as a notice) | S |
| H8 | Wish list, reviews | C |

### I. Seller portal

| ID | Feature | Prio |
|----|---------|------|
| I1 | Seller registration with trader details (name, address, contact; DSA Art. 30 style verification, simulated) | M |
| I2 | Create and edit listings: title, description, category, price, stock, photos, EAN, GPSR fields | M |
| I3 | Listing status: live, under review, removed (with reason) | M |
| I4 | Messages from the marketplace (safety notices) | M |
| I5 | Bulk upload via CSV | C |

### J. Marketplace back office

| ID | Feature | Prio |
|----|---------|------|
| J1 | Overview of listings and orders | M |
| J2 | Every listing create/update sends an event to Recall Radar | M |
| J3 | Executes approved actions from Recall Radar (removal, notices) | M |

### K. Security and privacy (both products)

| ID | Requirement | Prio |
|----|-------------|------|
| K1 | Separate roles: buyer, seller, marketplace admin (RadarMart); analyst, reviewer, admin (Recall Radar) | M |
| K2 | Secure login, password hashing, session protection, CSRF protection, rate limiting | M |
| K3 | Image upload validation (type, size), safe image fetching from allowed domains only | M |
| K4 | Signed events between RadarMart and Recall Radar; duplicate events ignored | M |
| K5 | Protection against prompt injection hidden in listing text | M |
| K6 | GDPR: only demo personal data, data minimisation in logs, privacy notice, deletion on request | M |
| K7 | AI transparency: users are told when content is AI-generated (EU AI Act Art. 50) | M |

# 7. Key user journeys

1. **Re-upload caught at upload.** A seller lists a pacifier clip identical to an alerted product. Within
   seconds Recall Radar opens a case; the reviewer approves; the listing shows "removed – product
   safety"; the seller receives a notice.
2. **New alert, catalogue scan.** A new alert for a laser projector is published. Within the hour Recall
   Radar finds two RadarMart listings, notifies the team on Discord and by Gmail, and proposes removal.
3. **Buyers protected.** One of those listings had three orders. After approval, the three buyers get a
   recall notice in their account and by e-mail.
4. **Safe product passes.** A seller uploads a safe baby bib; the result is "clear" and no one is disturbed.
5. **Question to the assistant.** The reviewer asks in German which deadline applies; the assistant answers
   in plain language and cites the GPSR article.
6. **Audit.** The compliance lead exports all decisions of the last month for the authority.

# 8. Value and success measurement

## 8.1 Value drivers

| Value | How Recall Radar creates it |
|-------|----------------------------|
| **Speed** | Minutes instead of days from alert or upload to a reviewed decision |
| **Coverage** | Every alert is checked against every listing; every new listing is checked against every alert |
| **Prevention** | Re-uploads are caught before the first sale |
| **Efficiency** | Analysts review a short list of evidence-backed candidates instead of searching |
| **Compliance and risk** | Deadlines tracked, complete audit trail; lower risk of fines (up to €100,000 per breach in Germany) and of consumer harm |
| **Trust** | Buyers are informed about recalls; sellers receive clear reasons |

## 8.2 KPIs

Targets marked *provisional* are confirmed after the baseline study.

| KPI | Definition | Target (v1.0) |
|-----|-----------|---------------|
| Catch rate | Share of known dangerous products in the test set that are detected (match or similar) | provisional ≥ 90 % |
| False-alarm rate | Share of safe listings wrongly flagged | provisional ≤ 5 % |
| Time to detection | Event received → result available (listing check) | provisional p95 ≤ 10 s |
| Back-scan time | New alert → catalogue scan finished | provisional ≤ 5 min |
| Time to decision | Case opened → reviewer decision | measured; compared with baseline |
| Analyst minutes per check | Manual (baseline) vs. assisted | measured |
| Deadline compliance | Cases decided within 2 / 3 working days | 100 % in demo |
| Explanation quality | Citation correctness and readability (Flesch / Flesch-Amstad) | provisional ≥ 95 % correct citations |
| Cost per 1,000 checks | Cloud + AI cost | measured; total running cost ≤ €30 per month |

## 8.3 Baseline and proof

The baseline is measured by hand before development (Study 2: 10 listings, time per check, accuracy,
confidence). The same cases are processed with Recall Radar after development. The difference is
reported in the release notes, together with an extrapolation: minutes saved per check × number of
checks per year. Example for orientation only: if a manual check took 30 minutes and an assisted one 8
minutes, the 4,671 alerts of 2025 alone would save about 1,700 analyst hours per year.

# 9. Product-level quality requirements

| Area | Requirement |
|------|-------------|
| Availability | The live demo is reachable 24/7; it may take a few seconds to wake up after idle time (cost control) |
| Performance | See KPIs; the storefront page loads quickly on a normal connection |
| Languages | English and German throughout (UI, explanations, notices) |
| Accessibility | Keyboard navigation, sufficient contrast, alt texts |
| Reliability | Failed steps are retried automatically; failures are logged, explained and reported |
| Privacy | GDPR principles; demo data only |
| AI governance | Human approval for every consequential action; AI-generated text labelled; results explained |
| Cost | Total running cost ≤ €30 per month |

# 10. Data sources

| Source | Use | Licence |
|--------|-----|---------|
| EU Safety Gate weekly reports (2005 to today, EN/DE) | Knowledge base of dangerous products; test cases | Commission reuse policy, attribution |
| Amazon Berkeley Objects (147,702 listings, 398,212 images) | RadarMart catalogue of normal, safe products | CC BY 4.0 (attribution) |
| GPSR, Regulation (EU) 2023/988 (EN/DE, EUR-Lex) | Legal duties, citations | EUR-Lex reuse, attribution |

# 11. Assumptions, constraints and risks

| Item | Type | Handling |
|------|------|----------|
| Toys are the second-largest alert category but absent from the public catalogue | Risk | Toy detection is tested with Safety Gate data only; stated openly |
| No real marketplace traffic | Constraint | RadarMart and a traffic simulator generate realistic events |
| German full-text and photo matching quality unknown before testing | Risk | Every matching stage is evaluated on a labelled test set before release |
| Photos in alerts may belong to third parties | Risk | Linked and fingerprinted, not redistributed, until licence terms are confirmed |
| Budget ≤ €30 per month | Constraint | Serverless hosting, scale-to-zero, small open/efficient AI models |
| Laws change (e.g. EU AI Act timelines) | Risk | Legal texts are versioned; sources dated |

# 12. Release plan

| Release | Content |
|---------|---------|
| **v1.0** (end of project) | All **M** features of Recall Radar and RadarMart, end-to-end demo, measured KPIs |
| **v1.1** | **S** features (spot-check campaigns, four-eyes principle, export, connector management, safety-concern button) |
| **Later** | **C** features, connectors for real marketplace APIs, more languages |

The detailed sprint plan, backlog and progress are tracked on the project board and in the repository.

# 13. Glossary

| Term | Meaning |
|------|--------|
| Safety Gate | EU rapid alert system for dangerous non-food products |
| GPSR | General Product Safety Regulation (EU) 2023/988 |
| DSA | Digital Services Act (EU) 2022/2065 |
| Listing | A product offer by a seller on a marketplace |
| Alert | A published notification about a dangerous product |
| Case | A finding that needs human review |
| HITL | Human in the loop: a person approves before an action is executed |

# 14. Sources

1. bevh, press conference presentation 2026: https://bevh.org/fileadmin/content/05_presse/Pressemitteilungen_2026/Praesentation_bevh_2026.pdf
2. Safety Gate 2025 report summary: https://informat.ro/en/eu/eu-safety-gate-cosmetics-109704
3. EaseCert, Safety Gate 2025 report: https://easecert.com/blogs/insights/eu-safety-gate-2025-report
4. Euronews, 5 March 2026: https://www.euronews.com/2026/03/05/record-number-of-dangerous-products-intercepted-by-the-eu-in-2025-safety-report-finds
5. Reuters via WHBL, 29 April 2026: https://whbl.com/2026/04/29/french-regulator-says-most-e-commerce-platform-products-it-tested-breach-eu-rules/
6. Matheson, product safety for online marketplaces: https://www.mhc.ie/latest/insights/product-safety-for-providers-of-online-marketplaces
7. Freshfields, new product safety rules for online marketplaces: https://www.freshfields.com/en/our-thinking/blogs/risk-and-compliance/green-light-for-new-product-safety-rules-affecting-online-marketplaces-102id7j
8. DSA Article 31: https://www.springlex.eu/en/packages/dsa/dsa-regulation/article-31/
9. novomind, GPSR and ProdSG fines: https://www.novomind.com/en/blog/general-product-safety-regulation-gpsr/
10. EU product safety sweep 2025 summary: https://www.dsca.gob.es/sites/default/files/consumo_masinfo/Resumen_informe_UE_SWEEP_2025.pdf
11. Which?, listing illegal products on marketplaces: https://www.which.co.uk/news/article/how-we-easily-listed-an-illegal-product-on-online-marketplaces-a8cJp4R3hhAX
12. BEUC, 250 products tested: https://www.beuc.eu/press-releases/two-thirds-250-products-bought-online-marketplaces-fail-safety-tests-consumer-groups
13. Own analyses (Safety Gate XML, ABO metadata, manual studies): `docs/data/data-sources.md`, `evals/baseline/`

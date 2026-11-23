# KAVACH Case Dossier Documentation

## 1. Overview and Route

The dossier page is accessible at the route `#/case/<case_id>/dossier`. It provides a printable, single-page case summary designed for offline review and export via browser print controls.

## 2. Page Contents and Structure

The page consists of up to nine numbered sections rendered in sequential order:

1. **Title Block**: Displays case name, case ID, synthetic indicator, full 64-character case fingerprint (derived `document_hash` from leads response, unbroken without shortening), generation timestamp passed at render time, and the current user's name and role. For an unanalyzed case, only this block, case facts, evidence inventory, and limits are displayed along with the notice: "Case not analyzed: no leads or graph summary."
2. **Disclaimer**: The disclaimer string returned by the API leads endpoint rendered verbatim.
3. **Case Facts**: Count of case documents, total CDR record rows, and total bank record rows.
4. **Graph Summary**: Total nodes, total edges, schema version string, and a tabular breakdown of node counts per entity type (PERSON, PHONE, IMEI, ACCOUNT, VEHICLE) sorted alphabetically.
5. **Priority Leads**: The top 10 leads ordered strictly by money flow from the server (never re-ordered). Each entry includes rank, name, person ID, money-flow score, controlled accounts, role chips, verbatim reasons, and plain-text evidence references (FIR documents naming this person: list of up to 10 document IDs with total count, or "none recorded", followed by accounts and paise flow). Includes the note: "Ordered by money flow; structural scores are explanation only".
6. **Flagged Detector Leads**: Accounts and phones flagged by mule and burner detectors with `flagged: true`, displaying identifier, detector score, reasons, and evidence row references. When no items are flagged, displays "No flagged items."
7. **Evidence Inventory & Hashes**: Hash table listing all case documents with raw upload SHA-256, stored text SHA-256, and character count; CDR file rows and SHA-256; bank transactions file rows and SHA-256; and the 64-character case fingerprint. CDR and Bank rows display the label "uploaded file name not recorded" instead of fixed filenames. All hashes are rendered in monospace with word wrapping. Includes explanation note regarding raw bytes and stored text hashes.
8. **System Limitations**: The verbatim limitations strings from the leads endpoint, supplemented by notes on typed text only (no OCR) and multi-entry name variations.
9. **Certificate Block**: Draft template for Certificate under Section 63(4)(c) of the Bharatiya Sakshya Adhiniyam, 2023 (Part A) with signatory blanks represented by underscores, followed by the statement: "Part B (expert) is not completed by this system."

## 3. API Endpoints Feeding the Page

The page consumes existing backend endpoints without requiring specialized report generation endpoints:

- `GET /api/cases/{case_id}`: Supplies case metadata, document lists with hashes, and CSV file statistics.
- `GET /api/cases/{case_id}/leads`: Supplies money-flow priority leads, detector outputs, disclaimer, and case fingerprint.
- `GET /api/cases/{case_id}/people`: Supplies entity records with document references naming each person.
- `GET /api/cases/{case_id}/graph`: Supplies graph summary metrics and node elements for type counting.

## 4. How to Open and Save as PDF

1. Select a case from the case rail and click the **Dossier** link in the navigation menu, or navigate directly to `#/case/<case_id>/dossier`.
2. Click the **Print / Save as PDF** button at the top of the page, or press `Ctrl+P` (`Cmd+P` on macOS).
3. In the browser print dialog:
   - Set **Destination** to **Save as PDF**.
   - Set **Paper size** to **A4**.
   - Set **Layout** to **Portrait**.
   - Check **Background graphics** to preserve table borders and token shading.
4. Click **Save** to write the PDF file to disk.

Print stylesheets automatically hide UI chrome (status bar, case rail, print button, limits trigger), expand the document to full width, avoid page breaks within table rows, and enforce A4 14mm margins.

## 5. What is Not Included

- No client-side or server-side third-party PDF compilation libraries.
- No legal assertions, automated signing, or evidentiary certifications.
- No modifications to database state, audit log structures, or backend schemas.
- No new external network requests or dependencies.

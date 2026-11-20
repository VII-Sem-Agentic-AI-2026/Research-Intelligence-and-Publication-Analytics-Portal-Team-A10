# Project scope and engineering acceptance criteria

Updated: 27 October 2026. This document supersedes older teaching notes where
they conflict with current behavior. It includes the 16 engineering-audit fixes.

## Purpose

A local, authenticated research publication portal for faculty, academic reviewers
and research administrators. It imports authorized source exports, calculates
checkable metrics, and produces reports that require explicit human review.
Gemini provides a role-scoped conversational assistant and explanatory text.
Deterministic code owns data permissions, calculations and publication decisions.

## Data and scientific scope

- Faculty retain a separate association with a canonical publication. Department
  totals count unique publications; faculty views retain their own associations.
- Reports cover either publications through a reporting year or publications in
  that year. Reporting years must be four digits, between 1900 and next year.
- Full department names and existing abbreviations are accepted. Built-in aliases
  include Mechanical Engineering -> ME and Computer Science and Engineering -> CSE.
- Citations describe the imported snapshot, not historical citations received in
  the reporting year. Fractional/malformed counts are rejected. Unknown/missing
  counts parse as unknown and cannot enter an active metrics dataset until resolved;
  they never silently become a measured zero.
- Multi-source agreement is corroboration, not verified author identity. Human
  attribution review remains necessary. DOI/title-year candidates with missing
  DOI data are surfaced for source correction, not automatically merged or
  resolved through an approval flag.
- Explanations receive actual queried sources and sources contributing in-scope
  evidence, not the plan's default source list. Sources returning no in-scope
  records cannot be described as contributing data. Known source-name violations
  cause the model text to be withheld and replaced by a deterministic summary.
  Explanation checks are recorded in groq_explanation_validation. The publication
  gate also rejects stored drafts naming sources absent from their evidence.
  This conservative name check is not a general proof of semantic correctness.

## Consent and authorization

- Faculty may change only their own assigned consent/profile links and upload only
  their own publication exports. Administrators and Research Office retain the
  existing ability to manage faculty profiles; this does not prove personal consent.
- Every consent may be withdrawn, including the last active source. Imported data
  is retained; source reads/uploads requiring withdrawn consent are denied.
- Publication of a pending report rechecks current source consent. Affected drafts
  must be regenerated and reviewed. Already published historical versions are
  retained; withdrawal does not silently delete history.
- Enabled source profiles require absolute HTTP(S) URLs without embedded
  credentials. URL validity is not a claim of profile ownership.
- HoD scope is department-limited. Academic approval belongs to Dean, HoD or
  Research Office accounts, not Administrator accounts. See ACCOUNTS.md.

## Report integrity and recovery

- The validation gate recomputes metric values and unique-publication summary
  totals and verifies evidence IDs against the contributing publications.
- Publication reruns validation even if a previously saved validation was green.
- Every attribution and duplicate decision requires the existing human review.
- Only RUNNING or FAILED runs can resume. A REQUIRES_CORRECTION run needs corrected
  inputs and a new execution. Completed/published runs return their existing state.
- An omitted lab selection uses the full pipeline; an explicit empty list is an
  error. An explicit tool-budget argument takes precedence over the environment;
  otherwise RESEARCH_TOOL_BUDGET defaults to 10000, bounded to 1–1000000.

## Input, output and AI safeguards

- Roster imports reject incomplete rows atomically with row numbers rather than
  silently dropping faculty. Publication records retain source provenance.
- BibTeX supports one-line/multiline entries, nested braces, quoted commas and
  multiple entries. Unsupported string macros/concatenation must be expanded;
  they produce an explicit error. Other supported formats remain CSV, TSV, XLSX,
  JSON and RIS.
- Spreadsheet-facing CSV exports prefix formula-leading text with an apostrophe;
  canonical source text remains unchanged internally.
- Passwords, API keys and upload bytes use secure inline forms. Recognizable
  credential statements in normal chat are rejected before model invocation and
  history persistence. Recognizable sensitive older messages are redacted when
  reading history and before supplying history to the model. No pattern detector
  can guarantee detection of arbitrary unlabeled secrets.
- AI rate-limit errors produce safe HTTP 429 responses with retry guidance instead
  of provider organization/billing payloads. Local controls still work without AI.
- Gemini limits remain account-dependent. The shared key can be saved using
  Windows account-bound DPAPI encryption and is restored automatically at startup.
  Disable AI removes the saved key. Per-user portal keys remain future scope.

## Explicit exclusions

Local stdio MCP transport for Gemini report research tools is documented in MCP.md.
This release does not implement licensed live publication-source
adapters, automatic ORCID resolution, historical citation reconstruction, public
Internet deployment, institutional SSO or certified NIRF/NAAC submissions. Export
labels do not imply regulatory compliance. Browser/device layout and live Gemini
quota behavior need separate end-to-end validation beyond the isolated tests.

## Audit regression mapping

| Finding | Implemented correction | Permanent regression coverage |
|---|---|---|
| B01–B02 | Complete revocation; current-consent publication check | tests/test_audit_fixes.py |
| B03 | Independent totals, metric and evidence-ID checks | tests/test_audit_fixes.py |
| B04–B05 | Credential screening/history redaction; safe provider errors | tests/test_audit_fixes.py |
| B06–B07 | CSV formula neutralization; profile URL validation | tests/test_audit_fixes.py |
| B08–B10 | Brace-aware BibTeX; atomic roster errors; strict/unknown counts | tests/test_audit_fixes.py |
| B11 | Missing-DOI candidate review without auto-merge | tests/test_audit_fixes.py |
| B12–B14 | Recovery guards; empty-selection rejection; explicit budget | tests/test_audit_fixes.py |
| B15–B16 | Reporting-year bounds and department aliases | tests/test_audit_fixes.py |

Older audit reports describe the pre-fix snapshot. Keep them as historical evidence;
use the post-fix verification outputs to assess the current implementation.

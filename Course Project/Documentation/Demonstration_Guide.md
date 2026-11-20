# Project demonstration guide

Artifact: Research Intelligence and Publication Analytics Portal
Team division: A

## Before the demonstration

1. Install the requirements from Course Project/Code in a new virtual environment.
2. Start the portal on port 8001 and create the initial administrator locally.
3. Create the faculty and reviewer accounts through account management. Give each
   account its appropriate faculty ID or department; keep passwords private.
4. Configure the Gemini key using the secure administrator form if demonstrating
   AI-assisted reports. Do not display the key in slides, terminals or recordings.
5. Use the shipped fictional fixture or authorized exports. Explain the dataset
   and source coverage to the examiner before showing metrics.

## Suggested demonstration sequence

1. Explain fragmentation of publication data and the stakeholders in the original
   problem statement. Show the README and repository folders.
2. Sign in as Faculty, select the department if required, and show profile links,
   consent controls and the account's own publication upload surface.
3. Show a supported source export and its provenance fields, then import it into
   the matching faculty profile. Source consent must be enabled first.
4. Sign in as a department reviewer. Generate a bibliometric report for CSE through
   2026, or use a reporting period compatible with the demonstration dataset.
5. Inspect the executed lab chain, source records, duplicate candidates, citation
   method and source coverage. Explain that Gemini's plan is advisory and the
   calculations are performed by Python.
6. Record attribution evidence and individual match decisions. If metadata needs
   correction, correct the inputs and regenerate the report.
7. Publish with an authorized academic reviewer. Show the released version and
   CSV export, then explain rollback. An administrator cannot academically approve.
8. Show Verification_Results.txt and explain one authorization regression and one
   metric or import regression. Show MCP.md for the actual tool transport path.

## Questions to answer accurately

- Imported source agreement is corroboration, not independently verified author identity.
- Citation counts are imported snapshots. Grouping by publication year does not
  show citations received in each calendar year.
- Live licensed publication-source integration remains future scope.
- NIRF/NAAC labels describe export organization, not regulatory certification.
- The project contains 14 internal labs; the course's 12 assignments are separate.

## Remaining submission actions

Add the 12 assignments later. The repository is
https://github.com/Naveen-R789/Research-Intelligence-and-Publication-Analytics-Portal.
Transfer it to the teacher's designated organization after its link is supplied,
then submit the resulting repository URL and artifact name in the approval form.

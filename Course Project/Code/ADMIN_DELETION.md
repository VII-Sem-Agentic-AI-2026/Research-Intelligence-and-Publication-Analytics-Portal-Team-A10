# Administrator deletion

Sign in as an administrator.

- In **Account management**, disable the account first. Its **Delete account permanently** button then appears. Confirmation removes the login record, credentials, sessions, pending assistant confirmations and private portal chat documents. The administrator cannot delete their own account. Faculty profiles, publications, consent decisions and historical review/audit records remain.
- In **Reports**, use **Delete report permanently** and confirm. This removes the report run, all its saved published versions and its report-history entry. If it was the current published report, the current pointer is cleared and exports are unavailable until another report is published or restored. Source publications remain. A report currently marked RUNNING must finish first.

The assistant exposes the same administrator-only actions and requires an explicit confirmation button. Saying yes alone does not execute deletion.

Deletion is authoritative in SQLite. Durable markers prevent leftover JSON mirrors, migration or stale cached writes from restoring deleted reports. Failed file cleanup produces a warning and is retried when connectors reload. New accounts receive identifiers greater than all previously allocated identifiers, so they cannot inherit deleted account histories or review assignments.

Deletion audit records and historical consent/review evidence are retained. Existing backups, audit logs, already downloaded exports and copies held outside the portal are not erased. These controls remove active application records; they are not a forensic secure-erasure facility.

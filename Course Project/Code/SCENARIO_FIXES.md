# Scenario audit fixes

The portal now reads bounded JSON request bodies with a ten-second read timeout before acquiring any mutation lock. Read endpoints do not take the mutation lock. Report generation and resume use separate orchestrators and per-user operation locks; short mutations retain serialized authorization and persistence checks. The same user's assistant conversation is serialized so concurrent messages do not overwrite history. Requests still execute synchronously in server threads; this is not a distributed background-job system.

Research Office can select a replacement active Dean when the previously assigned Dean account is disabled. The old pending/accepted request is cancelled in the same transaction as the new assignment. Both changes are audited. The replacement must accept before reviewing or publishing.

Uploads reject every kind except `roster` and `publication` before processing or archiving.

Consent responses commit their decision, actor, source consent, and a pending compatibility-export entry together in SQLite. File export failures produce a successful saved decision with an export warning. Pending exports retry when connectors reload, including server startup. Dataset lookup reads the SQLite source document even if its JSON mirror does not yet exist. SQLite remains authoritative; the export does not write older data back into the database.

The HTTP workspace returns counts and report summaries rather than full publication arrays. Publications use `GET /api/publications?page=1&page_size=50&query=...&year=...`; page size is limited to 100 and access scope is applied before filtering/pagination. Report summaries use `GET /api/reports?page=1&page_size=10`, limited to 20. Authorized detail uses `GET /api/report?run_id=...`. The dashboard provides search, page controls, and an explicit Open report details button. The assistant's publication and report queries also support page numbers.

Regression checks in `tests/test_stress_fixes.py` cover upload atomicity, slow requests, another user's concurrent mutations, Dean replacement, export failure/retry, normalized indexes, compact workspace data, pagination and report-detail isolation. `tests/test_portal_pagination.js` checks pagination controls and report-detail loading with a simulated DOM.

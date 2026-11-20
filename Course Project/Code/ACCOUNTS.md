# Accounts and role-specific portals

On their first sign-in, faculty select and confirm their department. The selection
is stored on both the account and the linked faculty record in the dataset;
existing and future publications inherit department membership through faculty ID.
Exports do not need a department column. Existing faculty accounts are asked to
confirm once after this update. Department corrections after confirmation are
handled by the administrator. Password changes remain available during onboarding.
Faculty must complete department selection before uploading publication exports.
Uploads are restricted on the server to the account's own faculty ID and update
matching source records while retaining other faculty members' records.

Open http://127.0.0.1:8001. If no accounts exist, first-time setup creates the
administrator. Choose your own login ID and a unique password of 12–128 characters.
There are no shipped passwords, sample login accounts or public registration.
Setup is closed transactionally after the first administrator is created.

Under Account management, the administrator creates accounts and assigns roles.
Create/import the faculty roster before assigning faculty accounts. Assign a
faculty account to one faculty ID, and a HoD to one department. Give each person
their initial credentials privately; they can change the password after login.

| Role | Data scope | Allowed actions |
|---|---|---|
| Faculty | Own profile, uploads and report results | Edit own consent/source links; upload own publications; change own password |
| HoD | Assigned department | Generate reports; review attribution/matches; approve department reports |
| Dean | Institution | Generate, review, approve and roll back published reports |
| Research Office | Institution | Manage/import research data, generate/review/approve reports and roll back |
| Administrator | Institution | Manage accounts, disable accounts, manage/import data and generate reports; cannot academically approve |

The UI changes navigation by role. The API independently checks permissions on
every request; changing role, reviewer name, faculty ID or department in a browser
request cannot grant access. Faculty responses exclude other faculty results,
institutional narratives and internal source snapshots. HoDs cannot review reports
from other departments. Administrative and academic approval duties are separate.

Passwords are salted and hashed using PBKDF2-HMAC-SHA256 (600,000 iterations).
Raw passwords are never stored. Session tokens are stored only as SHA-256 digests
in SQLite; browser cookies are HttpOnly and SameSite=Strict with one-hour expiry.
Logout revokes the session. Password changes and disabling an account revoke
existing sessions. Login throttling limits failed attempts by login ID and address.
Account creation/disabling is recorded in account_events. Existing shared-token
sessions are not migrated and cannot authenticate to the new portal.

Accounts and sessions live in runtime/portal.sqlite3 alongside research state.
Existing research records and published reports remain intact. Back up that
database using SQLite's backup facilities; do not copy only a live WAL-mode file.

This deployment binds only to the local machine. First-time setup must be done by
the machine owner before permitting other local users to access it. Public/LAN
deployment requires HTTPS, host configuration and institutional identity policies;
institutional SSO, email invitations and automated forgotten-password recovery are
not included. Do not expose the HTTP server directly on the Internet.

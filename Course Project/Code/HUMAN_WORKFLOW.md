# Faculty consent and Dean review

## Group consent requests

Research Office can select **Department-wide** or **Institution-wide** under
**Consent requests → Request consent from a group**. Select the sources and
purpose, then preview recipients before sending. Requests use each faculty
member's saved profile links. The preview explains skipped faculty: no active
account, missing/invalid links, existing consent, or overlapping pending requests.
If recipients or request details change, a new preview is required.

Sending creates separate requests; each faculty member approves or declines only
their own request. The Research Office inbox groups responses by batch and shows
pending, approved, declined and expired counts. Requests expire after seven days.
This uses portal inbox delivery, not email.

## Attribution review checklist

Reviewers confirm faculty identity, publication ownership and resolution of
namesake/ownership conflicts using three checkboxes. All must be selected before
confirmation. The server validates the checklist and stores the selections,
reviewer identity and timestamp. No typed note is required in the dashboard.

Research Office sends a source-specific consent request from **Consent requests**. An active faculty account must be linked to the profile. The request records its purpose, exact source URLs, requester, and seven-day expiry. Sending it does not grant consent.

The assigned faculty member signs in, opens **Consent requests**, and approves or declines. Approval enables only the requested sources and records the faculty user's identity. Declining preserves existing consent. Faculty can also manage or revoke their own source consent from their profile. Research Office and administrators may revoke consent but cannot grant new consent or change an approved URL directly, including through bulk JSON imports. Existing historical consent is preserved.

For a validated draft awaiting approval, Research Office selects an active Dean in **Reports** and sends a review request. The Dean responds in **Dean review requests**. Once assigned, review and publication are blocked until that Dean accepts; only that Dean can then record review decisions and publish. A declined assignment may be sent to another Dean. Acceptance does not itself approve or publish the report. All existing evidence, attribution, duplicate and current-consent publication checks still apply.

Requests, responses and actor identities are stored in SQLite. Notifications are portal inbox entries; no email delivery is implemented. Reports without a named assignment retain the existing role-based review workflow. The assistant exposes the same scoped request/response actions with explicit confirmation.

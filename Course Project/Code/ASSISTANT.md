# Conversational dashboard assistant

After sign-in, open **Assistant** at the bottom right. The resizable-by-viewport
panel remains available while moving between workspace views. It uses the external
Gemini model selected by GEMINI_MODEL; default gemini-3.5-flash-lite. Research-context
sharing to Gemini was explicitly approved by the user for this implementation.

If the key is missing, an administrator sees **Configure AI** in the chat panel.
The secure key form sends the value directly to the local server and saves it
using Windows account-bound DPAPI encryption. It never passes through the model or
chat history. Saved keys load automatically after restart under the same Windows
account. Disable AI deletes the saved key. GEMINI_API_KEY in the server environment
continues to work. The app never simulates a model response when Gemini is unavailable.

Examples:

- Faculty: “Show my publications”, “Generate my 2026 bibliometric report”,
  “Upload my Scopus export”, “Update my source consent”.
- HoD: “Generate the 2026 CSE bibliometric report”, “Which drafts need review?”
- Dean/Research Office: “Show the evidence for this report”, “Review this duplicate”,
  “Approve report run-…”, “Export the current published report”.
- Administrator: “Create a faculty account for …”, “List accounts”, “Disable this
  account”, “Upload a faculty roster”. Administrator cannot approve academic reports.
- Everyone: “Change my password”, “Sign me out”, “Open my publications”.

The LLM calls a genuine LangChain StructuredTool. A shared Actions gateway executes
the same authorization rules used by the dashboard API. Faculty report generation
uses only that faculty's records. HoD report actions stay within their department.
Scoped read tools never return another faculty's records to a faculty account.
Histories are stored by server-authenticated user ID, not by a client-supplied ID.

Account creation, password changes, API keys, sign-out and file selection appear as
inline secure forms. Passwords, session cookies, raw file bytes and key fields are
excluded from model tools. Parsed publication records may be supplied to Gemini when
the signed-in account has access. Do not type credentials into ordinary chat.

Consent changes, attribution decisions, duplicate decisions, publishing, rollback
and disabling accounts produce an explicit confirmation card showing the proposed
parameters. Pending confirmations expire after ten minutes, are bound to a user,
and can execute once only. Dismissing the card leaves the action unexecuted. The LLM
has no confirmation tool and cannot grant itself permission. Account creation and
credential submissions require the user's secure-form submission.

Each message allows at most five model rounds and eight tool calls. Identical
mutation requests within a turn reuse their result. Publication reads return at
most 100 records; report lists return at most 30 summaries and disclose totals.
Large tool responses are explicitly marked truncated. Narrow the query when needed.

Verification uses scripted models with the real tool loop and temporary SQLite
databases, including faculty isolation, department restrictions, confirmation
ownership/replay protection, personal report generation and account-private history.
An actual Gemini request still requires a valid key and available account quota.

Report explanations now receive actual source coverage rather than the planned
source list. Unsupported source mentions are withheld and replaced by a verified
summary. Per-faculty queried sources and contributing evidence sources are retained
separately, and historical pending drafts are rechecked before publication.

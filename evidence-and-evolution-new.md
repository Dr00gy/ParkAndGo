---

# C07 Engineering Decision Record (re-verified against reporting baseline)

This section re-states the three C06 findings in the exact format C07 asks
for (Claim / Expected / Observed / Verify / Disposition / Closure
evidence), reproduced against the **reporting baseline** — updated
2026-10-31 to the actual current HEAD of the real GitHub repository,
commit `df96da241a71ca5f06087aa048a4a73980d4c405` ("In place edit of
review output", 2026-10-26) — rather than only against the original
**C06 assessed baseline** (the unclean `main` working tree AutoRepo
reviewed on 2026-10-25). *(Updated 2026-10-31: the team shared the real
GitHub commit history, so the re-verification below is now checked
against actual commit hashes/messages/dates instead of only
team-reported references.)* The full checklist AutoRepo submitted stays
in `C06_Assessment_Form_CZ_filled.md` / `C06_Assessment_Form_EN_filled.md`;
this is the disposition record C07 asks to be kept in
`docs/evidence-and-evolution.md`.

### F1 — 10× concurrency pressure was never measured

- **Claim:** the design addresses the 10× concurrent reservation pressure
  from `intent-and-change.md` with an evaluable criterion, a measurement,
  and a decision derived from that measurement (C04 obligation).
- **Expected:** a declared measurable workload, a pass/fail criterion, and
  a decision that follows from an actual measured result.
- **Observed (C06 assessed baseline, unclean `main`, 2026-10-25):** the
  race condition was named and explained, but no load/concurrency
  measurement existed anywhere in the repository — only sequential,
  single-threaded pytest coverage.
- **Verify (reporting baseline — added at commit `593435b9...`, still
  present unchanged at current HEAD `df96da24...`):**
  `tests/test_concurrency_measurement.py`
  now exists and is part of the suite. It runs 10 concurrent `confirm()`
  calls against the same resource and the same fully-overlapping time
  slot, each in its own thread with its own DB session, against one
  shared SQLite file — the exact scenario `intent-and-change.md`
  describes. Representative measured result: **4 of 10 concurrent
  requests ended up CONFIRMED on the same slot**, empirically reproducing
  the predicted race. The test is `pytest.mark.xfail(strict=False)`,
  because a DB-level fix (uniqueness/exclusion constraint or
  `SELECT ... FOR UPDATE`-style locking) is explicitly out of scope for
  this project phase (ADR-01 "reconsider when").
- **Disposition:** VERIFIED FINDING → **ACCEPT** (the required change was
  the measurement itself, not a code fix to the overlap check — already
  done).
- **Closure evidence:** `pytest -v` at the reporting baseline →
  `23 passed, 1 xfailed`; `tests/test_concurrency_measurement.py` added at
  commit `593435b925f999066b9c05e94ce76dc68fbf0d48` ("feat: add admin
  reservation approvals and .gitignore", Jiri Hruby, 2026-10-04) and still
  present, unchanged by any later commit, at current HEAD
  `df96da241a71ca5f06087aa048a4a73980d4c405` (2026-10-26).

### F2 — unclean / unidentified assessed baseline

- **Claim:** documentation, code and tests at the time of review
  represented one single, reproducible, assessable version.
- **Expected:** a named commit/tag and a clean working tree (no modified
  `parking.db`, no untracked IDE metadata).
- **Observed (C06 assessed baseline, 2026-10-25):** `main` had a modified
  `parking.db` and an untracked `ParkAndGo.iml`; no commit/tag was named
  at review time.
- **Verify (reporting baseline):** a `.gitignore` excluding `*.db`,
  `*.iml`, `.idea/`, virtualenvs and bytecode caches was added and
  committed; `parking.db`/`ParkAndGo.iml` are no longer tracked; the three
  "Application commit / tag" placeholders earlier in this document are
  now filled in (`ae3bf4f5...` for C02, `377535ad...` for C03/C05), and
  `593435b9...` is the commit where the `.gitignore` itself landed.
  *(Verified against the real GitHub commit history on 2026-10-31: commit
  `593435b925f999066b9c05e94ce76dc68fbf0d48` -- "feat: add admin
  reservation approvals and .gitignore", Jiri Hruby, 2026-10-04 -- does
  add `.gitignore`, confirming the team's claim. Two small corrections to
  the team's own F2 reasoning, visible in the same commit history: (1)
  the tags were filled in by a separate, later commit,
  `e323e400be493771deae38f073b6563c82b1d4ff` ("Tags", 2026-10-19), not by
  `593435b9...` itself as the F2 reason text implies; (2) `.gitignore` was
  briefly removed and then restored on 2026-10-26 --
  `7ab8013ac5938bdaabfa657e319c0dc2ffcc2543` ("Delete .gitignore")
  immediately followed by `76958edfd56dd8890ba940f8fc5c7fb7577f5f08`
  ("Revert 'Delete .gitignore'"). Neither correction changes the
  disposition -- `.gitignore` and the commit/tag placeholders are
  genuinely present at the current HEAD -- but both are worth having
  right for the record.)*
- **Disposition:** the owning team's own re-assessment recorded this as
  **REJECTED**, with the reasoning "`.gitignore` is not missing, neither
  are tags, and the tree is already clean."
  **One note for the record, worth deciding deliberately rather than by
  default:** under the strict C06/C07 vocabulary, REJECTED usually means
  *the candidate was never a real defect in the first place* — which
  wasn't true here (git status at assessment time genuinely was unclean,
  AutoRepo's observation was accurate). What actually happened is closer
  to **ACCEPTED — change required, now done**, with the commit above as
  closure evidence. The practical outcome is identical either way (fixed,
  closed, evidenced); only the taxonomy label differs, and the team should
  use whichever label matches how the instructor explained this exercise
  if that differs from the plain reading here.
- **Closure evidence:** commit `593435b925f999066b9c05e94ce76dc68fbf0d48`
  (`.gitignore` added, 2026-10-04) and commit
  `e323e400be493771deae38f073b6563c82b1d4ff` ("Tags", 2026-10-19, tags
  filled in this document); both confirmed present in the real GitHub
  commit history, as of current HEAD
  `df96da241a71ca5f06087aa048a4a73980d4c405` (2026-10-26). *(Verification
  performed: checked directly against the GitHub commit history the team
  shared on 2026-10-31 -- no longer only a team-reported reference.)*

### F3 — stale consistency-check document

- **Claim:** `docs/ParkAndGo_consistency_checks.md` accurately describes
  the current implementation.
- **Expected:** the table matches current code and the C05 documentation.
- **Observed (C06 assessed baseline):** row 2 still named the retired
  private helper `_has_overlapping_confirmed()`, and row 5 claimed Prolong
  Reservation was missing from the use-case diagram without pointing at
  `ParkAndGo_consistency_checks_ult.md`, which had already fixed that
  exact diagram.
- **Verify (reporting baseline):** `docs/ParkAndGo_consistency_checks.md`
  rows 2 and 5 are now corrected in place (both marked
  `[updated 2026-10-25]`), row 2 names `availability.has_overlap()` and
  cross-references the C05 extraction, row 5 points to
  `ParkAndGo_consistency_checks_ult.md` as the resolved "after" version —
  confirmed directly against the copy of this file in the project as of
  2026-10-31.
- **Disposition:** VERIFIED FINDING → **ACCEPTED — change required, now
  done**.
- **Closure evidence:** `docs/ParkAndGo_consistency_checks.md`, rows 2 and
  5, present at the reporting baseline; no code change was needed, since
  `availability.py` and the Prolong diagram were already correct — only
  the consistency-check document had fallen behind them.

### Housekeeping action taken alongside this review (not a C06 finding, but C07-relevant)

While re-verifying F1–F3 against the current repository state, several
**stale, pre-C02-fix duplicate documents** were found sitting at the root
of this project's knowledge base (`evidence-and-evolution.md`,
`ParkAndGo_consistency_checks.md`, `architecture-and-decisions.md`,
`parking_reservation_specification.md`,
`ParkAndGo_consistency_checks_ult.md`,
`approval_workflow_impact_analysis.md`, `intent-and-change.md` — all dated
2026-10-11, before the `docs/` folder existed in this project). These were
superseded duplicates of the real, current files under `docs/`, and one of
them (the stale root `evidence-and-evolution.md`) still carried the
*original*, pre-fix C06 owner disposition (ACCEPTED instead of the team's
own later REJECTED for F2, and no commit hashes at all) — exactly the kind
of documentation-drift risk recorded as **R-02** in the Risk Register
below. All seven stale duplicates were deleted from the project on
2026-10-31 so that `docs/` is the single, unambiguous source of truth
going forward.

---

# C07/C08 Risk Register

Built from the current C06/C07 findings above, the remaining open items
already tracked throughout this document (ADR-01's accepted gaps, the
C03/C05 "remaining design risk" notes), and direct inspection of the
project state on 2026-10-31. At least one risk per the required
categories (Technical/Quality, Release/Operation, People/Resources,
Security/Privacy, Schedule/Integration) is included, per the C07/C08
assignment's minimum of 4 risks across at least 3 categories.

### R-01

- **Risk statement:** The overlap check (`availability.has_overlap()`) is
  a plain application-level read-then-write with no DB-level transaction
  isolation or uniqueness constraint → under truly concurrent `confirm()`
  / `approve()` calls on the same resource and slot, more than one can
  read "no overlap" before either commits → BR-02 (no two overlapping
  CONFIRMED reservations) is violated under real concurrent load, not
  just in theory.
- **Category:** Technical / Quality
- **Initial risk:** L = 3 (High) — not a hypothetical: directly reproduced
  by `tests/test_concurrency_measurement.py` (4/10 double-booked in a
  representative run). I = 3 (High) — breaks the system's central
  business invariant (BR-02). **Priority: HIGH (9)**.
- **Response strategy:** ACCEPT for this project phase, with monitoring —
  not MITIGATE, because the only real fix (a DB-level uniqueness/exclusion
  constraint or stricter transaction isolation) was explicitly agreed to
  be out of scope for this phase (see ADR-01 "reconsider when" in
  `architecture-and-decisions.md`).
- **Treatment, owner, evidence:** `tests/test_concurrency_measurement.py`
  added as a permanent, re-runnable measurement (not a one-off number in
  a report); owner: whole team; no code fix planned this phase.
- **Expected / actual residual:** Expected: unchanged at L=3/I=3 (HIGH) —
  accepting a risk does not reduce it, it only makes it visible and
  monitored. Actual: **confirmed HIGH, accepted** — the measurement is
  itself the evidence, not an estimate.
- **Acceptance & trigger:** Accepted by the team for the current course
  scope; **trigger to revisit:** the ADR-01 "reconsider when" condition
  (sustained real concurrent load beyond a single-process course demo, or
  a decision to deploy beyond the classroom).

### R-02

- **Risk statement:** The project's knowledge base held duplicate copies
  of several core documents (including `evidence-and-evolution.md` itself)
  at two different paths with diverging content → a future edit applied
  to the wrong copy → a reviewer or the instructor is shown stale evidence
  (this already happened once: the root-level duplicate still had the
  pre-fix C06 disposition and no commit hashes).
- **Category:** Release / Operation
- **Initial risk:** L = 2 (Medium) — not hypothetical, it had already
  occurred once by the time this was found. I = 2 (Medium) — confusing and
  reputationally costly during a review, but recoverable. **Priority:
  MEDIUM (4)**.
- **Response strategy:** MITIGATE.
- **Treatment, owner, evidence:** all seven stale root-level duplicates
  deleted on 2026-10-31 (see Housekeeping action above); `docs/` is now
  the single source of truth.
- **Expected / actual residual:** Expected: L=1/I=1 (LOW) once the
  duplicates are gone and the team commits to always editing under
  `docs/`. Actual: **NOT VERIFIED** — the duplicates are deleted, but no
  second person has yet confirmed the team's actual git repository (not
  just this project's knowledge base) has no equivalent duplication.
- **Acceptance & trigger:** owner: whole team; **trigger:** any future
  upload/sync of project files should diff against what's already in
  `docs/` before adding new copies.

### R-03

- **Risk statement:** The 23-passed/1-xfailed test suite and the live
  `/ui/` demo have, as far as this record shows, only been confirmed
  running from one development environment → if that is a single team
  member and they are unavailable before the Technical Design Review, no
  one else can reproduce the evidence live.
- **Category:** People / Resources
- **Initial risk:** L = 2 (Medium) — a realistic, common course-project
  failure mode, no specific signal yet that it will happen. I = 3 (High)
  — the defence format (Part A) explicitly expects a runnable
  demonstration, not just slides. **Priority: HIGH (6)**.
- **Response strategy:** MITIGATE.
- **Treatment, owner, evidence:** a clean checkout + `pip install -r
  requirements.txt` + `python -m pytest -v` + `uvicorn src.main:app
  --reload` on a second machine before the defence.
  *(Partial mitigating signal found 2026-10-31: the real GitHub commit
  history shows commits authored/committed under at least three distinct
  identities -- "Jiri Hruby", GitHub user "Dr00gy", and "SIM0390" -- so
  the team is not literally a single contributor.)*
  **Done 2026-10-31:** a fresh `git clone` on a second machine (a
  notebook) was pulled and run independently -- result: `23 passed,
  1 xfailed`, matching the reporting baseline exactly, and the `/ui/`
  page and its functionality work normally on that machine too. This
  closes the narrow technical claim (the build and test suite are
  reproducible from a clean checkout on a machine other than the main
  development one). **Still open:** this run was performed by the same
  person who did the earlier work, on a second machine -- not yet by a
  *different team member*. The "unavailable team member" scenario the
  risk statement describes is therefore only partially addressed; a true
  second-person run is still worth doing before the live defence if
  another team member is available to do it, but the build/test
  reproducibility itself is no longer in doubt.
- **Expected / actual residual:** Expected: L=1/I=2 (LOW) once reproduced
  on a second environment. **Actual: L=1/I=2 (LOW), VERIFIED for build/
  test reproducibility** (clean checkout → `23 passed, 1 xfailed` → `/ui/`
  works, confirmed 2026-10-31 on a second machine). The narrower
  "different team member" residual stays **NOT VERIFIED**.
- **Acceptance & trigger:** **trigger:** if a different team member's run
  fails where this one succeeded, treat it as an environment-specific
  Issue, not a repeat of this risk.

### R-04

- **Risk statement:** `jmena_hesla.txt` stores the seeded admin and a demo
  user's real login credentials in plain text (`admin@parkandgo.test` /
  `admin12345`; a personal-looking test email and password) inside the
  project's shared knowledge base → if this project or repository is
  shared more broadly than intended, those credentials (and the habit of
  reusing a real-looking personal email for a throwaway test account) are
  exposed.
- **Category:** Security / Privacy
- **Initial risk:** L = 2 (Medium) — depends entirely on who else can see
  this project/repo, no evidence either way. I = 2 (Medium) — these are
  demo-only credentials for a course project with no real user data
  behind them, but the pattern (plaintext credentials file, a real-looking
  personal email used for a "test" account) is worth not normalizing.
  **Priority: MEDIUM (4)**.
- **Response strategy:** ACCEPT for the admin demo account specifically
  (README already documents `admin@parkandgo.test` / `admin12345` openly,
  by design, so a grader can log in) — MITIGATE for the second, more
  personal-looking test credential by not reusing a real email pattern
  for throwaway accounts going forward.
- **Treatment, owner, evidence:** no code change needed (the architecture
  decision to keep authorization a simple seeded flag is already recorded
  and accepted — C03 driver #3/RBAC, still open by design); recommend the
  team stop adding personal-looking emails to `jmena_hesla.txt` for future
  test accounts. Owner: whole team, ongoing practice, no fixed due date.
- **Expected / actual residual:** Expected: L=1/I=2 (LOW) if the project's
  sharing scope stays limited to the course. Actual: **NOT VERIFIED** —
  sharing scope of this Project was not something this session could
  check.
- **Acceptance & trigger:** accepted by the team for the admin demo
  account; **trigger:** before sharing this project or repository outside
  the course (e.g. in a portfolio), rotate/remove real-looking personal
  credentials from `jmena_hesla.txt`.

### R-05

- **Risk statement:** Several items are already explicitly recorded as
  "deliberately open" (a real scheduler for expiration, DB-level
  concurrency locking, capping the approval deadline to the reservation
  start, notifications on REJECTED/EXPIRED, admin cancelling other users'
  reservations, RBAC beyond a single `is_admin` flag) — but none of them
  currently has an owner or a target date, so there is nothing to show as
  planned CP2 preparation if asked.
- **Category:** Schedule / Integration
- **Initial risk:** L = 3 (High) — this will almost certainly come up as a
  direct question in the Engineering Review & Defence (Part A, criterion
  4). I = 2 (Medium) — it costs defence points and planning credibility,
  it does not break anything already working. **Priority: HIGH (6)**.
- **Response strategy:** MITIGATE.
- **Treatment, owner, evidence:** pick at most one or two of the six open
  items as explicit CP2 candidates with an owner and a date (see Next
  Action Plan, P4, in the status report); leave the rest explicitly
  recorded as accepted/open rather than silently implied as "already
  handled." **Owner/date: TODO — the team must decide which item(s), if
  any, actually become CP2 scope.**
- **Expected / actual residual:** Expected: L=2/I=2 (MEDIUM) once at least
  one item has a named owner and date. Actual: **NOT VERIFIED** — no CP2
  scoping decision has been made yet as of this record.
- **Acceptance & trigger:** **trigger:** the next team planning
  conversation before CP2, specifically to assign owner(s)/date(s) or
  explicitly re-accept the full list as "no CP2 work planned, risk
  accepted as-is."

### Open issues (not risks — already happened)

- The three "Application commit / tag" placeholders in the C02/C03/C05
  sections above are now filled; no open issue remains there.
- R-03's "second clean environment run" has not yet been attempted, so it
  is tracked as a risk (uncertain future event), not yet an issue.

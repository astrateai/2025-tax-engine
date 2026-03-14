# Reviewer Workflow States (V1)

## Purpose
Define explicit human-review checkpoints so no tax return is treated as complete without CPA review.

## States
1) `drafted`
- Kevin generated forms + reviewer packet.
- Not reviewed by human yet.

2) `reviewer_assigned`
- Named reviewer has ownership.
- Due date for review is set.

3) `review_rejected`
- Reviewer found issues.
- Must include rejection reasons and required fixes.

4) `revision_in_progress`
- Kevin is applying reviewer-requested changes.

5) `review_approved`
- Reviewer approved for internal readiness.
- Still not submitted/e-filed.

## Required Fields per case
- `caseId`
- `scenarioOrClient`
- `status`
- `reviewer` (required in reviewer_assigned/review_approved/review_rejected)
- `updatedAt`
- `notes`
- `blockingIssues` (array)
- `notSubmittedConfirmed` (bool, must remain true)

## Hard Rules
- No transition to `review_approved` without named reviewer.
- `notSubmittedConfirmed` must always be true.
- If blockers exist, status cannot be `review_approved`.

## Transition Map
- drafted -> reviewer_assigned
- reviewer_assigned -> review_rejected | review_approved
- review_rejected -> revision_in_progress
- revision_in_progress -> reviewer_assigned

#!/usr/bin/env bash
# One-time GitHub setup: labels, sprint milestones, project board, branch protection.
# Prerequisites: `gh auth login` and `gh auth refresh -s project`; repo already pushed.
# Usage: ./scripts/setup_github.sh <owner>/<repo>
set -euo pipefail

REPO="${1:?usage: $0 <owner>/<repo>}"
OWNER="${REPO%%/*}"

echo "==> Labels"
label() { gh label create "$1" --repo "$REPO" --color "$2" --description "$3" --force; }
label "type:epic"  "5319e7" "Large body of work spanning several stories"
label "type:story" "0e8a16" "User story"
label "type:bug"   "d73a4a" "Something is broken"
label "type:chore" "c5def5" "Tooling, setup, maintenance"
label "security"   "b60205" "Security-relevant change"
label "eval"       "fbca04" "Has an evaluation metric / report"
for f in $(seq -w 1 17); do label "F$f" "bfdadc" "Feature F$f"; done

echo "==> Milestones (one per sprint)"
milestone() {
  gh api "repos/$REPO/milestones" -f title="$1" -f description="$2" -f due_on="$3" >/dev/null \
    || echo "   (milestone '$1' may already exist)"
}
milestone "Sprint 0: Setup"            "Accounts, repo, board, backlog, toolchain" "2026-11-08T23:59:59Z"
milestone "Sprint 1: Data Foundation"  "F01-F05: governed multi-modal data in Postgres, 3 envs" "2026-11-11T23:59:59Z"
milestone "Sprint 2: AI Core"          "F06-F12: evaluated RAG, agents, MCP, guardrails, HITL" "2026-11-15T23:59:59Z"
milestone "Sprint 3: Product & Release" "F13-F17 + RadarMart: API, UI, A2A, notifications, AKS proof, v1.0.0" "2026-11-19T23:59:59Z"

echo "==> Project board"
gh project create --owner "$OWNER" --title "Recall Radar" >/dev/null || echo "   (project may already exist)"
echo "   Add columns in the web UI: Backlog, Ready, In Progress, In Review, Done"

echo "==> Branch protection on main (PR required, CI must pass, no force-push)"
gh api -X PUT "repos/$REPO/branches/main/protection" --input - <<'JSON'
{
  "required_status_checks": { "strict": true, "contexts": ["quality", "secret-scan"] },
  "enforce_admins": true,
  "required_pull_request_reviews": { "required_approving_review_count": 0 },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON

echo "Done. Next: ./scripts/create_backlog.sh $REPO"

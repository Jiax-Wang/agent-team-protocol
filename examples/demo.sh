#!/usr/bin/env bash
# demo.sh — Full agent-team protocol walkthrough
# This script demonstrates the complete workflow using file-level coordination.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_TEAM="$SCRIPT_DIR/../agent-team.sh"

# Clean up any previous demo
rm -rf .agent-team

echo "============================================"
echo "  Agent Team Protocol — Live Demo"
echo "============================================"
echo ""

# ─── 1. Initialize team ──────────────────────────────────

echo ">>> Step 1: Initialize the team"
"$AGENT_TEAM" init demo-team
echo ""

# ─── 2. Add members ──────────────────────────────────────

echo ">>> Step 2: Add team members"
"$AGENT_TEAM" member add architect "Architecture design and planning"
"$AGENT_TEAM" member add implementer "Code implementation"
"$AGENT_TEAM" member add reviewer   "Code review and QA"
echo ""

# ─── 3. Add tasks ────────────────────────────────────────

echo ">>> Step 3: Create tasks"
"$AGENT_TEAM" task add "Design database schema" high
"$AGENT_TEAM" task add "Implement user API endpoints" high
"$AGENT_TEAM" task add "Add input validation middleware" medium
"$AGENT_TEAM" task add "Write integration tests" medium
"$AGENT_TEAM" task add "Update API documentation" low
echo ""

# ─── 4. Show status ──────────────────────────────────────

echo ">>> Step 4: Team status overview"
"$AGENT_TEAM" status
echo ""

echo ">>> Task list:"
"$AGENT_TEAM" task list
echo ""

# ─── 5. Architect claims and works ────────────────────────

echo ">>> Step 5: Architect claims task-001"
"$AGENT_TEAM" task claim task-001 architect
echo ""

echo ">>> Architect writes design artifact..."
mkdir -p .agent-team/artifacts/task-001
cat > .agent-team/artifacts/task-001/schema-design.md << 'DOC'
# Database Schema Design

## Tables
- users (id, email, password_hash, created_at)
- sessions (id, user_id, token, expires_at)
- roles (id, name)

## Indexes
- users.email (unique)
- sessions.token (unique)
- sessions.user_id (foreign key)
DOC
echo ""

echo ">>> Architect completes task-001"
"$AGENT_TEAM" task complete task-001 "Database schema designed: 3 tables with indexes. See artifacts/task-001/schema-design.md"
echo ""

# ─── 6. Inter-agent messaging ─────────────────────────────

echo ">>> Step 6: Architect messages implementer with design handoff"
"$AGENT_TEAM" msg architect implementer info \
  "Schema design is complete. Please review artifacts/task-001/schema-design.md before starting API implementation. Tables: users, sessions, roles. Use bcrypt for password hashing."
echo ""

echo ">>> Implementer's inbox:"
"$AGENT_TEAM" inbox implementer
echo ""

# ─── 7. Implementer claims task-002 ────────────────────────

echo ">>> Step 7: Implementer reads inbox, claims task-002"
"$AGENT_TEAM" task claim task-002 implementer
echo ""

echo ">>> Implementer works on API endpoints..."
mkdir -p .agent-team/artifacts/task-002
cat > .agent-team/artifacts/task-002/implementation-notes.md << 'DOC'
# User API Implementation

## Files Created
- src/routes/auth.ts — POST /login, POST /register
- src/middleware/auth.ts — JWT verification
- src/models/user.ts — User model with bcrypt

## Decisions
- JWT expiry: 24 hours
- Password min length: 8 chars
- Rate limiting: 5 attempts per minute per IP
DOC
echo ""

echo ">>> Implementer completes task-002"
"$AGENT_TEAM" task complete task-002 "API endpoints implemented. See artifacts/task-002/implementation-notes.md"
echo ""

# ─── 8. Implementer asks reviewer for help ────────────────

echo ">>> Step 8: Implementer requests code review from reviewer"
"$AGENT_TEAM" msg implementer reviewer request \
  "Please review the auth implementation. I'm concerned about the edge case where a user registers with an already-existing email. See task-002 artifact."
echo ""

echo ">>> Reviewer's inbox:"
"$AGENT_TEAM" inbox reviewer
echo ""

# ─── 9. Reviewer claims task-003 ──────────────────────────

echo ">>> Step 9: Reviewer claims task-003 (validation middleware)"
"$AGENT_TEAM" task claim task-003 reviewer
echo ""

echo ">>> Reviewer works and completes..."
mkdir -p .agent-team/artifacts/task-003
cat > .agent-team/artifacts/task-003/review-log.md << 'DOC'
# Task-003 Review Log
- Added email format validation
- Added password strength check
- Fixed duplicate email edge case in registration
- All tests passing
DOC
echo ""

echo ">>> Reviewer responds to implementer"
"$AGENT_TEAM" msg reviewer implementer response \
  "Reviewed. Found and fixed the duplicate email edge case. Added proper validation. See task-003 artifact for details."
echo ""

"$AGENT_TEAM" task complete task-003 "Input validation added. Fixed duplicate email edge case. See artifacts/task-003/review-log.md"
echo ""

# ─── 10. Final status ─────────────────────────────────────

echo ">>> Step 10: Final team status"
"$AGENT_TEAM" status
echo ""

echo ">>> All tasks:"
"$AGENT_TEAM" task list
echo ""

echo ">>> Team log:"
cat .agent-team/log/team.log
echo ""

echo "============================================"
echo "  Demo complete!"
echo "  .agent-team/ directory preserved for inspection."
echo "  Run: ls -R .agent-team/"
echo "============================================"

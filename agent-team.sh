#!/usr/bin/env bash
# agent-team.sh — File-level multi-agent coordination
# Protocol: reads/writes .agent-team/ directory
# Usage: agent-team <command> [args...]

set -euo pipefail

TEAM_ROOT=".agent-team"
MEMBERS_DIR="$TEAM_ROOT/members"
TASKS_DIR="$TEAM_ROOT/tasks"
INBOX_DIR="$TEAM_ROOT/inbox"
ARTIFACTS_DIR="$TEAM_ROOT/artifacts"
LOCKS_DIR="$TEAM_ROOT/locks"
LOG_DIR="$TEAM_ROOT/log"
TEAM_JSON="$TEAM_ROOT/team.json"

# ─── helpers ───────────────────────────────────────────────

die() { echo "ERROR: $*" >&2; exit 1; }
log_event() {
  local msg="$1"
  mkdir -p "$LOG_DIR"
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $msg" >> "$LOG_DIR/team.log"
}

ensure_init() {
  [ -f "$TEAM_JSON" ] || die "No .agent-team/ found. Run: agent-team init <name>"
}

# acquire_lock <name> [timeout_secs]
acquire_lock() {
  local name="$1" timeout="${2:-30}" waited=0
  mkdir -p "$LOCKS_DIR"
  while ! mkdir "$LOCKS_DIR/${name}" 2>/dev/null; do
    sleep 1; waited=$((waited + 1))
    [ $waited -ge $timeout ] && die "Lock timeout: $name"
  done
}

release_lock() { rmdir "$LOCKS_DIR/${1}" 2>/dev/null || true; }

# In-place JSON value update using sed (no jq dependency)
json_set() {
  local file="$1" key="$2" val="$3"
  # First try to replace quoted value, then null
  sed -i "s|\"${key}\": *\"[^\"]*\"|\"${key}\": \"${val}\"|" "$file" 2>/dev/null || true
  sed -i "s|\"${key}\": *null|\"${key}\": \"${val}\"|" "$file" 2>/dev/null || true
}

json_get() {
  local file="$1" key="$2"
  local raw
  raw=$(grep -o "\"${key}\": *\"[^\"]*\"" "$file" 2>/dev/null | head -1 | sed 's/.*: *"//;s/"//') || true
  if [ -z "$raw" ]; then
    raw=$(grep -o "\"${key}\": *null" "$file" 2>/dev/null | head -1 | sed 's/.*: *null/null/') || true
  fi
  [ -z "$raw" ] && raw=""
  echo "$raw"
}

# ─── init ──────────────────────────────────────────────────

cmd_init() {
  local name="${1:-my-team}"
  [ -d "$TEAM_ROOT" ] && die "$TEAM_ROOT already exists"
  local now
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  mkdir -p "$TASKS_DIR"/{pending,in-progress,completed,blocked}
  mkdir -p "$MEMBERS_DIR" "$INBOX_DIR" "$ARTIFACTS_DIR" "$LOCKS_DIR" "$LOG_DIR"

  cat > "$TEAM_JSON" << JSON
{
  "name": "${name}",
  "project": "",
  "created": "${now}",
  "settings": {
    "max_parallel_tasks": 3,
    "task_claim_timeout_minutes": 30
  }
}
JSON
  echo "OK: Team '$name' initialized at $TEAM_ROOT"
  log_event "team_init name=$name"
}

# ─── members ───────────────────────────────────────────────

cmd_member_add() {
  ensure_init
  local id="$1" role="${2:-worker}"
  local member_file="$MEMBERS_DIR/${id}.json"
  [ -f "$member_file" ] && die "Member '$id' already exists"
  mkdir -p "$MEMBERS_DIR" "$INBOX_DIR"
  cat > "$member_file" << JSON
{
  "id": "${id}",
  "role": "${role}",
  "status": "idle"
}
JSON
  touch "$INBOX_DIR/${id}.md"
  echo "OK: Member '$id' ($role) added"
  log_event "member_add id=$id role=$role"
}

cmd_member_list() {
  ensure_init
  echo "Team members:"
  for f in "$MEMBERS_DIR"/*.json; do
    [ -f "$f" ] || continue
    local id role
    id=$(json_get "$f" "id")
    role=$(json_get "$f" "role")
    echo "  $id ($role)"
  done
}

# ─── tasks ─────────────────────────────────────────────────

cmd_task_add() {
  ensure_init
  local title="$1" priority="${2:-medium}"
  local n
  n=$(find "$TASKS_DIR/pending" "$TASKS_DIR/in-progress" -name '*.json' 2>/dev/null | wc -l)
  n=$((n + 1))
  local tid
  tid=$(printf "task-%03d" "$n")
  local now
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  cat > "$TASKS_DIR/pending/${tid}.json" << JSON
{
  "id": "${tid}",
  "title": "${title}",
  "description": "",
  "priority": "${priority}",
  "dependencies": [],
  "assigned_to": null,
  "parent_task": null,
  "tags": [],
  "created_at": "${now}",
  "claimed_at": null,
  "completed_at": null,
  "artifact_path": null,
  "result_summary": "",
  "block_reason": ""
}
JSON
  echo "OK: $tid added: $title"
  log_event "task_add id=$tid title=$title priority=$priority"
}

cmd_task_list() {
  ensure_init
  local status="${1:-all}"
  local dirs=""
  case "$status" in
    all)       dirs="$TASKS_DIR/pending $TASKS_DIR/in-progress $TASKS_DIR/completed $TASKS_DIR/blocked" ;;
    pending)   dirs="$TASKS_DIR/pending" ;;
    active)    dirs="$TASKS_DIR/in-progress" ;;
    done)      dirs="$TASKS_DIR/completed" ;;
    blocked)   dirs="$TASKS_DIR/blocked" ;;
    *)         die "Unknown status: $status (use: all, pending, active, done, blocked)" ;;
  esac

  local found=0
  for d in $dirs; do
    shopt -s nullglob
    for f in "$d"/*.json; do
      [ -f "$f" ] || continue
      found=1
      local id title priority assignee
      id=$(json_get "$f" "id")
      title=$(json_get "$f" "title")
      priority=$(json_get "$f" "priority")
      assignee=$(json_get "$f" "assigned_to")
      local stat_dir
      stat_dir=$(basename "$(dirname "$f")")
      printf "  [%s] %-12s %-8s %s" "$stat_dir" "$id" "$priority" "$title"
      [ "$assignee" != "" ] && [ "$assignee" != "null" ] && printf " (assigned: %s)" "$assignee"
      echo
    done
  done
  [ $found -eq 0 ] && echo "  (no tasks)"
  return 0
}

cmd_task_show() {
  ensure_init
  local tid="$1"
  local f
  f=$(find "$TASKS_DIR" -name "${tid}.json" 2>/dev/null | head -1)
  [ -z "$f" ] && die "Task not found: $tid"
  echo "=== $tid ==="
  cat "$f"
}

# Claim a task (atomic mv pending -> in-progress)
cmd_task_claim() {
  ensure_init
  local tid="$1" agent="${2:-unknown}"
  local src="$TASKS_DIR/pending/${tid}.json"
  [ -f "$src" ] || die "Task not in pending: $tid"

  local dst="$TASKS_DIR/in-progress/${tid}.json"
  local now
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  # Update fields before moving (we own the file in pending)
  json_set "$src" "assigned_to" "$agent"
  json_set "$src" "claimed_at" "$now"

  mv "$src" "$dst" || die "Failed to claim $tid (another agent may have claimed it)"
  echo "OK: $agent claimed $tid"
  log_event "task_claim id=$tid agent=$agent"
}

# Complete a task (atomic mv in-progress -> completed)
cmd_task_complete() {
  ensure_init
  local tid="$1" summary="${2:-}"
  local src="$TASKS_DIR/in-progress/${tid}.json"
  [ -f "$src" ] || die "Task not in-progress: $tid"

  local dst="$TASKS_DIR/completed/${tid}.json"
  local now
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  json_set "$src" "completed_at" "$now"
  [ -n "$summary" ] && json_set "$src" "result_summary" "$summary"

  mv "$src" "$dst" || die "Failed to complete $tid"
  echo "OK: $tid completed"
  log_event "task_complete id=$tid summary=$summary"
}

# Block a task (atomic mv in-progress -> blocked)
cmd_task_block() {
  ensure_init
  local tid="$1" reason="${2:-no reason given}"
  local src="$TASKS_DIR/in-progress/${tid}.json"
  [ -f "$src" ] || die "Task not in-progress: $tid"

  local dst="$TASKS_DIR/blocked/${tid}.json"
  json_set "$src" "block_reason" "$reason"
  mv "$src" "$dst" || die "Failed to block $tid"
  echo "OK: $tid blocked: $reason"
  log_event "task_block id=$tid reason=$reason"
}

# Unblock a task
cmd_task_unblock() {
  ensure_init
  local tid="$1"
  local src="$TASKS_DIR/blocked/${tid}.json"
  [ -f "$src" ] || die "Task not blocked: $tid"

  json_set "$src" "block_reason" ""
  json_set "$src" "assigned_to" "null"
  json_set "$src" "claimed_at" "null"
  mv "$src" "$TASKS_DIR/pending/${tid}.json" || die "Failed to unblock $tid"
  echo "OK: $tid unblocked and returned to pending"
  log_event "task_unblock id=$tid"
}

# ─── messages ──────────────────────────────────────────────

cmd_msg() {
  ensure_init
  local from="$1" to="$2" type="${3:-info}"; shift 3
  local text="$*"
  [ -z "$text" ] && die "Message text required"
  local now
  now=$(date -u +%Y-%m-%dT%H:%M:%SZ)

  mkdir -p "$INBOX_DIR"
  local target="$INBOX_DIR/${to}.md"
  cat >> "$target" << MSG
---
from: ${from}
to: ${to}
timestamp: ${now}
type: ${type}
---

${text}
---
MSG
  echo "OK: Message sent from $from to $to"
  log_event "msg from=$from to=$to type=$type"
}

cmd_inbox() {
  ensure_init
  local agent="$1"
  local f="$INBOX_DIR/${agent}.md"
  if [ -f "$f" ] && [ -s "$f" ]; then
    echo "=== Inbox: $agent ==="
    cat "$f"
  else
    echo "Inbox for $agent is empty"
  fi
}

cmd_inbox_clear() {
  ensure_init
  local agent="$1"
  local f="$INBOX_DIR/${agent}.md"
  echo "" > "$f"
  echo "OK: Inbox cleared for $agent"
}

# ─── status ────────────────────────────────────────────────

cmd_status() {
  ensure_init
  local name now
  name=$(json_get "$TEAM_JSON" "name")
  echo "Team: $name"
  echo "============================"

  for status in pending in-progress completed blocked; do
    local count
    count=$(find "$TASKS_DIR/$status" -name '*.json' 2>/dev/null | wc -l)
    printf "  %-12s: %d\n" "$status" "$count"
  done

  echo
  echo "Members:"
  for f in "$MEMBERS_DIR"/*.json; do
    [ -f "$f" ] || continue
    local mid role task_count
    mid=$(json_get "$f" "id")
    role=$(json_get "$f" "role")
    task_count=$(find "$TASKS_DIR/in-progress" -name '*.json' -exec grep -l "\"assigned_to\": \"${mid}\"" {} \; 2>/dev/null | wc -l)
    printf "  %-15s %-30s active tasks: %d\n" "$mid" "($role)" "$task_count"
  done
}

# ─── spawn ─────────────────────────────────────────────────

cmd_spawn() {
  ensure_init
  local agent="$1"
  local member_file="$MEMBERS_DIR/${agent}.json"
  [ -f "$member_file" ] || die "Agent '$agent' not in team. Run: agent-team member add $agent <role>"
  local role
  role=$(json_get "$member_file" "role")
  local team_name
  team_name=$(json_get "$TEAM_JSON" "name")

  cat << PROMPT
You are agent "${agent}" in team "${team_name}".
Your role: ${role}

## FILE PROTOCOL — .agent-team/

All coordination happens via the filesystem. You MUST follow this protocol:

### Work Loop
1. Check your inbox: read .agent-team/inbox/${agent}.md
2. Scan tasks: ls .agent-team/tasks/pending/
3. Claim one task: mv .agent-team/tasks/pending/<task>.json .agent-team/tasks/in-progress/
   - Then update "assigned_to" and "claimed_at" fields in the file
4. Execute the task — write deliverables to .agent-team/artifacts/<task-id>/
5. Complete: update "completed_at" and "result_summary", then
   mv .agent-team/tasks/in-progress/<task>.json .agent-team/tasks/completed/
6. If you need something from another agent, APPEND to .agent-team/inbox/<their-name>.md
   Format:
   ---
   from: ${agent}
   to: <recipient>
   timestamp: <ISO8601>
   type: request|response|info|alert
   ---
   <message>
   ---
7. Repeat until no claimable tasks remain

### Rules
- Always CLAIM before working (atomic mv prevents race conditions)
- Write result_summary in the task JSON when done
- Check your inbox before claiming each new task
- If blocked by a dependency, mv task to tasks/blocked/ and message the dependency holder
- If blocked on external info, message the "user" agent

### Available Commands (use Bash tool)
- agent-team task list pending    — see available tasks
- agent-team task claim <id> ${agent}  — claim a task (or use raw mv)
- agent-team task complete <id> "summary"  — complete a task
- agent-team task block <id> "reason"  — block a task
- agent-team msg ${agent} <to> request "<text>"  — send message
- agent-team inbox ${agent}  — check your inbox
- agent-team status  — team overview

Begin by checking your inbox and listing pending tasks.
PROMPT
}

# ─── disband ───────────────────────────────────────────────

cmd_disband() {
  ensure_init
  echo "WARNING: This will delete .agent-team/ and all state."
  echo -n "Type 'yes' to confirm: "
  read -r confirm
  [ "$confirm" = "yes" ] || { echo "Aborted."; exit 0; }
  rm -rf "$TEAM_ROOT"
  echo "OK: Team disbanded"
}

# ─── main ──────────────────────────────────────────────────

print_usage() {
  cat << EOF
agent-team — File-level multi-agent coordination

USAGE:
  agent-team init <name>                    Create new team
  agent-team member add <id> <role>         Add member
  agent-team member list                    List members
  agent-team task add <title> [priority]    Create task
  agent-team task list [status]             List tasks (all/pending/active/done/blocked)
  agent-team task show <tid>                Show task details
  agent-team task claim <tid> <agent>       Claim task (agent action)
  agent-team task complete <tid> [summary]  Complete task (agent action)
  agent-team task block <tid> <reason>      Block task (agent action)
  agent-team task unblock <tid>             Unblock task
  agent-team msg <from> <to> <type> <text>  Send message
  agent-team inbox <agent>                  Read agent inbox
  agent-team inbox-clear <agent>            Clear agent inbox
  agent-team spawn <agent-id>               Generate agent prompt
  agent-team status                         Team overview
  agent-team disband                        Delete .agent-team/

PROTOCOL: $(dirname "$0")/PROTOCOL.md
EOF
}

main() {
  local cmd="${1:-}"
  [ -z "$cmd" ] && { print_usage; exit 0; }
  shift || true

  case "$cmd" in
    init)            cmd_init "$@" ;;
    member)          sub="${1:-}"; shift || true
                     case "$sub" in
                       add)    cmd_member_add "$@" ;;
                       list)   cmd_member_list ;;
                       *)      die "Unknown member subcommand: $sub" ;;
                     esac ;;
    task)            sub="${1:-}"; shift || true
                     case "$sub" in
                       add)      cmd_task_add "$@" ;;
                       list)     cmd_task_list "$@" ;;
                       show)     cmd_task_show "$@" ;;
                       claim)    cmd_task_claim "$@" ;;
                       complete) cmd_task_complete "$@" ;;
                       block)    cmd_task_block "$@" ;;
                       unblock)  cmd_task_unblock "$@" ;;
                       *)        die "Unknown task subcommand: $sub" ;;
                     esac ;;
    msg)             cmd_msg "$@" ;;
    inbox)           cmd_inbox "$@" ;;
    inbox-clear)     cmd_inbox_clear "$@" ;;
    spawn)           cmd_spawn "$@" ;;
    status)          cmd_status ;;
    disband)         cmd_disband ;;
    help|--help|-h)  print_usage ;;
    *)               die "Unknown command: $cmd. Try: agent-team help" ;;
  esac
}

main "$@"

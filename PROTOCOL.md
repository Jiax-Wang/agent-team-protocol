# Agent Team Protocol v1.0

## 概述

Agent Team Protocol 是一个**文件系统级的多代理协调协议**。它使用文件系统原语（原子重命名、目录创建、追加写入）实现代理之间的任务分配、消息传递和状态同步，无需中心化 API 或实验性功能。

### 设计原则

- **零依赖** — 仅需文件系统和 bash
- **原子操作** — 利用 `mv` 的原子性实现无锁任务状态转换
- **可调试** — 所有状态以文件形式可见，`cat`/`ls` 即可排查
- **跨会话持久化** — 关闭终端后状态保留，下次可继续
- **模型无关** — 不依赖特定 LLM 模型或 API

---

## 目录结构

```
.agent-team/
├── team.json                # 团队配置
├── tasks/
│   ├── pending/             # 待认领任务
│   ├── in-progress/         # 执行中任务
│   ├── completed/           # 已完成任务
│   └── blocked/             # 被阻塞任务
├── inbox/
│   └── <agent-name>.md      # 每个代理的收件箱（追加写入）
├── artifacts/               # 共享产出物
├── locks/                   # 临时锁目录
└── log/
    └── team.log             # 团队活动日志（追加写入）
```

### 状态转换图

```
pending ──(claim)──> in-progress ──(complete)──> completed
                         │
                         └──(block)──> blocked ──(unblock)──> pending
```

所有状态转换通过**原子 `mv`** 完成，无需锁。

---

## 文件格式

### team.json

```json
{
  "name": "my-project-team",
  "project": "project-name",
  "created": "2026-05-19T10:00:00Z",
  "members": [
    {
      "id": "architect",
      "role": "Architecture design and technical planning",
      "status": "idle"
    },
    {
      "id": "implementer",
      "role": "Code implementation",
      "status": "idle"
    },
    {
      "id": "reviewer",
      "role": "Code review and quality assurance",
      "status": "idle"
    }
  ],
  "settings": {
    "max_parallel_tasks": 3,
    "task_claim_timeout_minutes": 30,
    "coordination_mode": "file"
  }
}
```

成员状态：`idle` | `working` | `waiting` | `done`

### 任务文件 `tasks/<status>/<task-id>.json`

```json
{
  "id": "task-001",
  "title": "Implement user authentication API",
  "description": "Add JWT-based authentication endpoints: POST /login, POST /register, GET /me",
  "priority": "high",
  "dependencies": [],
  "assigned_to": null,
  "parent_task": null,
  "subtasks": [],
  "tags": ["api", "auth"],
  "created_at": "2026-05-19T10:00:00Z",
  "claimed_at": null,
  "completed_at": null,
  "artifact_path": null,
  "result_summary": "",
  "block_reason": ""
}
```

### 收件箱消息格式

每个代理的收件箱是追加写入的 markdown 文件：

```markdown
---
from: architect
to: implementer
timestamp: 2026-05-19T10:00:00Z
type: request
ref: task-002
---

The API should use bcrypt for password hashing and return
JWT tokens with 24h expiry. See artifacts/auth-design.md for details.
---
```

消息类型：`request` | `response` | `info` | `alert` | `handoff`

---

## 核心操作

### 1. 认领任务（原子操作，无需锁）

```bash
# 代理认领 task-001
mv .agent-team/tasks/pending/task-001.json \
   .agent-team/tasks/in-progress/task-001.json

# 更新任务文件中的 assigned_to 和 claimed_at
# （mv 后原地修改，此文件已归该代理独有，无并发问题）
```

### 2. 完成任务

```bash
# 更新 completed_at 和 result_summary
# 然后移动
mv .agent-team/tasks/in-progress/task-001.json \
   .agent-team/tasks/completed/task-001.json
```

### 3. 阻塞任务

```bash
# 写入 block_reason，然后移动
mv .agent-team/tasks/in-progress/task-001.json \
   .agent-team/tasks/blocked/task-001.json
```

### 4. 发送消息

消息通过**追加写入**目标代理的收件箱文件。追加写入在 POSIX 系统上对于小于 PIPE_BUF（通常 4096 字节）的写入是原子的。

```bash
cat >> .agent-team/inbox/implementer.md << 'MSG'
---
from: architect
to: implementer
timestamp: 2026-05-19T10:00:00Z
type: request
ref: task-003
---

Please add rate limiting to the login endpoint.
MSG
```

### 5. 文件锁（仅用于 team.json 更新）

对于需要读-改-写 `team.json` 的罕见操作，使用 `mkdir` 原子性：

```bash
acquire_lock() {
  local name="$1"
  local timeout="${2:-30}"
  local waited=0
  while ! mkdir ".agent-team/locks/${name}" 2>/dev/null; do
    sleep 1
    waited=$((waited + 1))
    [ $waited -ge $timeout ] && return 1
  done
  return 0
}

release_lock() {
  rmdir ".agent-team/locks/${1}" 2>/dev/null
}
```

`mkdir` 是原子操作 — 只有一个进程能成功创建同一个目录。

---

## 代理工作循环

每个代理遵循以下循环：

```
LOOP:
  1. 检查自己的 inbox，处理未读消息
  2. 扫描 tasks/pending/ 中依赖已满足的任务
  3. 按优先级排序，选择一个任务
  4. 原子认领：mv pending -> in-progress
  5. 执行任务
  6. 将产出写入 artifacts/<task-id>/
  7. 更新任务文件，mv in-progress -> completed
  8. 如需要，向相关代理发送消息
  9. 检查是否有更多可认领的任务
     - 有：回到步骤 2
     - 无：更新 team.json 中自身状态为 done
```

### 认领规则

1. 只能认领 `dependencies` 全部在 `completed/` 中的任务
2. 优先认领 `priority` 为 `high` 的任务
3. 同优先级按 `created_at` 时间排序
4. 每个代理同时最多持有 `max_parallel_tasks` 个任务（默认 1）

---

## 代理系统提示词

每个代理在启动时接收以下核心指令：

```
You are agent "<agent-id>" in team "<team-name>".
Your role: <role-description>

You work via FILE PROTOCOL at .agent-team/:

TASKS:
  - Claim: read tasks/pending/, pick one, mv to tasks/in-progress/
  - Work: execute the task
  - Complete: update task JSON, mv to tasks/completed/

MESSAGES:
  - Check inbox/<your-name>.md for new messages
  - Send to others by appending to inbox/<their-name>.md
  - Format: ---\nfrom: <you>\nto: <them>\n...

ARTIFACTS:
  - Write deliverables to artifacts/<task-id>/

RULES:
  - Always claim before starting work (atomic mv)
  - Report results in task JSON result_summary field
  - Check inbox before claiming each new task
  - If blocked, mv task to tasks/blocked/ and message the dependency holder
```

---

## 协调器职责

`agent-team.sh` 协调器负责：

1. **初始化** — 创建 `.agent-team/` 目录结构
2. **成员管理** — 注册/移除代理
3. **任务管理** — 添加、列出、查看任务
4. **状态监控** — 显示团队整体进度
5. **生成代理提示词** — 为每个代理生成符合协议的启动提示词
6. **冲突检测** — 检测任务是否在 in-progress 中超时
7. **清理** — 归档或删除 `.agent-team/`

协调器**不执行任务**，只维护基础设施。任务的执行由代理完成。

---

## 并发安全保证

| 操作 | 机制 | 安全性 |
|------|------|--------|
| 任务认领 | `mv` 原子重命名 | 完全安全，无需锁 |
| 任务完成 | `mv` 原子重命名 | 完全安全 |
| 发送消息 | 追加写入独立文件 | 安全（单条消息 < 4096 字节） |
| 修改 team.json | `mkdir` 锁 | 安全 |
| 写入 artifact | 独立子目录 | 安全（无共享写入） |

---

## 与 Agent Teams API 对比

| 维度 | Agent Teams API | File Protocol |
|------|----------------|---------------|
| 依赖 | Claude Opus + 实验性开关 | 文件系统 + bash |
| 代理间通信 | 实时消息 | 追加文件 + 轮询 |
| 状态同步 | API 调用 | 文件读取 |
| 持久化 | 会话内 | 跨会话持久 |
| 可调试性 | 黑盒 | `cat`/`ls` 即可 |
| 成本 | ~3.5x 基准 | 取决模型 |
| 跨模型 | 仅 Opus | 任何模型 |

---

## 扩展点

- **Git 集成** — `.agent-team/` 可 git commit，团队间共享状态
- **Webhook 通知** — 可添加 `post-transition-hook` 触发外部通知
- **时间线回放** — `log/team.log` 记录所有事件，可回放分析
- **自定义代理角色** — 通过 `team.json` 动态定义新角色
- **嵌套团队** — team 本身可以是另一个 team 的子任务

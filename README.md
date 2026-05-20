# Agent Team Protocol

文件系统级多代理协调协议 — 纯 bash，无依赖，跨模型，跨平台。

## 核心理念

每个代理通过读写 `.agent-team/` 目录协作：

```
.agent-team/
├── team.json                # 团队配置
├── members/
│   └── <agent>.json         # 每个成员一个文件
├── tasks/
│   ├── pending/             # 待认领 (原子 mv → in-progress)
│   ├── in-progress/         # 执行中
│   ├── completed/           # 已完成
│   └── blocked/             # 被阻塞
├── inbox/
│   └── <agent>.md           # 追加式消息
├── artifacts/               # 共享产出
└── log/team.log             # 事件日志
```

**原子操作保证并发安全**：任务认领通过 `mv pending → in-progress` 实现无锁并发。

## 快速开始

```bash
# 安装
curl -fsSL https://raw.githubusercontent.com/obra/agent-team-protocol/main/install.sh | bash

# 创建团队
agent-team init 杂志社

# 添加成员
agent-team member add 撰稿人 "文章撰写"
agent-team member add 编辑 "审核润色"

# 创建任务
agent-team task add "撰写发刊词" high
agent-team task add "排版校对" medium

# 认领并完成任务
agent-team task claim task-001 撰稿人
echo "文章内容..." > .agent-team/artifacts/task-001/article.md
agent-team task complete task-001 "发刊词完成，见 artifacts/task-001/article.md"

# 代理间通信
agent-team msg 撰稿人 编辑 request "请审阅文章"

# 查看收件箱
agent-team inbox 编辑

# 团队概览
agent-team status

# 生成代理提示词（用于 LLM Agent 工具）
agent-team spawn 撰稿人
```

## 命令参考

| 命令 | 说明 |
|------|------|
| `agent-team init <name>` | 创建团队 |
| `agent-team member add <id> <role>` | 添加成员 |
| `agent-team member list` | 列出成员 |
| `agent-team task add <title> [priority]` | 创建任务 |
| `agent-team task list [status]` | 列任务 (all/pending/active/done/blocked) |
| `agent-team task show <id>` | 任务详情 |
| `agent-team task claim <id> <agent>` | 原子认领任务 |
| `agent-team task complete <id> [summary]` | 完成任务 |
| `agent-team task block <id> <reason>` | 阻塞任务 |
| `agent-team task unblock <id>` | 解除阻塞 |
| `agent-team msg <from> <to> <type> <text>` | 发送消息 |
| `agent-team inbox <agent>` | 查看收件箱 |
| `agent-team inbox-clear <agent>` | 清空收件箱 |
| `agent-team spawn <agent-id>` | 生成 LLM 代理提示词 |
| `agent-team status` | 团队概览 |
| `agent-team disband` | 删除团队 |

## 设计原则

- **零依赖** — 仅需 bash 和文件系统
- **原子安全** — mv / mkdir 原子操作保证并发安全
- **可调试** — cat/ls 即可排查所有状态
- **跨会话持久** — 关闭终端后状态保留
- **模型无关** — 不绑定任何 LLM 提供商

## 协议文档

完整规范见 [PROTOCOL.md](PROTOCOL.md)。

## 许可

MIT

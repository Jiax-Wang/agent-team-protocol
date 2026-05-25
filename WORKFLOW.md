# Agent Team v2 工作流

融合 YOLO 持久化架构 + Finance 实时辩论引擎。Anthropic API 驱动。

## 三种运行模式

```
用户
 │
 ├── debate "问题"  ──→  实时同步辩论  ──→  收敛  ──→  方案
 │
 ├── signoff "决策"  ──→  四方审查投票  ──→  批准/否决
 │
 └── task <角色>     ──→  异步任务分配  ──→  inbox通信
```

## 模式1: 实时辩论 (debate)

```
python cli.py debate "v7_final 2787张退步的根因是什么？"
python cli.py debate "是否应该加入 v3 真实数据？" --rounds 20
python cli.py debate "合成图最优占比是多少？" --no-think
```

流程：
Round 1: algo + data + reviewer 并行发言（初始观点）
Round 2: critic 抨击（只批判，不建议）
Round 3-5: 自由辩论
Round 6-8: 收敛共识
→ 自动终止 → 保存到 state/debates/

## 模式2: 正式签字 (signoff)

```
python cli.py signoff "上线 v7_final 模型"
python cli.py vote signoff-2026-05-24-01 algo pass "技术可行"
python cli.py vote signoff-2026-05-24-01 data pass "数据质量达标"
python cli.py vote signoff-2026-05-24-01 reviewer pass "规范合规"
python cli.py vote signoff-2026-05-24-01 critic pass "方法论无缺陷"
```

流程：PM发起提案 → 写入 signoffs.jsonl → 讨论窗口（15分钟）→ 投票 → PM裁决

## 模式3: 异步任务 (task)

```
python cli.py task algo "模型训练" "用 neg35 配方训练 v7_final"
python cli.py task data "数据审计" "检查 v7_syn500 的 408 张标注质量"
python cli.py inbox algo
python cli.py inbox
```

## 收件箱

```
python cli.py inbox          # 所有角色未读汇总
python cli.py inbox algo     # algo 的未读消息
python cli.py summary        # 团队状态概览
```

## 环境变量

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export ANTHROPIC_MODEL="claude-sonnet-4-20250514"  # 可选
```

## 核心设计原则

1. **持久化优先**：所有状态落盘，session 断了可恢复
2. **辩论即争议解决**：分歧→实时辩论→收敛→执行
3. **签字即责任**：四方背书，有据可查
4. **私密思考**：Agent 发言前先内部推理（`--think`），其他 Agent 看不到
5. **收件箱异步**：不需要所有 Agent 同时在线

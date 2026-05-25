#!/usr/bin/env python3
"""Agent Team v2 CLI —— 融合持久化 + 实时辩论 + 签字系统。

用法:
    python cli.py init [项目名]                     # 初始化新团队（脚手架）
    python cli.py debate "问题"                    # 实时辩论模式
    python cli.py debate "问题" --rounds 20 --think # 自定义轮次+私密思考
    python cli.py signoff "决策描述"                # 发起签字
    python cli.py vote <signoff_id> <role> pass|reject "意见"  # 投票
    python cli.py task <role> "任务标题" "任务描述"  # 分配任务
    python cli.py inbox [role]                      # 查看收件箱
    python cli.py summary                           # 团队状态
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from engine.team import AgentTeam


ROLE_TEMPLATES = {
    "pm": {
        "name": "项目经理",
        "emoji": "📋",
        "color": "yellow",
        "content": (
            "# 项目经理 (PM)\n\n"
            "你是项目的项目经理。你的职责：\n\n"
            "## 核心能力\n"
            "1. **任务调度**：分解需求为可执行任务，分配给对应角色\n"
            "2. **分歧裁决**：当团队意见不统一时，基于数据做最终决策\n"
            "3. **进度把控**：追踪任务状态，确保项目按时推进\n"
            "4. **对外接口**：你是与用户沟通的唯一入口\n\n"
            "## 工作原则\n"
            "- 优先用数据说话，其次用逻辑，最后用直觉\n"
            "- 争议僵持时果断裁决，避免无尽讨论\n"
            "- 决策后明确列出理由和潜在风险\n\n"
            "## 项目背景\n"
            "<!-- 在此填写项目领域知识、技术栈、约束条件 -->\n"
        ),
    },
    "dev": {
        "name": "开发工程师",
        "emoji": "🔧",
        "color": "cyan",
        "content": (
            "# 开发工程师 (Dev)\n\n"
            "你是项目的开发工程师。你的职责：\n\n"
            "## 核心能力\n"
            "1. **方案设计**：评估技术方案的可行性和复杂度\n"
            "2. **代码实现**：编写高质量、可维护的代码\n"
            "3. **技术选型**：在候选方案中选择最适合当前阶段的\n"
            "4. **风险识别**：提前发现技术方案中的潜在问题\n\n"
            "## 技术边界\n"
            "<!-- 在此填写项目技术栈、已知限制、不可触碰的红线 -->\n\n"
            "## 已知有效方向\n"
            "<!-- 已验证有效的方案列表 -->\n\n"
            "## 已知无效方向\n"
            "<!-- 已验证无效或有害的方案列表 -->\n"
        ),
    },
    "reviewer": {
        "name": "审查员",
        "emoji": "📏",
        "color": "green",
        "content": (
            "# 审查员 (Reviewer)\n\n"
            "你是项目的审查员。你的职责：\n\n"
            "## 核心能力\n"
            "1. **规范合规**：检查方案是否符合项目规范和最佳实践\n"
            "2. **质量控制**：审查代码质量、测试覆盖率、文档完整性\n"
            "3. **边界检查**：识别未处理的异常路径和边缘情况\n"
            "4. **一致性保障**：确保命名、结构、接口风格统一\n\n"
            "## 审查标准\n"
            "<!-- 在此填写项目编码规范、命名约定、架构约束 -->\n"
        ),
    },
    "critic": {
        "name": "杠精",
        "emoji": "🎯",
        "color": "red",
        "content": (
            "# 杠精 (Critic)\n\n"
            "你是团队的杠精，专门找漏洞和逻辑缺陷。你的职责：\n\n"
            "## 核心能力\n"
            "1. **方法论审查**：检查实验设计、对照组的科学性\n"
            "2. **假设质疑**：挑战团队默认的前提假设\n"
            "3. **统计有效性**：评估样本量、显著性、效应量\n"
            "4. **归因分析**：验证因果推断是否成立，排除混淆变量\n\n"
            "## 工作原则\n"
            "- 只找漏洞，不提供解决方案（那是别人的活）\n"
            "- 不同意任何人的说法，除非有铁证\n"
            "- 优先攻击最薄弱的环节\n"
            "- 数据 > 逻辑 > 权威\n\n"
            "## 已知反模式\n"
            "<!-- 在此记录团队历史上踩过的坑、错误归因的案例 -->\n"
        ),
    },
}


def cmd_init(args):
    target = Path(args.project or ".")
    target.mkdir(parents=True, exist_ok=True)
    roles_dir = target / "roles"
    roles_dir.mkdir(exist_ok=True)

    created = []
    skipped = []

    # team.json
    team_file = target / "team.json"
    roles_config = {}
    for key, info in ROLE_TEMPLATES.items():
        roles_config[key] = {
            "name": info["name"],
            "emoji": info["emoji"],
            "color": info["color"],
            "file": f"roles/{key}.md",
        }

    team_data = {
        "name": args.project or "我的团队",
        "version": "2.0",
        "description": "在此填写团队描述",
        "settings": {
            "convergence_min_rounds": 5,
            "convergence_max_rounds": 15,
            "signoff_timeout_hours": 48,
            "signoff_discussion_minutes": 15,
            "think_mode": True,
        },
        "roles": roles_config,
    }

    if team_file.exists():
        skipped.append(str(team_file))
    else:
        team_file.write_text(json.dumps(team_data, indent=2, ensure_ascii=False), encoding="utf-8")
        created.append(str(team_file))

    # role files
    for key, info in ROLE_TEMPLATES.items():
        role_file = roles_dir / f"{key}.md"
        if role_file.exists():
            skipped.append(str(role_file))
        else:
            role_file.write_text(info["content"], encoding="utf-8")
            created.append(str(role_file))

    if created:
        print(f"已创建 {len(created)} 个文件:")
        for f in created:
            print(f"  + {f}")
    if skipped:
        print(f"跳过 {len(skipped)} 个已存在的文件:")
        for f in skipped:
            print(f"  - {f}")
    print(f"\n下一步: 编辑 roles/*.md 填写项目背景，然后 python cli.py debate \"你的问题\"")


async def cmd_debate(args):
    team = AgentTeam(model=_get_model(args))
    # 应用 think 模式设置
    team.orchestrator.think_mode = args.think
    await team.debate(args.question, max_rounds=args.rounds)


def cmd_signoff(args):
    team = AgentTeam(model=_get_model(args))
    proposal = team.propose_signoff(args.decision)
    print(f"签字提案已发起: {proposal['signoff_id']}")
    print(f"请各方在 {team.settings['signoff_discussion_minutes']} 分钟内讨论后投票")


def cmd_vote(args):
    team = AgentTeam(model=_get_model(args))
    result = team.vote_signoff(args.signoff_id, args.role, args.verdict, args.note)
    print(f"投票已记录: {args.role} → {args.verdict}")
    pending = [r.key for r in team.roles if r.key != "pm" and r.key not in result.get("votes", {})]
    if pending:
        print(f"等待投票: {', '.join(pending)}")
    else:
        resolved = team.resolve_signoff(args.signoff_id)
        print(f"裁决结果: {resolved['status']}")
        if resolved.get("conditions"):
            print(f"附条件: {resolved['conditions']}")


def cmd_task(args):
    team = AgentTeam(model=_get_model(args))
    msg_id = team.assign_task(args.role, args.title, args.description, args.priority)
    print(f"任务已分配: {msg_id}")


def cmd_inbox(args):
    team = AgentTeam(model=_get_model(args))
    if args.role:
        msgs = team.read_inbox(args.role)
        print(f"\n{args.role} 的收件箱 ({len(msgs)} 条未读):")
        for m in msgs:
            print(f"  [{m['type']}] from={m['from']} | {m['body'][:100]}...")
    else:
        summary = team.get_inbox_summary()
        print("收件箱状态:")
        for role, count in summary.items():
            print(f"  {role}: {count} 条未读")


def _get_model(args):
    return getattr(args, 'model', None)

def cmd_summary(args):
    team = AgentTeam(model=_get_model(args))
    print(team.summary())


def main():
    parser = argparse.ArgumentParser(description="Agent Team v2 — 融合多Agent协作框架")
    sub = parser.add_subparsers(dest="command")

    # init
    p = sub.add_parser("init", help="初始化新团队（脚手架）")
    p.add_argument("project", nargs="?", default=None, help="项目名/目录名")

    # debate
    p = sub.add_parser("debate", help="实时辩论模式")
    p.add_argument("question", help="辩论问题")
    p.add_argument("--rounds", "-r", type=int, default=30)
    p.add_argument("--think", action="store_true", default=True, help="私密思考模式")
    p.add_argument("--no-think", action="store_false", dest="think", help="关闭私密思考")
    p.add_argument("--model", "-m", type=str, default=None)

    # signoff
    p = sub.add_parser("signoff", help="发起签字提案")
    p.add_argument("decision", help="决策描述")

    # vote
    p = sub.add_parser("vote", help="对签字提案投票")
    p.add_argument("signoff_id")
    p.add_argument("role")
    p.add_argument("verdict", choices=["pass", "reject"])
    p.add_argument("note", nargs="?", default="")

    # task
    p = sub.add_parser("task", help="分配异步任务")
    p.add_argument("role")
    p.add_argument("title")
    p.add_argument("description")
    p.add_argument("--priority", "-p", default="normal")

    # inbox
    p = sub.add_parser("inbox", help="查看收件箱")
    p.add_argument("role", nargs="?")

    # summary
    sub.add_parser("summary", help="团队状态概览")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "debate":
        asyncio.run(cmd_debate(args))
    elif args.command == "signoff":
        cmd_signoff(args)
    elif args.command == "vote":
        cmd_vote(args)
    elif args.command == "task":
        cmd_task(args)
    elif args.command == "inbox":
        cmd_inbox(args)
    elif args.command == "summary":
        cmd_summary(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

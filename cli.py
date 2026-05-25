#!/usr/bin/env python3
"""Agent Team v2 CLI —— 融合持久化 + 实时辩论 + 签字系统。

用法:
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
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from engine.team import AgentTeam


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

    if args.command == "debate":
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

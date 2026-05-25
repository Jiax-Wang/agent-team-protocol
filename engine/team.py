"""团队管理器 —— 融合架构的核心调度层。

整合：收件箱 + 辩论引擎 + 签字系统。
三种运行模式：debate（实时辩论）、signoff（正式签字）、task（异步任务）。
"""

import asyncio
import json
from pathlib import Path

from engine.inbox import InboxSystem
from engine.orchestrator import DebateOrchestrator, Role
from engine.signoff import SignoffSystem


class AgentTeam:
    """通用多Agent协作团队。"""

    def __init__(self, config_path: str = "team.json", model: str | None = None):
        self.config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        self.settings = self.config["settings"]
        self.model = model
        self.inbox = InboxSystem()
        self.signoff = SignoffSystem()

        # 加载角色
        self.roles: list[Role] = []
        for key, cfg in self.config["roles"].items():
            role_file = Path(cfg["file"])
            if not role_file.exists():
                role_file = Path(config_path).parent / cfg["file"]
            system_prompt = role_file.read_text(encoding="utf-8") if role_file.exists() else cfg.get("description", "")
            self.roles.append(Role(
                key=key, name=cfg["name"], emoji=cfg["emoji"],
                color=cfg["color"], system_prompt=system_prompt,
            ))
            self.inbox.register_role(key)

        # 创建辩论引擎
        think_mode = self.settings.get("think_mode", True)
        self.orchestrator = DebateOrchestrator(self.roles, model=model, think_mode=think_mode)

    async def debate(self, question: str, max_rounds: int | None = None) -> dict:
        """运行实时辩论模式。"""
        if max_rounds is None:
            max_rounds = self.settings.get("convergence_max_rounds", 30)
        return await self.orchestrator.run_debate(question, max_rounds=max_rounds)

    def propose_signoff(self, decision: str) -> dict:
        """发起签字提案。"""
        proposal = self.signoff.create_proposal(decision)
        # 广播到所有角色收件箱
        signoff_id = proposal["signoff_id"]
        for role in self.roles:
            if role.key == "pm":
                continue
            self.inbox.send(
                to_role=role.key,
                msg_type="signoff_proposal",
                body=f"PM 发起签字提案 [{signoff_id}]: {decision}\n请审查并回复 signoff_vote。",
                from_role="pm",
                ref_id=signoff_id,
            )
        return proposal

    def vote_signoff(self, signoff_id: str, role_key: str, verdict: str, note: str = "") -> dict:
        """对签字提案投票。"""
        return self.signoff.vote(signoff_id, role_key, verdict, note)

    def resolve_signoff(self, signoff_id: str) -> dict:
        """裁决签字提案。"""
        voter_keys = [r.key for r in self.roles if r.key != "pm"]
        return self.signoff.resolve(signoff_id, voter_keys)

    def assign_task(self, role_key: str, title: str, description: str,
                    priority: str = "normal") -> str:
        """分配异步任务。"""
        return self.inbox.send(
            to_role=role_key,
            msg_type="task_assign",
            body=f"任务: {title}\n\n{description}",
            from_role="pm",
            priority=priority,
        )

    def get_inbox_summary(self) -> dict:
        """查看各角色收件箱状态。"""
        return self.inbox.get_unread_summary()

    def read_inbox(self, role_key: str) -> list[dict]:
        """读取角色收件箱。"""
        return self.inbox.read_unread(role_key)

    def summary(self) -> str:
        """团队状态概览。"""
        modes = list(self.config["modes"].keys())
        role_names = [r.name for r in self.roles]
        inbox_summary = self.get_inbox_summary()
        pending_signoffs = len(self.signoff.get_pending())

        lines = [
            f"团队: {self.config['name']}",
            f"角色: {', '.join(role_names)}",
            f"模式: {', '.join(modes)}",
            f"私密思考: {'开启' if self.settings.get('think_mode') else '关闭'}",
            f"待处理签字: {pending_signoffs}",
            f"收件箱: {inbox_summary}",
        ]
        return "\n".join(lines)

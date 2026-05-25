"""多Agent实时辩论编排器 —— 从 Finance Agent Team 继承并泛化。

核心能力：
- N角色同步辩论（不限于3个）
- 私密思考模式（先想再说）
- 分阶段轮次指令（发散→收敛）
- 自动收敛检测
- 独立上下文（每个Agent维护私有思考历史）
"""

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from openai import AsyncOpenAI
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn


@dataclass
class Role:
    """辩论角色定义。"""
    key: str
    name: str
    emoji: str
    color: str
    system_prompt: str
    role_label: str = ""

    def __post_init__(self):
        if not self.role_label:
            self.role_label = f"{self.emoji} {self.name}"


CONVERGE_KEYWORDS = [
    "达成一致", "一致同意", "我同意方案", "我接受方案", "我闭嘴",
    "三方签字", "共同签署", "最终方案", "不再争论", "完全同意",
    "没有分歧", "共识达成", "可以签字", "我认可", "可以执行",
]


class DebateOrchestrator:
    """泛化辩论编排器。支持N个角色、私密思考、收敛检测。"""

    def __init__(self, roles: list[Role], model: str | None = None, think_mode: bool = True):
        self.console = Console()

        api_key = os.environ.get("DEEPSEEK_API_KEY")
        base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.client = None
        self.use_mock = False
        if api_key:
            self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        else:
            self.use_mock = True
            self.console.print("[dim]DEEPSEEK_API_KEY 未设置，使用 mock 模式[/dim]")
        self.model = model or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        self.roles = {r.key: r for r in roles}
        self.role_order = [r.key for r in roles if r.key != "pm"]  # PM不参与辩论
        self.think_mode = think_mode
        self.question = ""
        self.transcript: list[tuple[str, str]] = []
        self.private_thoughts: dict[str, str] = {}

    def _build_transcript_text(self) -> str:
        if not self.transcript:
            return ""
        lines = []
        for agent_key, content in self.transcript:
            role = self.roles[agent_key]
            lines.append(f"### {role.role_label}")
            lines.append(content)
            lines.append("")
        return "\n".join(lines)

    def _get_round_instruction(self, round_num: int, speaker_key: str) -> str:
        """根据轮次和角色返回不同的发言指令。"""
        if round_num == 0:
            return "请发表你对用户问题的初步分析和建议。这是辩论的第一轮，尽情展示你的专业判断。"
        if round_num == 1 and speaker_key == "critic":
            return "请针对前两位专家的发言进行批判性分析。找出漏洞、过度乐观的假设、被忽略的风险。火力全开！"
        if round_num < 5:
            return (
                "请针对最新一轮的发言进行回应。你可以：补充新观点、反驳他人的论点、"
                "修正自己之前的判断。发言要简洁有力。"
            )
        if round_num < 8:
            return (
                "辩论已进入后半程。请识别共识点，明确列出同意什么、"
                "仍然不同意什么、底线是什么。不要引入新话题，聚焦缩小分歧。"
            )
        if round_num < 9:
            return (
                "辩论即将结束。请给出你可以接受的最终妥协方案。"
                "方案必须包含具体数字和执行步骤，经得起验算。"
            )
        return (
            "这是最后一轮。请给出最终陈述——一个你可以签字负责的方案。"
            "格式：用表格列出具体金额/配置/预期/风险/执行时间。"
        )

    async def _call_agent(self, agent_key: str, round_num: int) -> str:
        """调用单个Agent。think_mode下先私下思考再公开发言。"""
        role = self.roles[agent_key]
        transcript = self._build_transcript_text()
        instruction = self._get_round_instruction(round_num, agent_key)

        if self.use_mock:
            return self._mock_response(agent_key, round_num)

        if transcript:
            base = f"公开辩论记录：\n\n{transcript}\n\n用户问题：\n{self.question}"
        else:
            base = f"用户问题：\n{self.question}"

        if not self.think_mode:
            resp = await self.client.chat.completions.create(
                model=self.model, max_tokens=800,
                messages=[
                    {"role": "system", "content": role.system_prompt},
                    {"role": "user", "content": f"{base}\n\n{instruction}"},
                ],
            )
            return resp.choices[0].message.content or ""

        # ── 私密思考 ──
        private_history = self.private_thoughts.get(agent_key, "")
        think_prompt = (
            f"{base}\n\n"
            f"【私密思考时间 —— 其他Agent看不到】\n"
            f"1. 上一轮各方说了什么？谁的论证有漏洞？\n"
            f"2. 你的核心目标？本轮想达成什么？\n"
            f"3. 策略选择：进攻/让步/提出新方案？\n"
            + (f"\n你之前的私密思考：\n{private_history}\n" if private_history else "")
            + f"\n现在请思考，不要公开发言。"
        )
        think_resp = await self.client.chat.completions.create(
            model=self.model, max_tokens=600,
            messages=[
                {"role": "system", "content": role.system_prompt},
                {"role": "user", "content": think_prompt},
            ],
        )
        thought = think_resp.choices[0].message.content or ""
        self.private_thoughts[agent_key] = (
            self.private_thoughts.get(agent_key, "") + f"\n[第{round_num+1}轮思考]\n{thought}\n"
        )

        # ── 公开发言 ──
        speak_prompt = (
            f"{base}\n\n"
            f"你的私密策略分析已完成。现在以{role.name}身份公开发言。\n"
            f"要求：{instruction}\n"
            f"注意：不要透露私密策略（如'我计划先让步'）。"
        )
        speak_resp = await self.client.chat.completions.create(
            model=self.model, max_tokens=800,
            messages=[
                {"role": "system", "content": role.system_prompt},
                {"role": "user", "content": speak_prompt},
            ],
        )
        return speak_resp.choices[0].message.content or ""

    def _check_convergence(self, round_num: int) -> bool:
        if round_num < 5:
            return False
        n = len(self.role_order)
        recent = self.transcript[-n:] if len(self.transcript) >= n else self.transcript
        if len(recent) < n:
            return False
        texts = [c for _, c in recent]
        all_short = all(len(t) < 300 for t in texts)
        any_conv = any(any(kw in t for kw in CONVERGE_KEYWORDS) for t in texts)
        return all_short or any_conv

    async def run_debate(self, question: str, max_rounds: int = 30) -> dict:
        """运行辩论。返回最终状态。"""
        self.question = question
        self.transcript = []
        self.private_thoughts = {}

        self.console.print()
        self.console.print(Panel(f"[bold white]{question}[/bold white]",
                           title="📋 用户问题", border_style="white"))

        # Round 0: 所有非critic角色发言
        non_critics = [k for k in self.role_order if k != "critic"]
        critics = [k for k in self.role_order if k == "critic"]

        for round_num in range(max_rounds):
            label = f"第 {round_num + 1} 轮"
            self.console.print(f"\n[bold cyan]━━━ {label} ━━━[/bold cyan]\n")

            # 确定本轮发言人
            if round_num == 0 and non_critics:
                speakers = non_critics
            elif round_num == 1 and critics:
                speakers = critics
            else:
                speakers = self.role_order

            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                          console=self.console) as progress:
                task = progress.add_task("[cyan]Agent 辩论中...", total=None)
                tasks = [self._call_agent(ak, round_num) for ak in speakers]
                responses = await asyncio.gather(*tasks, return_exceptions=True)
                progress.remove_task(task)

            for agent_key, response in zip(speakers, responses):
                role = self.roles[agent_key]
                if isinstance(response, Exception):
                    content = f"❌ 调用失败: {response}"
                    border = "red"
                else:
                    content = str(response)
                    border = role.color
                    self.transcript.append((agent_key, content))
                self.console.print(Panel(content, title=role.role_label, border_style=border))

            if self._check_convergence(round_num):
                self.console.print("\n[bold yellow]🔨 三方已达成妥协，辩论自然终止[/bold yellow]")
                break

        self._save_debate()
        self.console.print("\n[bold green]✅ 辩论结束[/bold green]\n")
        return {"transcript": self.transcript, "question": self.question}

    def _mock_response(self, agent_key: str, round_num: int) -> str:
        """Mock 模式 —— 生成模拟发言用于架构测试。"""
        role = self.roles[agent_key]
        templates = {
            "algo": [
                "从训练曲线看，模型在 epoch 15 时 val loss 已收敛，后续 85 个 epoch 在震荡。这说明数据信号已耗尽。增加合成图相当于增加噪声，不是信息。",
                "建议回退到 v5_pretrain 配方，同时在 v5 基础上做 multi-seed 验证。如果三 seed 稳定，那就是答案。",
            ],
            "data": [
                "v5_pretrain 的 590 张合成图用了纯 v3 ROI + v3 背景。后续实验混入了 v2 ROI（即使 10%）和不同材质 ROI，破坏了域一致性。",
                "408 张新的纯 v3 合成图理论上是同配方的，但如果生成参数（seed/variants/aug）和 590 不同，分布偏移就可能存在。",
            ],
            "reviewer": [
                "所有实验配置合规，没有违反 CLAUDE.md 硬约束。问题不在这方面。",
                "建议 focus 在数据配方上，合规方面没有红线问题。",
            ],
            "critic": [
                "你们忽略了一个关键事实：所有实验都在同一 16 张 v2 上评估。20+ 次实验的 selection bias 已经无法忽略。v5_pretrain 可能只是'碰巧'在 v2 上最好。",
                "而且 v2+v3 的 265 张 val 中，v3 占了 249 张。v3 和训练数据时间重叠——这不是独立的测试集。我们一直在用'被污染的测试集'做决策。",
            ],
            "pm": [
                "综合各方意见：根因是域偏移——合成图来自 v3 时间域，无法泛化到 v2。解决方案是采集多场景数据，不是继续调参。",
                "当前建议：部署 v5_pretrain，同时启动多场景数据采集计划。",
            ],
        }
        lines = templates.get(agent_key, ["需要更多实验数据才能给出判断。"])
        return lines[round_num % len(lines)]

    def _save_debate(self) -> None:
        """保存辩论记录。"""
        debates_dir = Path("state/debates")
        debates_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_q = "".join(c for c in self.question[:30] if c.isalnum() or c in " _-").strip() or "debate"
        filepath = debates_dir / f"{ts}_{safe_q}.md"

        lines = [f"# 辩论记录", "", f"**问题**: {self.question}",
                 f"**时间**: {datetime.now()}", f"**模型**: {self.model}", "", "---", ""]
        for agent_key, content in self.transcript:
            role = self.roles[agent_key]
            lines.append(f"## {role.role_label}")
            lines.append(content)
            lines.append("")
        filepath.write_text("\n".join(lines), encoding="utf-8")
        self.console.print(f"\n[dim]📄 辩论记录已保存至: {filepath}[/dim]")

"""签字系统 —— 从 YOLO Agent Team 继承。

重大决策需要四方投票。每个角色在自身领域内拥有一票否决权。
支持：提案→讨论→投票→裁决→条件追踪。
"""

import json
from datetime import datetime, timezone
from pathlib import Path


class SignoffSystem:
    """管理正式签字流程。"""

    def __init__(self, state_dir: str = "state"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.signoffs_file = self.state_dir / "signoffs.jsonl"
        if not self.signoffs_file.exists():
            self.signoffs_file.write_text("", encoding="utf-8")

    def create_proposal(self, pm_decision: str, signoff_id: str = "") -> dict:
        """创建签字提案。"""
        if not signoff_id:
            signoff_id = datetime.now(timezone.utc).strftime("%Y-%m-%d") + "-" + pm_decision[:20]
        proposal = {
            "signoff_id": signoff_id,
            "pm_decision": pm_decision,
            "status": "pending",
            "votes": {},
            "conditions": [],
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "resolved_ts": None,
        }
        self._save(proposal)
        return proposal

    def vote(self, signoff_id: str, role: str, verdict: str, note: str = "") -> dict:
        """角色投票。verdict: pass | reject。"""
        proposal = self._load(signoff_id)
        if not proposal:
            raise ValueError(f"签字提案 {signoff_id} 不存在")
        proposal["votes"][role] = {"verdict": verdict, "note": note}
        self._save(proposal)
        return proposal

    def resolve(self, signoff_id: str, required_roles: list[str]) -> dict:
        """裁决签字结果。全票pass→approved，任一reject→rejected。"""
        proposal = self._load(signoff_id)
        if not proposal:
            raise ValueError(f"签字提案 {signoff_id} 不存在")

        verdicts = []
        conditions = []
        for role in required_roles:
            v = proposal["votes"].get(role, {})
            if not v:
                proposal["status"] = "pending"
                self._save(proposal)
                return proposal
            verdicts.append(v["verdict"])
            if v.get("note"):
                conditions.append(f"{role}: {v['note']}")

        if all(v == "pass" for v in verdicts):
            proposal["status"] = "approved"
            proposal["conditions"] = conditions if conditions else ["无"]
        else:
            proposal["status"] = "rejected"

        proposal["resolved_ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._save(proposal)
        return proposal

    def get_pending(self) -> list[dict]:
        """获取所有待处理的提案。"""
        proposals = []
        if not self.signoffs_file.exists():
            return proposals
        for line in self.signoffs_file.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                p = json.loads(line)
                if p.get("status") in ("pending", "in_review"):
                    proposals.append(p)
            except json.JSONDecodeError:
                continue
        return proposals

    def _save(self, proposal: dict) -> None:
        """保存或更新提案。"""
        proposals = []
        if self.signoffs_file.exists():
            for line in self.signoffs_file.read_text(encoding="utf-8").strip().split("\n"):
                if not line.strip():
                    continue
                try:
                    p = json.loads(line)
                    if p.get("signoff_id") != proposal["signoff_id"]:
                        proposals.append(p)
                except json.JSONDecodeError:
                    continue
        proposals.append(proposal)
        self.signoffs_file.write_text(
            "\n".join(json.dumps(p, ensure_ascii=False) for p in proposals) + "\n",
            encoding="utf-8"
        )

    def _load(self, signoff_id: str) -> dict | None:
        if not self.signoffs_file.exists():
            return None
        for line in self.signoffs_file.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                p = json.loads(line)
                if p.get("signoff_id") == signoff_id:
                    return p
            except json.JSONDecodeError:
                continue
        return None

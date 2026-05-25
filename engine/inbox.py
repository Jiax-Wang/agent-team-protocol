"""文件收件箱系统 —— 从 YOLO Agent Team 继承。

每个角色拥有独立的 inbox JSONL 文件。消息按行追加，按时间排序。
支持：任务分配、审查请求、挑战邀请、签字提案、系统广播。
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


class InboxSystem:
    """管理所有角色的收件箱文件。"""

    def __init__(self, base_dir: str = "."):
        self.inbox_dir = Path(base_dir) / "inbox"
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.roles: list[str] = []

    def register_role(self, role_key: str) -> None:
        """注册一个角色，创建其收件箱文件。"""
        if role_key not in self.roles:
            self.roles.append(role_key)
        inbox_file = self._path(role_key)
        if not inbox_file.exists():
            inbox_file.write_text("", encoding="utf-8")

    def _path(self, role_key: str) -> Path:
        return self.inbox_dir / f"{role_key}.jsonl"

    def send(self, to_role: str, msg_type: str, body: str,
             from_role: str = "system", ref_id: str = "",
             priority: str = "normal") -> str:
        """向指定角色收件箱发送消息。返回消息ID。"""
        msg = {
            "id": f"msg-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{to_role}",
            "from": from_role,
            "to": to_role,
            "type": msg_type,
            "ref_id": ref_id,
            "priority": priority,
            "body": body,
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "read": False,
        }
        with open(self._path(to_role), "a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
        return msg["id"]

    def read_unread(self, role_key: str) -> list[dict]:
        """读取某个角色的未读消息。"""
        path = self._path(role_key)
        if not path.exists():
            return []
        messages = []
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        for line in lines:
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
                if not msg.get("read", False):
                    messages.append(msg)
            except json.JSONDecodeError:
                continue
        return messages

    def read_all(self, role_key: str) -> list[dict]:
        """读取某个角色的所有消息。"""
        path = self._path(role_key)
        if not path.exists():
            return []
        messages = []
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        for line in lines:
            if not line.strip():
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return messages

    def mark_read(self, role_key: str, msg_ids: list[str] | None = None) -> None:
        """标记消息为已读。msg_ids=None 则全部标记。"""
        path = self._path(role_key)
        if not path.exists():
            return
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        updated = []
        for line in lines:
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
                if msg_ids is None or msg["id"] in msg_ids:
                    msg["read"] = True
                updated.append(json.dumps(msg, ensure_ascii=False))
            except json.JSONDecodeError:
                continue
        path.write_text("\n".join(updated) + "\n", encoding="utf-8")

    def get_unread_summary(self) -> dict[str, int]:
        """获取各角色未读消息数量汇总。"""
        return {r: len(self.read_unread(r)) for r in self.roles}

    def broadcast(self, msg_type: str, body: str, from_role: str = "system") -> list[str]:
        """向所有角色广播消息。返回消息ID列表。"""
        ids = []
        for role in self.roles:
            ids.append(self.send(role, msg_type, body, from_role=from_role))
        return ids

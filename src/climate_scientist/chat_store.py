"""Small local JSON store for the Streamlit chat sidebar and conversation history."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid

from .config import PROJECT_ROOT

CHAT_DIRECTORY = PROJECT_ROOT / "experiments" / "chats"


def _path(chat_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", chat_id):
        raise ValueError("Invalid chat identifier")
    return CHAT_DIRECTORY / f"{chat_id}.json"


def load_chat(chat_id: str) -> dict:
    path = _path(chat_id)
    if not path.exists():
        return {"id": chat_id, "title": "New chat", "created_at": None,
                "updated_at": None, "messages": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_chat(chat: dict) -> None:
    CHAT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    destination = _path(chat["id"])
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(chat, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(destination)


def create_chat() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    chat = {"id": uuid.uuid4().hex, "title": "New chat", "created_at": now,
            "updated_at": now, "messages": []}
    save_chat(chat)
    return chat


def add_message(chat: dict, role: str, content: str, plot_path: str | None = None,
                metadata: dict | None = None) -> dict:
    if role not in {"user", "assistant"}:
        raise ValueError("Chat message role must be user or assistant")
    chat["messages"].append({"role": role, "content": content,
        "plot_path": plot_path, "metadata": metadata or {},
        "created_at": datetime.now(timezone.utc).isoformat()})
    if role == "user" and chat["title"] == "New chat":
        chat["title"] = content.strip().replace("\n", " ")[:64] or "New chat"
    chat["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_chat(chat)
    return chat


def list_chats() -> list[dict]:
    if not CHAT_DIRECTORY.exists():
        return []
    chats = []
    for path in CHAT_DIRECTORY.glob("*.json"):
        try:
            chat = json.loads(path.read_text(encoding="utf-8"))
            chats.append({"id": chat["id"], "title": chat.get("title", "New chat"),
                          "updated_at": chat.get("updated_at", "")})
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
    return sorted(chats, key=lambda item: item["updated_at"], reverse=True)

import json
from pathlib import Path
from typing import Optional
from context.store.base_context_store import BaseContextStore

class LocalContextStore(BaseContextStore):
    """
    Local context store implementation.
    Each agent's context is stored in a file named {agent_id}.json
    inside the configured directory.
    """
    def __init__(self, root_path: Path):
        self.root_path = Path(root_path).expanduser()
        self.root_path.mkdir(parents=True, exist_ok=True)

    def _get_agent_file(self, agent_id: str) -> Path:
        return self.root_path / f"{agent_id}.json"

    def get_context(self, agent_id: str) -> Optional[str]:
        path = self._get_agent_file(agent_id)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def set_context(self, agent_id: str, context: str) -> None:
        path = self._get_agent_file(agent_id)
        path.write_text(context, encoding="utf-8")

    def delete_context(self, agent_id: str) -> None:
        path = self._get_agent_file(agent_id)
        if path.exists():
            path.unlink()

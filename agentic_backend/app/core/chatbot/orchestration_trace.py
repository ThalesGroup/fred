# orchestration_trace.py
from dataclasses import dataclass, field
from typing import Set, Optional

@dataclass
class OrchestrationTrace:
    libraries: Set[str] = field(default_factory=set)
    mcp_services: Set[str] = field(default_factory=set)
    tools: Set[str] = field(default_factory=set)
    docs_used: int = 0
    search_policy: Optional[str] = None
    temperature: Optional[float] = None

    def add_library(self, name: str): 
        if name: self.libraries.add(name)

    def add_mcp(self, service: str): 
        if service: self.mcp_services.add(service)

    def add_tool(self, tool: str): 
        if tool: self.tools.add(tool)

    def bump_docs(self, n: int = 1): 
        self.docs_used += max(0, n)

    def set_search_policy(self, policy: Optional[str]): 
        self.search_policy = policy or self.search_policy

    def set_temperature(self, temp: Optional[float]): 
        self.temperature = temp if temp is not None else self.temperature

    def to_plugins_dict(self) -> dict:
        d = {}
        if self.libraries:     d["libraries"]     = sorted(self.libraries)
        if self.mcp_services:  d["mcp_services"]  = sorted(self.mcp_services)
        if self.tools:         d["tools"]         = sorted(self.tools)
        if self.docs_used:     d["docs_used"]     = self.docs_used
        if self.search_policy: d["search_policy"] = self.search_policy
        if self.temperature is not None: d["temperature"] = self.temperature
        return d

"""
Core data models for skills and their manifests.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[no-redef]
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]

import tomli_w


@dataclass
class RuntimeConfig:
    type: Literal["python", "node", "binary", "none"]
    python_version: Optional[str] = None
    node_version: Optional[str] = None
    install_cmd: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"type": self.type, "install_cmd": self.install_cmd}
        if self.python_version:
            d["python_version"] = self.python_version
        if self.node_version:
            d["node_version"] = self.node_version
        return d


@dataclass
class McpConfig:
    entrypoint: str
    transport: Literal["stdio", "sse"] = "stdio"
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    command: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "entrypoint": self.entrypoint,
            "transport": self.transport,
            "args": self.args,
            "env": self.env,
        }
        if self.command:
            d["command"] = self.command
        return d


@dataclass
class HostsConfig:
    claude_code: bool = True
    codex: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {"claude_code": self.claude_code, "codex": self.codex}


@dataclass
class SkillManifest:
    name: str
    version: str
    description: str
    author: str
    tags: List[str]
    runtime: RuntimeConfig
    mcp: McpConfig
    hosts: HostsConfig
    install_path: Optional[Path] = None

    # ------------------------------------------------------------------ #
    # Factory                                                              #
    # ------------------------------------------------------------------ #

    @classmethod
    def from_toml(cls, path: Path) -> "SkillManifest":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls._from_dict(data, path.parent)

    @classmethod
    def _from_dict(
        cls, data: Dict[str, Any], install_path: Optional[Path] = None
    ) -> "SkillManifest":
        skill = data["skill"]
        rt = data.get("runtime", {})
        mc = data.get("mcp", {})
        hc = data.get("hosts", {})

        return cls(
            name=skill["name"],
            version=skill["version"],
            description=skill["description"],
            author=skill.get("author", ""),
            tags=skill.get("tags", []),
            runtime=RuntimeConfig(
                type=rt.get("type", "python"),
                python_version=rt.get("python_version"),
                node_version=rt.get("node_version"),
                install_cmd=rt.get("install_cmd", ""),
            ),
            mcp=McpConfig(
                entrypoint=mc.get("entrypoint", "src/main.py"),
                transport=mc.get("transport", "stdio"),
                args=mc.get("args", []),
                env=mc.get("env", {}),
                command=mc.get("command"),
            ),
            hosts=HostsConfig(
                claude_code=hc.get("claude_code", True),
                codex=hc.get("codex", True),
            ),
            install_path=install_path,
        )

    # ------------------------------------------------------------------ #
    # Serialisation                                                        #
    # ------------------------------------------------------------------ #

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill": {
                "name": self.name,
                "version": self.version,
                "description": self.description,
                "author": self.author,
                "tags": self.tags,
            },
            "runtime": self.runtime.to_dict(),
            "mcp": self.mcp.to_dict(),
            "hosts": self.hosts.to_dict(),
        }

    def save(self, path: Optional[Path] = None) -> None:
        target = path or (
            self.install_path / "skill.toml" if self.install_path else None
        )
        if target is None:
            raise ValueError("No path specified for saving skill manifest.")
        with open(target, "wb") as f:
            tomli_w.dump(self.to_dict(), f)

    # ------------------------------------------------------------------ #
    # Derived paths                                                        #
    # ------------------------------------------------------------------ #

    @property
    def venv_path(self) -> Optional[Path]:
        return self.install_path / ".venv" if self.install_path else None

    @property
    def venv_python(self) -> Optional[Path]:
        """Return the path to the venv Python executable, or None if not built."""
        if not self.venv_path:
            return None
        for candidate in [
            self.venv_path / "bin" / "python",
            self.venv_path / "Scripts" / "python.exe",
        ]:
            if candidate.exists():
                return candidate
        return None

    @property
    def entrypoint_path(self) -> Optional[Path]:
        return (
            self.install_path / self.mcp.entrypoint if self.install_path else None
        )

    @property
    def env_ready(self) -> bool:
        return self.venv_python is not None

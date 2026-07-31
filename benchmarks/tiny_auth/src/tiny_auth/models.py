from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Role = Literal["member", "admin"]


@dataclass(frozen=True)
class User:
    user_id: str
    role: Role


@dataclass(frozen=True)
class Project:
    project_id: str
    owner_id: str
    is_private: bool

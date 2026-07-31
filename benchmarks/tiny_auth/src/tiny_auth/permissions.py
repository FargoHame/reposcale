from __future__ import annotations

from tiny_auth.models import Project, User


def can_view_project(user: User, project: Project) -> bool:
    if not project.is_private:
        return True

    return project.owner_id == user.user_id

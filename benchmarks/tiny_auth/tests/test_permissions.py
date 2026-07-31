from __future__ import annotations

from tiny_auth import Project, User, can_view_project


def test_public_project_can_be_seen_by_members() -> None:
    user = User(user_id="user-1", role="member")
    project = Project(project_id="project-1", owner_id="someone-else", is_private=False)

    assert can_view_project(user, project) is True


def test_private_project_can_be_seen_by_owner() -> None:
    user = User(user_id="owner-1", role="member")
    project = Project(project_id="project-1", owner_id="owner-1", is_private=True)

    assert can_view_project(user, project) is True


def test_private_project_can_be_seen_by_admin() -> None:
    user = User(user_id="admin-1", role="admin")
    project = Project(project_id="project-1", owner_id="owner-1", is_private=True)

    assert can_view_project(user, project) is True


def test_private_project_cannot_be_seen_by_other_member() -> None:
    user = User(user_id="user-1", role="member")
    project = Project(project_id="project-1", owner_id="owner-1", is_private=True)

    assert can_view_project(user, project) is False

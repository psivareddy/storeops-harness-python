"""programmes data access. In-memory; no business rules, no external calls."""

from __future__ import annotations

from datetime import UTC, datetime

from app.programmes.models import Project, ProjectMember, ProjectRole, ProjectStatus

_NOW = datetime(2026, 8, 31, 8, 0, tzinfo=UTC)


def _seed_projects() -> list[Project]:
    return [
        Project(
            id="project-1",
            name="Autumn seasonal rollout",
            store_id="store-101",
            description="Seasonal range changeover across grocery and household",
            status=ProjectStatus.ACTIVE,
            members=(
                ProjectMember(user_id="user-2", role=ProjectRole.STORE_MANAGER, added_at=_NOW),
                ProjectMember(user_id="user-3", role=ProjectRole.DEPARTMENT_LEAD, added_at=_NOW),
            ),
            created_at=_NOW,
        ),
        Project(
            id="project-2",
            name="Chilled compliance drive",
            store_id="store-101",
            description="Temperature compliance across all chilled units",
            status=ProjectStatus.PLANNED,
            members=(
                ProjectMember(user_id="user-2", role=ProjectRole.STORE_MANAGER, added_at=_NOW),
            ),
            created_at=_NOW,
        ),
        Project(
            id="project-3",
            name="Store 102 refit phase 1",
            store_id="store-102",
            description="Front-of-store refit",
            status=ProjectStatus.CLOSED,
            members=(
                ProjectMember(user_id="user-4", role=ProjectRole.DEPARTMENT_LEAD, added_at=_NOW),
            ),
            created_at=_NOW,
        ),
    ]


class ProjectRepository:
    """In-memory programme store keyed by project id."""

    def __init__(self) -> None:
        self._projects: dict[str, Project] = {}
        self.reset()

    def reset(self) -> None:
        self._projects = {project.id: project for project in _seed_projects()}

    def list_all(self, *, store_id: str | None = None) -> list[Project]:
        projects = list(self._projects.values())
        if store_id is not None:
            projects = [project for project in projects if project.store_id == store_id]
        return sorted(projects, key=lambda project: project.id)

    def get(self, project_id: str) -> Project | None:
        return self._projects.get(project_id)

    def replace(self, project: Project) -> Project:
        self._projects[project.id] = project
        return project

    def count(self) -> int:
        return len(self._projects)


project_repository = ProjectRepository()

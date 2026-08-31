"""programmes business logic.

Demonstrates the module boundary rule in its permitted direction: enrolling a member requires
verifying the staff member exists, so this service calls :class:`StaffService` -- the *service*
layer of the ``staff`` module -- and never ``app.staff.repository``. Going through the service
means staff keeps ownership of what "a valid user" means; importing the repository would freeze
that decision into programmes.
"""

from __future__ import annotations

from app.programmes.models import Project, ProjectMember, ProjectMemberCreate
from app.programmes.repository import ProjectRepository, project_repository
from app.shared.errors import DuplicateMemberError, ProjectNotFoundError, ValidationError
from app.shared.events import EventBus, EventName, event_bus
from app.shared.logging import get_logger
from app.staff.service import StaffService, staff_service

logger = get_logger(__name__)


class ProgrammesService:
    """Read and write operations for store programmes."""

    def __init__(
        self,
        repository: ProjectRepository | None = None,
        bus: EventBus | None = None,
        staff: StaffService | None = None,
    ) -> None:
        self._repository = repository if repository is not None else project_repository
        self._bus = bus if bus is not None else event_bus
        self._staff = staff if staff is not None else staff_service

    # -- reads ------------------------------------------------------------------
    def list_projects(self, *, store_id: str | None = None) -> list[Project]:
        return self._repository.list_all(store_id=store_id)

    def get_project(self, project_id: str) -> Project:
        """Return a programme or raise :class:`ProjectNotFoundError`.

        The read entry point sibling modules use -- ``reports`` calls this rather than importing
        ``ProjectRepository``.
        """
        project = self._repository.get(project_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        return project

    def projects_for_store(self, store_id: str) -> list[Project]:
        return self._repository.list_all(store_id=store_id)

    # -- writes -----------------------------------------------------------------
    def add_member(self, project_id: str, payload: ProjectMemberCreate) -> Project:
        """Enrol a staff member, publishing ``PROGRAMME_MEMBER_ADDED``.

        Raises :class:`ProjectNotFoundError`, :class:`~app.shared.errors.UserNotFoundError`
        (via the staff service), :class:`ValidationError` for a closed programme, or
        :class:`DuplicateMemberError`. No event is published on any failure path.
        """
        project = self.get_project(project_id)

        # Cross-module read through the staff SERVICE layer. Raises USER_NOT_FOUND if unknown.
        user = self._staff.get_user(payload.user_id)

        if project.status.value == "CLOSED":
            raise ValidationError(
                f"Programme '{project_id}' is closed and cannot accept new members",
                details={"projectId": project_id, "status": project.status.value},
            )
        if project.has_member(user.id):
            raise DuplicateMemberError(project_id, user.id)

        member = ProjectMember(user_id=user.id, role=payload.role)
        updated = project.model_copy(update={"members": (*project.members, member)})
        self._repository.replace(updated)
        self._bus.publish(
            EventName.PROGRAMME_MEMBER_ADDED,
            {
                "projectId": updated.id,
                "storeId": updated.store_id,
                "userId": member.user_id,
                "role": member.role.value,
            },
        )
        logger.info("User %s enrolled on project %s", member.user_id, project_id)
        return updated


programmes_service = ProgrammesService()

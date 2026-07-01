import uuid
from sqlalchemy import String, Boolean, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class RolePermission(Base):
    __tablename__ = "role_permissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role: Mapped[str] = mapped_column(String(50))
    page_key: Mapped[str] = mapped_column(String(100))
    can_view: Mapped[bool] = mapped_column(Boolean, default=True)
    can_create: Mapped[bool] = mapped_column(Boolean, default=False)
    can_update: Mapped[bool] = mapped_column(Boolean, default=False)
    can_delete: Mapped[bool] = mapped_column(Boolean, default=False)


class RoleBranchPermission(Base):
    __tablename__ = "role_branch_permissions"
    __table_args__ = (UniqueConstraint("role", "branch_id", name="uq_role_branch"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role: Mapped[str] = mapped_column(String(50))
    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    allowed: Mapped[bool] = mapped_column(Boolean, default=True)

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Dict, List

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin

Identifier = Annotated[str, mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))]


class PolicyType(str, Enum):
    PRICING = "pricing"
    DISCOUNT = "discount"
    PAYMENT_TERMS = "payment_terms"
    PRICE_FLOOR = "price_floor"
    APPROVAL_MATRIX = "approval_matrix"
    SLA = "sla"
    CUSTOM = "custom"


class PolicyStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    SUPERSEDED = "superseded"


class PolicyChangeType(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    VERSION_CREATED = "version_created"
    ROLLED_BACK = "rolled_back"


class Policy(TimestampMixin, Base):
    __tablename__ = "policies"

    id: Mapped[Identifier]
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_type: Mapped[PolicyType] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[PolicyStatus] = mapped_column(String(20), default=PolicyStatus.DRAFT, nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")

    # Policy configuration as JSON
    configuration: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)

    # Metadata
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # Higher priority overrides lower

    # Relationships
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Version tracking
    parent_policy_id: Mapped[str | None] = mapped_column(ForeignKey("policies.id"), nullable=True)

    # Template association
    template_id: Mapped[str | None] = mapped_column(ForeignKey("policy_templates.id"), nullable=True)

    # Metadata
    tags: Mapped[List[str] | None] = mapped_column(JSON, nullable=True)

    created_by: Mapped["User"] = relationship(back_populates="created_policies", foreign_keys=[created_by_id])
    approved_by: Mapped["User | None"] = relationship(back_populates="approved_policies", foreign_keys=[approved_by_id])

    # Self-referential relationships
    parent_policy: Mapped["Policy | None"] = relationship("Policy", remote_side=[id], foreign_keys=[parent_policy_id])
    child_policies: Mapped[List["Policy"]] = relationship("Policy", cascade="all,delete-orphan", foreign_keys=[parent_policy_id])

    template: Mapped["PolicyTemplate | None"] = relationship("PolicyTemplate", back_populates="policies")

    versions: Mapped[List["PolicyVersion"]] = relationship("PolicyVersion", cascade="all,delete-orphan", back_populates="policy")
    change_logs: Mapped[List["PolicyChangeLog"]] = relationship("PolicyChangeLog", cascade="all,delete-orphan", back_populates="policy")
    validations: Mapped[List["PolicyValidation"]] = relationship("PolicyValidation", cascade="all,delete-orphan", back_populates="policy")


class PolicyVersion(TimestampMixin, Base):
    __tablename__ = "policy_versions"

    id: Mapped[Identifier]
    policy_id: Mapped[str] = mapped_column(ForeignKey("policies.id"), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    configuration: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    policy: Mapped["Policy"] = relationship("Policy", back_populates="versions")
    created_by: Mapped["User"] = relationship("User")


class PolicyTemplate(TimestampMixin, Base):
    __tablename__ = "policy_templates"

    id: Mapped[Identifier]
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_type: Mapped[PolicyType] = mapped_column(String(50), nullable=False)
    template_configuration: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    schema_definition: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)  # JSON Schema for validation
    is_system_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tags: Mapped[List[str] | None] = mapped_column(JSON, nullable=True)

    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    created_by: Mapped["User"] = relationship("User")
    policies: Mapped[List["Policy"]] = relationship("Policy", cascade="all,delete-orphan", back_populates="template")


class PolicyChangeLog(TimestampMixin, Base):
    __tablename__ = "policy_change_logs"

    id: Mapped[Identifier]
    policy_id: Mapped[str] = mapped_column(ForeignKey("policies.id"), nullable=False)
    change_type: Mapped[PolicyChangeType] = mapped_column(String(20), nullable=False)
    old_configuration: Mapped[Dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    new_configuration: Mapped[Dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    change_summary: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    policy: Mapped["Policy"] = relationship("Policy", back_populates="change_logs")
    changed_by: Mapped["User"] = relationship("User")


class PolicyValidation(TimestampMixin, Base):
    __tablename__ = "policy_validations"

    id: Mapped[Identifier]
    policy_id: Mapped[str] = mapped_column(ForeignKey("policies.id"), nullable=False)
    validation_type: Mapped[str] = mapped_column(String(50), nullable=False)  # syntax, semantic, conflict, etc.
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # passed, failed, warning
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    policy: Mapped["Policy"] = relationship("Policy", back_populates="validations")


class PolicyConflict(TimestampMixin, Base):
    __tablename__ = "policy_conflicts"

    id: Mapped[Identifier]
    policy_1_id: Mapped[str] = mapped_column(ForeignKey("policies.id"), nullable=False)
    policy_2_id: Mapped[str] = mapped_column(ForeignKey("policies.id"), nullable=False)
    conflict_type: Mapped[str] = mapped_column(String(50), nullable=False)  # configuration, priority, scope
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)  # high, medium, low
    resolution_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    policy_1: Mapped["Policy"] = relationship("Policy", foreign_keys=[policy_1_id])
    policy_2: Mapped["Policy"] = relationship("Policy", foreign_keys=[policy_2_id])
    resolved_by: Mapped["User | None"] = relationship("User")


class PolicySimulation(TimestampMixin, Base):
    __tablename__ = "policy_simulations"

    id: Mapped[Identifier]
    policy_id: Mapped[str] = mapped_column(ForeignKey("policies.id"), nullable=False)
    simulation_type: Mapped[str] = mapped_column(String(50), nullable=False)  # historical, scenario, impact
    test_data: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    results: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    policy: Mapped["Policy"] = relationship("Policy")
    created_by: Mapped["User"] = relationship("User")
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.database import get_db
from app.api.dependencies.auth import get_current_user
from app.models.policy import (
    Policy,
    PolicyConflict,
    PolicySimulation,
    PolicyStatus,
    PolicyTemplate,
    PolicyType,
    PolicyValidation,
    PolicyVersion,
)
from app.models.user import User, UserRole
from app.services.policy_service import PolicyService

router = APIRouter(prefix="/policies", tags=["policies"])


# Pydantic models for API requests/responses
class PolicyConfigurationRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    policy_type: PolicyType
    configuration: Dict[str, Any]
    effective_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    priority: int = Field(default=0, ge=0)
    tags: Optional[List[str]] = None
    template_id: Optional[str] = None


class PolicyUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    configuration: Optional[Dict[str, Any]] = None
    effective_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    priority: Optional[int] = Field(None, ge=0)
    tags: Optional[List[str]] = None


class PolicyConfigurationResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    policy_type: str
    status: str
    version: str
    configuration: Dict[str, Any]
    effective_at: Optional[datetime]
    expires_at: Optional[datetime]
    priority: int
    tags: Optional[List[str]]
    created_at: datetime
    updated_at: datetime
    created_by: str  # User email
    approved_by: Optional[str] = None
    parent_policy_id: Optional[str]
    template_id: Optional[str]
    validations: List[Dict[str, Any]] = []
    conflict_count: int = 0

    class Config:
        from_attributes = True


class PolicyTemplateResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    policy_type: str
    template_configuration: Dict[str, Any]
    schema_definition: Dict[str, Any]
    is_system_template: bool
    tags: Optional[List[str]]
    created_at: datetime

    class Config:
        from_attributes = True


class PolicyValidationRequest(BaseModel):
    policy_type: PolicyType
    configuration: Dict[str, Any]


class PolicyValidationResponse(BaseModel):
    is_valid: bool
    errors: List[str]
    warnings: List[str] = []


class PolicySimulationRequest(BaseModel):
    test_deals: List[Dict[str, Any]]


class PolicySimulationResponse(BaseModel):
    id: str
    policy_id: str
    simulation_type: str
    results: Dict[str, Any]
    summary: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class PolicyVersionResponse(BaseModel):
    id: str
    policy_id: str
    version: str
    configuration: Dict[str, Any]
    change_summary: Optional[str]
    created_at: datetime
    created_by: str

    class Config:
        from_attributes = True


class PolicyConflictResponse(BaseModel):
    id: str
    policy_1_name: str
    policy_2_name: str
    conflict_type: str
    description: str
    severity: str
    resolution_suggestion: Optional[str]
    resolved_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


def _has_policy_management_permission(user: User) -> bool:
    """Check if user has permission to manage policies"""
    return UserRole.REVOPS_ADMIN in user.roles or UserRole.ADMIN in user.roles


def _policy_to_response(policy: Policy, db: Session) -> PolicyConfigurationResponse:
    """Convert Policy model to response DTO"""
    # Load related data
    validations = list(policy.validations)
    conflicts = db.execute(
        "SELECT COUNT(*) FROM policy_conflicts WHERE (policy_1_id = :policy_id OR policy_2_id = :policy_id) AND resolved_at IS NULL",
        {"policy_id": policy.id},
    ).scalar() or 0

    return PolicyConfigurationResponse(
        id=policy.id,
        name=policy.name,
        description=policy.description,
        policy_type=policy.policy_type,
        status=policy.status,
        version=policy.version,
        configuration=policy.configuration,
        effective_at=policy.effective_at,
        expires_at=policy.expires_at,
        priority=policy.priority,
        tags=policy.tags,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
        created_by=policy.created_by.email if policy.created_by else "Unknown",
        approved_by=policy.approved_by.email if policy.approved_by else None,
        parent_policy_id=policy.parent_policy_id,
        template_id=policy.template_id,
        validations=[
            {
                "validation_type": v.validation_type,
                "status": v.status,
                "message": v.message,
                "details": v.details,
            }
            for v in validations
        ],
        conflict_count=conflicts,
    )


# Policy Templates Endpoints
@router.get("/templates", response_model=List[PolicyTemplateResponse])
async def get_policy_templates(
    policy_type: Optional[PolicyType] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get available policy templates"""
    service = PolicyService(db)
    templates = service.get_templates(policy_type)

    return [
        PolicyTemplateResponse(
            id=template.id,
            name=template.name,
            description=template.description,
            policy_type=template.policy_type,
            template_configuration=template.template_configuration,
            schema_definition=template.schema_definition,
            is_system_template=template.is_system_template,
            tags=template.tags,
            created_at=template.created_at,
        )
        for template in templates
    ]


@router.get("/templates/{template_id}", response_model=PolicyTemplateResponse)
async def get_policy_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific policy template"""
    service = PolicyService(db)
    template = service.get_template_by_id(template_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Policy template not found"
        )

    return PolicyTemplateResponse(
        id=template.id,
        name=template.name,
        description=template.description,
        policy_type=template.policy_type,
        template_configuration=template.template_configuration,
        schema_definition=template.schema_definition,
        is_system_template=template.is_system_template,
        tags=template.tags,
        created_at=template.created_at,
    )


# Policy CRUD Endpoints
@router.get("/", response_model=List[PolicyConfigurationResponse])
async def get_policies(
    policy_type: Optional[PolicyType] = Query(None),
    status: Optional[PolicyStatus] = Query(None),
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get policies with optional filtering"""
    service = PolicyService(db)
    policies = service.get_policies(policy_type, status, include_inactive)

    return [_policy_to_response(policy, db) for policy in policies]


@router.get("/{policy_id}", response_model=PolicyConfigurationResponse)
async def get_policy(
    policy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific policy"""
    service = PolicyService(db)
    policy = service.get_policy_by_id(policy_id)

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found"
        )

    return _policy_to_response(policy, db)


@router.post("/", response_model=PolicyConfigurationResponse)
async def create_policy(
    policy_request: PolicyConfigurationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new policy"""
    if not _has_policy_management_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to create policies",
        )

    service = PolicyService(db)
    policy = service.create_policy(
        name=policy_request.name,
        policy_type=policy_request.policy_type,
        configuration=policy_request.configuration,
        created_by=current_user,
        description=policy_request.description,
        template_id=policy_request.template_id,
        effective_at=policy_request.effective_at,
        expires_at=policy_request.expires_at,
        priority=policy_request.priority,
        tags=policy_request.tags,
    )

    return _policy_to_response(policy, db)


@router.put("/{policy_id}", response_model=PolicyConfigurationResponse)
async def update_policy(
    policy_id: str,
    policy_request: PolicyUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update an existing policy"""
    if not _has_policy_management_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to update policies",
        )

    service = PolicyService(db)
    policy = service.get_policy_by_id(policy_id)

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found"
        )

    if policy_request.configuration is None:
        policy_request.configuration = policy.configuration

    updated_policy = service.update_policy(
        policy_id=policy_id,
        configuration=policy_request.configuration,
        updated_by=current_user,
        name=policy_request.name,
        description=policy_request.description,
        effective_at=policy_request.effective_at,
        expires_at=policy_request.expires_at,
        priority=policy_request.priority,
        tags=policy_request.tags,
    )

    return _policy_to_response(updated_policy, db)


@router.post("/{policy_id}/activate", response_model=PolicyConfigurationResponse)
async def activate_policy(
    policy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Activate a policy"""
    if not _has_policy_management_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to activate policies",
        )

    service = PolicyService(db)
    policy = service.activate_policy(policy_id, current_user)

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found"
        )

    return _policy_to_response(policy, db)


@router.post("/{policy_id}/deactivate", response_model=PolicyConfigurationResponse)
async def deactivate_policy(
    policy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deactivate a policy"""
    if not _has_policy_management_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to deactivate policies",
        )

    service = PolicyService(db)
    policy = service.deactivate_policy(policy_id, current_user)

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found"
        )

    return _policy_to_response(policy, db)


# Policy Versioning Endpoints
@router.get("/{policy_id}/versions", response_model=List[PolicyVersionResponse])
async def get_policy_versions(
    policy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get policy version history"""
    service = PolicyService(db)
    versions = service.get_policy_versions(policy_id)

    return [
        PolicyVersionResponse(
            id=version.id,
            policy_id=version.policy_id,
            version=version.version,
            configuration=version.configuration,
            change_summary=version.change_summary,
            created_at=version.created_at,
            created_by=version.created_by.email if version.created_by else "Unknown",
        )
        for version in versions
    ]


@router.post("/{policy_id}/rollback/{version}", response_model=PolicyConfigurationResponse)
async def rollback_policy(
    policy_id: str,
    version: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rollback policy to a specific version"""
    if not _has_policy_management_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to rollback policies",
        )

    service = PolicyService(db)
    policy = service.rollback_policy(policy_id, version, current_user)

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Policy or version not found",
        )

    return _policy_to_response(policy, db)


# Policy Validation Endpoints
@router.post("/validate", response_model=PolicyValidationResponse)
async def validate_policy_configuration(
    validation_request: PolicyValidationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Validate policy configuration without saving"""
    service = PolicyService(db)
    errors = service.validate_policy_configuration(
        validation_request.policy_type, validation_request.configuration
    )

    return PolicyValidationResponse(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=[],
    )


@router.get("/{policy_id}/validations")
async def get_policy_validations(
    policy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get policy validation results"""
    policy = db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found"
        )

    validations = list(policy.validations)
    return [
        {
            "id": v.id,
            "validation_type": v.validation_type,
            "status": v.status,
            "message": v.message,
            "details": v.details,
            "created_at": v.created_at,
        }
        for v in validations
    ]


# Policy Conflict Endpoints
@router.get("/{policy_id}/conflicts", response_model=List[PolicyConflictResponse])
async def get_policy_conflicts(
    policy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get policy conflicts"""
    conflicts = db.execute(
        """
        SELECT pc.*, p1.name as policy_1_name, p2.name as policy_2_name
        FROM policy_conflicts pc
        JOIN policies p1 ON pc.policy_1_id = p1.id
        JOIN policies p2 ON pc.policy_2_id = p2.id
        WHERE (pc.policy_1_id = :policy_id OR pc.policy_2_id = :policy_id)
        AND pc.resolved_at IS NULL
        ORDER BY pc.severity DESC, pc.created_at DESC
        """,
        {"policy_id": policy_id},
    ).all()

    return [
        PolicyConflictResponse(
            id=conflict.id,
            policy_1_name=conflict.policy_1_name,
            policy_2_name=conflict.policy_2_name,
            conflict_type=conflict.conflict_type,
            description=conflict.description,
            severity=conflict.severity,
            resolution_suggestion=conflict.resolution_suggestion,
            resolved_at=conflict.resolved_at,
            created_at=conflict.created_at,
        )
        for conflict in conflicts
    ]


# Policy Simulation Endpoints
@router.post("/{policy_id}/simulate", response_model=PolicySimulationResponse)
async def simulate_policy_impact(
    policy_id: str,
    simulation_request: PolicySimulationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Simulate policy impact against test deals"""
    if not _has_policy_management_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to simulate policies",
        )

    service = PolicyService(db)
    simulation = service.simulate_policy_impact(
        policy_id, simulation_request.test_deals, current_user
    )

    return PolicySimulationResponse(
        id=simulation.id,
        policy_id=simulation.policy_id,
        simulation_type=simulation.simulation_type,
        results=simulation.results,
        summary=simulation.summary,
        created_at=simulation.created_at,
    )


@router.get("/{policy_id}/simulations", response_model=List[PolicySimulationResponse])
async def get_policy_simulations(
    policy_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get policy simulation history"""
    simulations = db.execute(
        select(PolicySimulation)
        .where(PolicySimulation.policy_id == policy_id)
        .order_by(PolicySimulation.created_at.desc())
        .limit(10)
    ).scalars().all()

    return [
        PolicySimulationResponse(
            id=sim.id,
            policy_id=sim.policy_id,
            simulation_type=sim.simulation_type,
            results=sim.results,
            summary=sim.summary,
            created_at=sim.created_at,
        )
        for sim in simulations
    ]


# Migration Endpoints
@router.post("/migrate-json", response_model=List[PolicyConfigurationResponse])
async def migrate_json_policies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Migrate existing JSON policies to database"""
    if not _has_policy_management_permission(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to migrate policies",
        )

    service = PolicyService(db)
    migrated_policies = service.migrate_json_policies(current_user)

    return [_policy_to_response(policy, db) for policy in migrated_policies]


# Export/Import Endpoints
@router.get("/{policy_id}/export")
async def export_policy(
    policy_id: str,
    format: str = Query("json", regex="^(json|yaml)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export policy configuration"""
    service = PolicyService(db)
    policy = service.get_policy_by_id(policy_id)

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found"
        )

    export_data = {
        "name": policy.name,
        "description": policy.description,
        "policy_type": policy.policy_type,
        "configuration": policy.configuration,
        "version": policy.version,
        "exported_at": datetime.utcnow().isoformat(),
        "exported_by": current_user.email,
    }

    if format == "yaml":
        import yaml
        content = yaml.dump(export_data, default_flow_style=False)
        media_type = "application/x-yaml"
    else:
        import json
        content = json.dumps(export_data, indent=2)
        media_type = "application/json"

    from fastapi.responses import Response
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename={policy.name.replace(' ', '_')}_policy.{format}"
        },
    )
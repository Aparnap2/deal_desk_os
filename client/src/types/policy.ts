export enum PolicyType {
  PRICING = 'pricing',
  DISCOUNT = 'discount',
  PAYMENT_TERMS = 'payment_terms',
  PRICE_FLOOR = 'price_floor',
  APPROVAL_MATRIX = 'approval_matrix',
  SLA = 'sla',
  CUSTOM = 'custom'
}

export enum PolicyStatus {
  DRAFT = 'draft',
  ACTIVE = 'active',
  INACTIVE = 'inactive',
  ARCHIVED = 'archived',
  SUPERSEDED = 'superseded'
}

export enum PolicyChangeType {
  CREATED = 'created',
  UPDATED = 'updated',
  DELETED = 'deleted',
  ACTIVATED = 'activated',
  DEACTIVATED = 'deactivated',
  VERSION_CREATED = 'version_created',
  ROLLED_BACK = 'rolled_back'
}

export interface PolicyTemplate {
  id: string;
  name: string;
  description?: string;
  policy_type: PolicyType;
  template_configuration: Record<string, any>;
  schema_definition: Record<string, any>;
  is_system_template: boolean;
  tags?: string[];
  created_at: string;
}

export interface Policy {
  id: string;
  name: string;
  description?: string;
  policy_type: PolicyType;
  status: PolicyStatus;
  version: string;
  configuration: Record<string, any>;
  effective_at?: string;
  expires_at?: string;
  priority: number;
  tags?: string[];
  created_at: string;
  updated_at: string;
  created_by: string;
  approved_by?: string;
  parent_policy_id?: string;
  template_id?: string;
  validations: PolicyValidation[];
  conflict_count: number;
}

export interface PolicyValidation {
  validation_type: string;
  status: string;
  message: string;
  details?: Record<string, any>;
}

export interface PolicyVersion {
  id: string;
  policy_id: string;
  version: string;
  configuration: Record<string, any>;
  change_summary?: string;
  created_at: string;
  created_by: string;
}

export interface PolicyConflict {
  id: string;
  policy_1_name: string;
  policy_2_name: string;
  conflict_type: string;
  description: string;
  severity: string;
  resolution_suggestion?: string;
  resolved_at?: string;
  created_at: string;
}

export interface PolicySimulation {
  id: string;
  policy_id: string;
  simulation_type: string;
  results: Record<string, any>;
  summary?: string;
  created_at: string;
}

export interface PolicyChangeLog {
  id: string;
  policy_id: string;
  change_type: PolicyChangeType;
  old_configuration?: Record<string, any>;
  new_configuration?: Record<string, any>;
  change_summary: string;
  reason?: string;
  changed_by: string;
  created_at: string;
}

export interface PolicyConfigurationRequest {
  name: string;
  description?: string;
  policy_type: PolicyType;
  configuration: Record<string, any>;
  effective_at?: string;
  expires_at?: string;
  priority?: number;
  tags?: string[];
  template_id?: string;
}

export interface PolicyUpdateRequest {
  name?: string;
  description?: string;
  configuration?: Record<string, any>;
  effective_at?: string;
  expires_at?: string;
  priority?: number;
  tags?: string[];
}

export interface PolicyValidationRequest {
  policy_type: PolicyType;
  configuration: Record<string, any>;
}

export interface PolicyValidationResponse {
  is_valid: boolean;
  errors: string[];
  warnings?: string[];
}

export interface PolicySimulationRequest {
  test_deals: Array<{
    id?: string;
    name?: string;
    amount: number;
    discount_percent: number;
    payment_terms_days: number;
    risk: 'low' | 'medium' | 'high';
  }>;
}

export interface PolicyFilterOptions {
  policy_type?: PolicyType;
  status?: PolicyStatus;
  include_inactive?: boolean;
}
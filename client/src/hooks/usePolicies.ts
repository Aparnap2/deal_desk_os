import { useState, useEffect } from 'react';
import { apiClient } from '../lib/api';
import {
  Policy,
  PolicyTemplate,
  PolicyType,
  PolicyStatus,
  PolicyVersion,
  PolicyConflict,
  PolicySimulation,
  PolicyConfigurationRequest,
  PolicyUpdateRequest,
  PolicyValidationRequest,
  PolicyValidationResponse,
  PolicySimulationRequest,
  PolicyFilterOptions
} from '../types/policy';

export function usePolicies(filters?: PolicyFilterOptions) {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPolicies = async () => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams();
      if (filters?.policy_type) params.append('policy_type', filters.policy_type);
      if (filters?.status) params.append('status', filters.status);
      if (filters?.include_inactive) params.append('include_inactive', 'true');

      const response = await apiClient.get(`/policies?${params}`);
      setPolicies(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch policies');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPolicies();
  }, [filters?.policy_type, filters?.status, filters?.include_inactive]);

  const createPolicy = async (data: PolicyConfigurationRequest): Promise<Policy> => {
    const response = await apiClient.post('/policies', data);
    setPolicies(prev => [response.data, ...prev]);
    return response.data;
  };

  const updatePolicy = async (id: string, data: PolicyUpdateRequest): Promise<Policy> => {
    const response = await apiClient.put(`/policies/${id}`, data);
    setPolicies(prev => prev.map(p => p.id === id ? response.data : p));
    return response.data;
  };

  const activatePolicy = async (id: string): Promise<Policy> => {
    const response = await apiClient.post(`/policies/${id}/activate`);
    setPolicies(prev => prev.map(p => p.id === id ? response.data : p));
    return response.data;
  };

  const deactivatePolicy = async (id: string): Promise<Policy> => {
    const response = await apiClient.post(`/policies/${id}/deactivate`);
    setPolicies(prev => prev.map(p => p.id === id ? response.data : p));
    return response.data;
  };

  const deletePolicy = async (id: string): Promise<void> => {
    await apiClient.delete(`/policies/${id}`);
    setPolicies(prev => prev.filter(p => p.id !== id));
  };

  return {
    policies,
    loading,
    error,
    fetchPolicies,
    createPolicy,
    updatePolicy,
    activatePolicy,
    deactivatePolicy,
    deletePolicy,
  };
}

export function usePolicyTemplates(policyType?: PolicyType) {
  const [templates, setTemplates] = useState<PolicyTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTemplates = async () => {
    setLoading(true);
    setError(null);

    try {
      const params = new URLSearchParams();
      if (policyType) params.append('policy_type', policyType);

      const response = await apiClient.get(`/policies/templates?${params}`);
      setTemplates(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch templates');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTemplates();
  }, [policyType]);

  return {
    templates,
    loading,
    error,
    fetchTemplates,
  };
}

export function usePolicy(policyId: string | null) {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPolicy = async () => {
    if (!policyId) return;

    setLoading(true);
    setError(null);

    try {
      const response = await apiClient.get(`/policies/${policyId}`);
      setPolicy(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch policy');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPolicy();
  }, [policyId]);

  return {
    policy,
    loading,
    error,
    fetchPolicy,
  };
}

export function usePolicyVersions(policyId: string | null) {
  const [versions, setVersions] = useState<PolicyVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchVersions = async () => {
    if (!policyId) return;

    setLoading(true);
    setError(null);

    try {
      const response = await apiClient.get(`/policies/${policyId}/versions`);
      setVersions(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch versions');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchVersions();
  }, [policyId]);

  const rollbackPolicy = async (version: string): Promise<Policy> => {
    if (!policyId) throw new Error('Policy ID is required');

    const response = await apiClient.post(`/policies/${policyId}/rollback/${version}`);
    return response.data;
  };

  return {
    versions,
    loading,
    error,
    fetchVersions,
    rollbackPolicy,
  };
}

export function usePolicyConflicts(policyId: string | null) {
  const [conflicts, setConflicts] = useState<PolicyConflict[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchConflicts = async () => {
    if (!policyId) return;

    setLoading(true);
    setError(null);

    try {
      const response = await apiClient.get(`/policies/${policyId}/conflicts`);
      setConflicts(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch conflicts');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConflicts();
  }, [policyId]);

  return {
    conflicts,
    loading,
    error,
    fetchConflicts,
  };
}

export function usePolicyValidation() {
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const validateConfiguration = async (request: PolicyValidationRequest): Promise<PolicyValidationResponse> => {
    setValidating(true);
    setError(null);

    try {
      const response = await apiClient.post('/policies/validate', request);
      return response.data;
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 'Validation failed';
      setError(errorMessage);
      throw new Error(errorMessage);
    } finally {
      setValidating(false);
    }
  };

  return {
    validateConfiguration,
    validating,
    error,
  };
}

export function usePolicySimulation(policyId: string | null) {
  const [simulations, setSimulations] = useState<PolicySimulation[]>([]);
  const [loading, setLoading] = useState(false);
  const [simulating, setSimulating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSimulations = async () => {
    if (!policyId) return;

    setLoading(true);
    setError(null);

    try {
      const response = await apiClient.get(`/policies/${policyId}/simulations`);
      setSimulations(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to fetch simulations');
    } finally {
      setLoading(false);
    }
  };

  const runSimulation = async (request: PolicySimulationRequest): Promise<PolicySimulation> => {
    if (!policyId) throw new Error('Policy ID is required');

    setSimulating(true);
    setError(null);

    try {
      const response = await apiClient.post(`/policies/${policyId}/simulate`, request);
      setSimulations(prev => [response.data, ...prev]);
      return response.data;
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || 'Simulation failed';
      setError(errorMessage);
      throw new Error(errorMessage);
    } finally {
      setSimulating(false);
    }
  };

  useEffect(() => {
    fetchSimulations();
  }, [policyId]);

  return {
    simulations,
    loading,
    simulating,
    error,
    fetchSimulations,
    runSimulation,
  };
}
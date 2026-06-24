/**
 * Access engine admin client (Phase 2).
 *
 * Talks to /api/access/* (the centralized ResourceAccessGrant engine) using the
 * shared, auth-configured axios instance. Mirrors the conventions of the other
 * api groups in lib/api.ts but isolated here to keep that file focused.
 */
import api from "@/lib/api";

export type GrantScope = "SUBJECT" | "RESOURCE";
/** Math / Reading / Both choice for Past Paper / Practice-test packs. */
export type SubjectScope = "math" | "reading" | "both";

/** Resource types that expand to subject sections, so a Math/Reading/Both choice applies. */
export const SUBJECT_SCOPED_TYPES = new Set(["practice_test_pack"]);
/** Resource types intentionally hidden from the access-console picker.
 *  practice_test IS shown now: pastpaper packs were removed, so standalone sections
 *  (grouped by collection_name) are granted individually. module/assessment_set stay
 *  hidden (granted indirectly / not assignable from this console). */
export const HIDDEN_PICKER_TYPES = new Set(["module", "assessment_set"]);
export type GrantStatus = "ACTIVE" | "REVOKED" | "EXPIRED";
export type GrantSource = "MANUAL" | "BULK" | "CLASSROOM" | "PURCHASE" | "SYSTEM";

export type ResourceAccessGrant = {
  id: number;
  user: number;
  user_email: string;
  user_name: string;
  scope: GrantScope;
  subject: string | null;
  resource_type: string | null;
  resource_id: number | null;
  /** Human-readable resource name (e.g. "March 2024 · MATH"); "" for subject grants. */
  resource_label: string;
  classroom: number | null;
  classroom_name: string;
  source: GrantSource;
  status: GrantStatus;
  is_effective: boolean;
  granted_by: number | null;
  granted_by_email: string;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
};

export type GrantEvent = {
  id: number;
  grant: number;
  action: string;
  actor: number | null;
  actor_email: string;
  note: string;
  snapshot: Record<string, unknown>;
  created_at: string;
};

export type ResourcePickerItem = {
  resource_type: string;
  resource_id: number;
  label: string;
  subjects: string[];
  published: boolean;
  /** Grouping label for the picker (former pastpaper pack title); "" if ungrouped. */
  group?: string;
};

export type BulkResult = {
  requested: number;
  created: number;
  skipped: number;
  grant_ids: number[];
  classroom_id?: number;
  resource_type?: string;
  resource_id?: number;
};

export type GrantListResponse = {
  count: number;
  next: string | null;
  previous: string | null;
  results: ResourceAccessGrant[];
};

export type GrantFilters = {
  q?: string;
  user?: number;
  scope?: GrantScope | "";
  status?: GrantStatus | "";
  source?: GrantSource | "";
  resource_type?: string;
  resource_id?: number;
  classroom?: number;
  page?: number;
  page_size?: number;
};

function listOf<T>(data: unknown): T[] {
  if (Array.isArray(data)) return data as T[];
  const obj = data as { results?: T[]; items?: T[] } | null;
  if (obj?.results) return obj.results;
  if (obj?.items) return obj.items;
  return [];
}

export type GrantResourceItem = {
  resource_type: string;
  resource_id: number;
  subject_scope?: SubjectScope;
};

export const accessApi = {
  listGrants: async (filters: GrantFilters = {}): Promise<GrantListResponse> => {
    const params: Record<string, string | number> = {};
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") params[k] = v as string | number;
    });
    const r = await api.get("/access/grants/", { params });
    const d = r.data;
    if (Array.isArray(d)) return { count: d.length, next: null, previous: null, results: d };
    return d as GrantListResponse;
  },

  grantSubject: async (payload: {
    user_ids: number[];
    subject: string;
    expires_at?: string | null;
  }): Promise<BulkResult> => {
    const r = await api.post("/access/grants/subject/", payload);
    return r.data as BulkResult;
  },

  grantResource: async (payload: {
    user_ids: number[];
    resource_type: string;
    resource_id: number;
    subject_scope?: SubjectScope;
    expires_at?: string | null;
  }): Promise<BulkResult> => {
    const r = await api.post("/access/grants/resource/", payload);
    return r.data as BulkResult;
  },

  grantClassroom: async (payload: {
    classroom_id: number;
    resource_type: string;
    resource_id: number;
    subject_scope?: SubjectScope;
    expires_at?: string | null;
  }): Promise<BulkResult> => {
    const r = await api.post("/access/grants/classroom/", payload);
    return r.data as BulkResult;
  },

  // Many-to-many: grant several resources to many students in one call.
  grantResources: async (payload: {
    user_ids: number[];
    resources: GrantResourceItem[];
    expires_at?: string | null;
  }): Promise<BulkResult> => {
    const r = await api.post("/access/grants/resource/", payload);
    return r.data as BulkResult;
  },

  // Many resources → every student in a classroom (transactional).
  grantClassroomResources: async (payload: {
    classroom_id: number;
    resources: GrantResourceItem[];
    expires_at?: string | null;
  }): Promise<BulkResult> => {
    const r = await api.post("/access/grants/classroom/", payload);
    return r.data as BulkResult;
  },

  revoke: async (grantId: number, note = ""): Promise<ResourceAccessGrant> => {
    const r = await api.post(`/access/grants/${grantId}/revoke/`, { note });
    return r.data as ResourceAccessGrant;
  },

  extend: async (grantId: number, expiresAt: string | null, note = ""): Promise<ResourceAccessGrant> => {
    const r = await api.post(`/access/grants/${grantId}/extend/`, { expires_at: expiresAt, note });
    return r.data as ResourceAccessGrant;
  },

  events: async (grantId: number): Promise<GrantEvent[]> => {
    const r = await api.get(`/access/grants/${grantId}/events/`);
    return listOf<GrantEvent>(r.data);
  },

  resourceTypes: async (): Promise<string[]> => {
    const r = await api.get("/access/resource-types/");
    return listOf<string>(r.data);
  },

  searchResources: async (type: string, q = "", limit = 30): Promise<ResourcePickerItem[]> => {
    const r = await api.get("/access/resources/", { params: { type, q, limit } });
    return listOf<ResourcePickerItem>(r.data);
  },
};

export const RESOURCE_TYPE_LABELS: Record<string, string> = {
  practice_test: "Practice / Past paper section",
  mock_exam: "Mock exam",
  midterm: "Midterm",
  practice_test_pack: "Practice test pack",
  assessment_set: "Assessment set",
  module: "Module",
};

export function resourceTypeLabel(rt: string): string {
  return RESOURCE_TYPE_LABELS[rt] ?? rt;
}

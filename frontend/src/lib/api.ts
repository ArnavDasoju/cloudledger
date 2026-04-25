const API = process.env.NEXT_PUBLIC_API_URL || "";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export const api = {
  health: () => get<{ status: string }>("/api/health"),
  getPeriods: () => get<{ periods: string[] }>("/api/periods"),

  uploadCSV: async (files: File[]) => {
    const form = new FormData();
    for (const f of files) form.append("files", f);
    const res = await fetch(`${API}/api/upload`, { method: "POST", body: form });
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    return res.json() as Promise<{ rows_inserted: number; rows_skipped: number; files_count: number }>;
  },

  uploadTerraform: async (files: File[]) => {
    const form = new FormData();
    for (const f of files) form.append("files", f);
    const res = await fetch(`${API}/api/upload/terraform`, { method: "POST", body: form });
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    return res.json() as Promise<{ resources_parsed: number; files_count: number }>;
  },

  runPipeline: (prior: string, current: string) =>
    fetch(`${API}/api/pipeline/run?prior_period=${prior}&current_period=${current}`, { method: "POST" })
      .then(r => { if (!r.ok) throw new Error(`Pipeline failed: ${r.status}`); return r.json(); }),

  getBillOverview: (prior: string, current: string) =>
    get<{ prior_total: number; current_total: number; delta: number; prior_period: string; current_period: string }>(
      `/api/bill-overview?prior_period=${prior}&current_period=${current}`
    ),

  getIngestionStats: (current: string) =>
    get<{
      billing_rows: number;
      current_period_rows: number;
      resource_count: number;
      terraform_resources: number;
      terraform_matched_cost: number;
      terraform_unmatched_cost: number;
      total_cost: number;
      coverage_pct: number;
      unattributed: number;
      period_breakdown: { period: string; rows: number; cost: number; unique_resources: number }[];
      data_quality: { missing_resource_id: number; missing_service: number; zero_cost_lines: number; negative_cost_lines: number };
      tag_coverage: { tagged_resources: number; tagged_cost: number; total_resources: number; total_cost: number };
      services: { service: string; rows: number; cost: number; resources: number; terraform_matched: number }[];
      top_unmatched: { resource_id: string; resource_name: string | null; service: string | null; cost: number }[];
      detected_providers: string[];
    }>(`/api/ingestion-stats?current_period=${current}`),

  getVarianceByService: (current: string) =>
    get<{
      services: { service: string; delta: number; abs_delta: number; count: number; prior_cost: number; current_cost: number }[];
      resources: { resource_id: string; resource_name: string | null; service: string; prior_cost: number; current_cost: number; delta: number; delta_pct: number; reason_code: string; in_terraform: boolean; evidence: string | null; team: string | null }[];
      reasons: { code: string; delta: number; abs_delta: number; count: number }[];
      total_variance: number;
      total_increases: number;
      total_decreases: number;
      net_change: number;
    }>(`/api/variance-by-service?current_period=${current}`),

  getRootCauses: (current: string) =>
    get<{
      planned: { amount: number; delta: number; count: number; top_resources: { resource_id: string; resource_name: string | null; service: string; delta: number; prior_cost: number; current_cost: number; reason_code: string; evidence: string | null; in_terraform: boolean; team: string | null }[] };
      drift: { amount: number; delta: number; count: number; top_resources: { resource_id: string; resource_name: string | null; service: string; delta: number; prior_cost: number; current_cost: number; reason_code: string; evidence: string | null; in_terraform: boolean; team: string | null }[] };
      usage: { amount: number; delta: number; count: number; top_resources: { resource_id: string; resource_name: string | null; service: string; delta: number; prior_cost: number; current_cost: number; reason_code: string; evidence: string | null; in_terraform: boolean; team: string | null }[] };
      edge_cases: { amount: number; delta: number; count: number; top_resources: { resource_id: string; resource_name: string | null; service: string; delta: number; prior_cost: number; current_cost: number; reason_code: string; evidence: string | null; in_terraform: boolean; team: string | null }[] };
      all_reasons: { code: string; delta: number; abs_delta: number; count: number }[];
    }>(`/api/root-causes?current_period=${current}`),

  getClosePacket: (current: string, prior?: string) =>
    get<{
      prior_cost: number;
      total_cost: number;
      net_variance: number;
      total_variance: number;
      reasons: { code: string; delta: number; abs_delta: number; count: number; top_resources: { name: string; delta: number; service: string }[] }[];
      resource_count: number;
      managed_count: number;
      managed_cost: number;
      action_items: { resource_name: string; service: string; delta: number; reason: string; action: string }[];
    }>(`/api/close-packet?current_period=${current}${prior ? `&prior_period=${prior}` : ""}`),

  getEngineeringView: (current: string) =>
    get<{
      managed_count: number; unmanaged_count: number; managed_cost: number; unmanaged_cost: number; total_cost: number;
      planned_count: number; planned_total: number; drift_count: number; drift_total: number;
      drift_resources: { resource_name: string; service: string; current_cost: number; delta: number; reason_code: string; team: string | null; iac_source: string }[];
      iac_sources: { source: string; count: number; cost: number }[];
      teams: { team: string; count: number; cost: number; managed: number; delta: number }[];
      total_resources: number;
    }>(`/api/engineering-view?current_period=${current}`),

  getTrends: () => get<{
    totals: { period: string; cost: number }[];
    by_service: Record<string, { period: string; cost: number; resources: number }[]>;
    variances: { prior_period: string; current_period: string; net_change: number; total_variance: number; by_reason: Record<string, { delta: number; abs_delta: number; count: number }> }[];
    anomalies: { period: string; resource_name: string; service: string; delta: number; delta_pct: number; reason: string }[];
  }>("/api/trends"),

  getGithubStatus: () => get<{ configured: boolean; repo: string | null; events_synced: number }>("/api/github/status"),

  syncGithub: async (period?: string) => {
    const url = period ? `${API}/api/github/sync?billing_period=${period}` : `${API}/api/github/sync`;
    const res = await fetch(url, { method: "POST" });
    if (!res.ok) throw new Error(`GitHub sync failed: ${res.status}`);
    return res.json() as Promise<{ prs_found: number; tf_prs: number; events_created: number; resources_matched: number }>;
  },

  runPipelineAll: async () => {
    const res = await fetch(`${API}/api/pipeline/run-all`, { method: "POST" });
    if (!res.ok) throw new Error(`Pipeline failed: ${res.status}`);
    return res.json() as Promise<{ periods: string[]; variance_runs: number }>;
  },

  connectAWS: async (accessKey: string, secretKey: string, region: string, months: number) => {
    const res = await fetch(`${API}/api/connect/aws`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_key: accessKey, secret_key: secretKey, region, months }),
    });
    if (!res.ok) { const t = await res.text(); throw new Error(t || `AWS connect failed: ${res.status}`); }
    return res.json() as Promise<{ rows_inserted: number; files: number; provider: string }>;
  },

  connectAzure: async (subscriptionId: string, tenantId: string, clientId: string, clientSecret: string, months: number) => {
    const res = await fetch(`${API}/api/connect/azure`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subscription_id: subscriptionId, tenant_id: tenantId, client_id: clientId, client_secret: clientSecret, months }),
    });
    if (!res.ok) { const t = await res.text(); throw new Error(t || `Azure connect failed: ${res.status}`); }
    return res.json() as Promise<{ rows_inserted: number; files: number; provider: string }>;
  },

  glExportUrl: (current: string) => `${API}/api/gl-export?current_period=${current}`,
  pdfExportUrl: (current: string, prior: string) =>
    `${API}/api/close-packet/pdf?current_period=${current}&prior_period=${prior}`,

  sendChat: async (message: string, screen: string, screenData: unknown, history: { role: string; content: string }[]) => {
    const res = await fetch(`${API}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, screen, screen_data: screenData, history }),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || `Chat failed: ${res.status}`);
    }
    return res.json() as Promise<{ reply: string }>;
  },
};

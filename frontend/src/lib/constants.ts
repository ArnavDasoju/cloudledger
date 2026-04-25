export const C = {
  bg: "#F5F1EB",
  card: "#FFFFFF",
  accent: "#C9633A",
  accentLight: "#E8A07A",
  text: "#2D2D2D",
  muted: "#999999",
  border: "#E8E6DE",
  green: "#2FA84F",
  red: "#D94444",
} as const;

export const SCREEN_NAMES = [
  "Upload", "Overview", "Ingestion", "Variance",
  "Root Causes", "Close Packet", "Engineering", "Trends",
];

export const SCREEN_DESC: Record<number, string> = {
  0: "Upload your billing CSVs and Terraform state to begin analysis.",
  1: "High-level view of month-over-month cloud spend and where variance is concentrated.",
  2: "Data quality checks on your uploaded files — what was parsed, matched, and flagged.",
  3: "Every resource that changed cost, with direction, magnitude, and classification.",
  4: "Why costs changed — grouped by planned changes, drift, usage, and edge cases.",
  5: "CFO-ready summary with variance breakdown, action items, and export options.",
  6: "Infrastructure-as-Code coverage, team attribution, and drift resource inventory.",
  7: "Multi-period cost trends, per-service analysis, and anomaly detection over time.",
};

export const REASON_EXPLAIN: Record<string, string> = {
  planned: "This cost change was expected — the resource is managed by Terraform and a matching change event (PR/apply) was found within the billing window.",
  orphan_sdk_created: "This resource has team tags but is not in any IaC state file. It was likely created via the console, CLI, or SDK outside of Terraform.",
  orphan_unknown: "This resource has no team tags and is not in any IaC state. Its origin is unknown — it may be a leftover from a deleted project or a manual creation.",
  legacy_untracked: "A low-cost resource that existed before IaC adoption. It predates your Terraform state and was never imported.",
  non_terraform_iac: "Managed by a non-Terraform IaC tool (CloudFormation, CDK, Pulumi, or ARM). Tags indicate IaC management but it's not in the uploaded .tfstate.",
  usage_growth: "This resource is managed by Terraform but has no recent change event. The cost increase is from organic usage growth (more traffic, storage, etc.).",
  new_resource: "This resource appears in the current month but not the prior month. It was newly provisioned during this billing period.",
  removed_resource: "This resource existed last month but is absent this month. It was deprovisioned or deleted.",
  price_change: "The resource is managed and usage is stable, but the unit price changed — likely a pricing update, tier shift, or commitment expiration.",
  steady_state: "This resource's cost is within normal month-length variation. After adjusting for the different number of days in each month, the actual change is negligible — no action needed.",
  drift: "General infrastructure drift — a change happened outside of IaC that affected cost.",
  savings_plan_allocation: "Cost movement from Savings Plan coverage changes — committed spend was reallocated across resources.",
  ri_coverage_shift: "Reserved Instance coverage shifted between resources, changing the effective cost allocation.",
  credit_applied: "A credit, refund, or bundled discount was applied to this resource, creating a negative cost delta.",
  cross_service_transfer: "Data transfer costs between services or regions. Often appears as NAT Gateway, CloudFront, or inter-AZ traffic.",
  spot_price_volatility: "Spot instance pricing fluctuation. Cost varies based on real-time market demand for spare capacity.",
  marketplace_subscription: "AWS/Azure Marketplace subscription cost. Billed through the cloud provider but paid to a third-party vendor.",
};

export const CLOUDLY_SUGGESTIONS: Record<string, string[]> = {
  Overview: ["What drove the biggest cost increase this month?", "Is this month's spend normal compared to prior?", "Which services should I investigate first?"],
  Ingestion: ["Are there any data quality issues I should worry about?", "Why aren't my resources matching Terraform?", "What percentage of spend is untagged?"],
  Variance: ["Which resources had the largest unexpected cost changes?", "Summarize the drift resources for me.", "What's the difference between orphan_sdk_created and orphan_unknown?"],
  "Root Causes": ["What's the single biggest driver of cost increase?", "How much variance is from drift vs planned changes?", "Which resources should I import to Terraform first?"],
  "Close Packet": ["Write a one-paragraph executive summary for my CFO.", "What are the key action items from this analysis?", "How confident is the variance classification?"],
  Engineering: ["Which teams have the most unmanaged resources?", "What's our IaC coverage gap in dollar terms?", "Prioritize the drift resources for me by impact."],
  Trends: ["What's the overall cost trajectory?", "Which services are growing fastest?", "Are there any anomalies I should investigate?"],
};

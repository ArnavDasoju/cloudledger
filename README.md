# ☁️ CloudLedger

**Cloud billing variance analysis — trace every dollar of cloud cost change to a specific engineering decision.**

CloudLedger automates the month-end cloud close process. Upload your billing exports and Terraform state (or connect directly to AWS/Azure), and get a CFO-ready variance report in minutes instead of days.

![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js) ![Python](https://img.shields.io/badge/Python-3.14-blue?logo=python) ![FastAPI](https://img.shields.io/badge/FastAPI-latest-009688?logo=fastapi) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql)

---

## What It Does

Every month, cloud bills change. Nobody can explain why. Engineering shipped a dozen changes, but nobody tracks which change cost what. The finance controller spends days manually reconciling spreadsheets.

CloudLedger fixes this by:

1. **Ingesting** billing CSVs (AWS FOCUS 1.2 / Azure Cost Export) or pulling directly from your cloud account
2. **Matching** every billed resource against your Terraform state to identify what's managed vs. drifted
3. **Classifying** each cost change with a reason code (planned, drift, usage growth, steady state, edge cases)
4. **Day-normalizing** variance to eliminate false positives from different month lengths
5. **Generating** a close packet with executive summary, action items, and journal entry exports

---

## Screens

| Screen | Purpose |
|--------|---------|
| **Upload** | Upload billing CSVs or connect AWS/Azure accounts directly |
| **Overview** | Month-over-month spend comparison with service breakdown |
| **Ingestion** | Data quality checks, Terraform match rate, tag coverage |
| **Variance** | Resource-level detail with expandable evidence rows |
| **Root Causes** | Why costs changed — planned, drift, usage, edge cases |
| **Close Packet** | CFO-ready summary, action items, PDF/CSV export |
| **Engineering** | IaC coverage, team attribution, drift inventory |
| **Trends** | Historical charts, per-service trends, anomaly detection |

---

## Key Features

### Variance Engine
- **Day-normalized comparison** — adjusts for different month lengths (Feb 28 vs Mar 31) to eliminate false positives
- **7 reason codes**: `planned`, `steady_state`, `usage_growth`, `new_resource`, `removed_resource`, `drift` variants, edge cases
- **Evidence chains** — every classification comes with a human-readable explanation

### Cloudly Assistant
- Embedded chatbot that answers questions about your billing data
- Cross-screen aware — sees data from all screens, not just the one you're viewing
- Suggested questions tailored to each screen
- Markdown rendering with highlighted key findings

### Cloud Account Connection
- **AWS**: Connect with Access Key + Secret Key, pulls from Cost Explorer API
- **Azure**: Connect with Service Principal credentials, pulls from Cost Management API
- Select 2–12 months of historical data

### GitHub CI/CD Integration
- Syncs merged PRs that touch `.tf` files
- Links infrastructure changes to specific cost impacts
- Reclassifies "drift" to "planned" when a matching PR is found

### MCP Server
- Exposes 6 tools for any MCP-compatible client
- Query billing data, variance, IaC coverage, and anomalies programmatically

### Multi-IaC Support
- Terraform (`.tfstate`)
- ARM Templates (Azure)
- CloudFormation
- Pulumi

---

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL 14+

### Installation

```bash
# Clone the repo
git clone https://github.com/ArnavDasoju/cloudledger.git
cd cloudledger

# Set up Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set up frontend
cd frontend
npm install
cd ..

# Create database
createdb cloudledger

# Configure environment
cp .env.example .env
# Edit .env with your database credentials
```

### Environment Variables

Create a `.env` file in the project root:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/cloudledger
ANTHROPIC_API_KEY=sk-ant-...    # For Cloudly assistant
GITHUB_TOKEN=ghp_...            # Optional: for CI/CD integration
GITHUB_REPO=your-org/your-repo  # Optional: for CI/CD integration
```

### Running

```bash
# Terminal 1: Start the backend
source venv/bin/activate
python -m uvicorn backend.server:app --host 0.0.0.0 --port 8000

# Terminal 2: Start the frontend
cd frontend
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

### Using the MCP Server

Add to your MCP client config (e.g. `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "cloudledger": {
      "command": "/path/to/cloudledger/venv/bin/python",
      "args": ["-m", "cloudledger.mcp_server"]
    }
  }
}
```

---

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Next.js    │────▶│   FastAPI    │────▶│  PostgreSQL  │
│   Frontend   │     │   Backend    │     │   Database   │
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │
                   ┌────────┼────────┐
                   │        │        │
              ┌────▼──┐ ┌───▼───┐ ┌──▼───┐
              │Cloudly│ │GitHub │ │ MCP  │
              │  API  │ │  API  │ │Server│
              └───────┘ └───────┘ └──────┘
```

**Backend** (`backend/server.py`) — FastAPI with 15+ endpoints for data ingestion, variance analysis, trends, chat, and cloud account connection.

**Analysis Engine** (`cloudledger/`) — Python modules for CSV ingestion, IaC state parsing, resource normalization, day-normalized variance computation, and reason code classification.

**Frontend** (`frontend/`) — Next.js 16 single-page app with glassmorphic design, staggered animations, interactive charts (Recharts), and the Cloudly chat panel.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/upload` | Upload billing CSVs |
| `POST` | `/api/upload/terraform` | Upload Terraform state |
| `POST` | `/api/pipeline/run` | Run variance for two periods |
| `POST` | `/api/pipeline/run-all` | Run variance for all period pairs |
| `POST` | `/api/connect/aws` | Connect to AWS account |
| `POST` | `/api/connect/azure` | Connect to Azure account |
| `POST` | `/api/github/sync` | Sync GitHub PRs |
| `POST` | `/api/chat` | Cloudly chat |
| `GET` | `/api/trends` | Historical cost trends |
| `GET` | `/api/ingestion-stats` | Data quality metrics |
| `GET` | `/api/variance-by-service` | Variance breakdown |
| `GET` | `/api/root-causes` | Root cause analysis |
| `GET` | `/api/close-packet` | Close packet data |
| `GET` | `/api/engineering-view` | IaC coverage metrics |
| `GET` | `/api/gl-export` | Journal entry CSV export |
| `GET` | `/api/close-packet/pdf` | Close packet PDF export |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React, Tailwind CSS, Recharts |
| Backend | FastAPI, SQLAlchemy, Pydantic |
| Database | PostgreSQL |
| NLP | Anthropic Claude API |
| Cloud SDKs | boto3 (AWS), Azure REST API |
| IaC Parsing | Terraform, ARM, CloudFormation, Pulumi |
| Protocol | MCP (Model Context Protocol) |

---

## License

MIT

---

Built for the month-end close. Trace every dollar.

# 🏥 Healthcare Analytics Copilot
### AI-Powered Natural Language to SQL Agent for Medicare Billing Analysis

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Streamlit-FF4B4B?style=for-the-badge&logo=streamlit)](https://healthcare-analytics-copilot.streamlit.app/)
[![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python)](https://python.org)
[![Claude AI](https://img.shields.io/badge/Claude-Sonnet%204.6-D4A017?style=for-the-badge)](https://anthropic.com)
[![CMS Data](https://img.shields.io/badge/Data-CMS%20Medicare%202023-0072B8?style=for-the-badge)](https://data.cms.gov)

> Ask any question about Houston Medicare billing data in plain English.  
> Claude converts it to SQL, queries real CMS 2023 data, and returns an executive insight + chart — instantly.

---

## Live Demo

**[→ Try it live: healthcare-analytics-copilot.streamlit.app](https://healthcare-analytics-copilot.streamlit.app/)**

No setup required. Click any example question in the sidebar to see the agent in action.

---

## Screenshots

### Homepage
![Homepage](https://raw.githubusercontent.com/Hahmedsid/cms-medicare-AI-Analyst/main/screenshot_homepage.png)

### Revenue Leakage Analysis
![Revenue Leakage](https://raw.githubusercontent.com/Hahmedsid/cms-medicare-AI-Analyst/main/screenshot_revenue_leakage.png)

### Reimbursement Rate Analysis
![Reimbursement Rates](https://raw.githubusercontent.com/Hahmedsid/cms-medicare-AI-Analyst/main/screenshot_reimbursement.png)

---

## What It Does

Healthcare revenue cycle teams spend hours writing SQL queries to answer basic business questions. This agent eliminates that friction entirely.

**You type:** *"Which providers in Houston have the highest revenue leakage?"*

**The agent:**
1. Sends your question + database schema to Claude Sonnet 4.6
2. Claude generates precise, safe SQL
3. SQL executes against real CMS Medicare 2023 data
4. Claude writes a 2-3 sentence executive summary of the findings
5. Results appear as a smart chart + narrative in seconds

---

## The Business Problem

Medicare providers in Texas billed **billions of dollars** in 2023 — but collected only a fraction of what they charged. The gap between what's billed and what Medicare pays is called **revenue leakage**, and it represents one of the most significant financial challenges facing health systems today.

This tool lets revenue cycle directors, CFOs, and BI analysts explore that gap interactively — without writing a single line of SQL.

**Example questions you can ask:**
- *"Which specialties have the worst reimbursement rates in Houston?"*
- *"Top 10 Houston providers by total revenue leakage"*
- *"Top 10 Cardiology providers by total billed amount"*
- *"Compare reimbursement rates between facility and office settings"*

---

## Architecture

```
User Question (plain English)
         │
         ▼
   Streamlit UI (app.py)
         │
         ▼
   Claude Sonnet 4.6 ◄── Database schema injected as system prompt
         │
         ▼
   SQL Executor (agent.py)
         │
         ├──► SQLite Database (CMS Medicare 2023 — Houston providers)
         │
         ├──► Smart Chart (auto-detects bar / line / pie based on data)
         │
         └──► AI Executive Narrative (Claude writes the insight)
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| AI / LLM | Claude Sonnet 4.6 (Anthropic) |
| Frontend | Streamlit |
| Charts | Plotly Express |
| Database | SQLite |
| Data Processing | Pandas |
| Data Source | CMS Medicare 2023 |
| Language | Python 3.12 |
| Deployment | Streamlit Community Cloud |

---

## Data

**Source:** [CMS Medicare Physician & Other Practitioners by Provider and Service (2023)](https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners/medicare-physician-other-practitioners-by-provider-and-service)

**Scope:** Houston, Texas providers — top 10,000 records by billing volume

**Key columns used:**
- `Tot_Sbmtd_Chrg` — Total amount billed to Medicare
- `Tot_Mdcr_Pymt_Amt` — Total amount Medicare actually paid
- `Reimbursement_Rate_Pct` — % of billed amount collected
- `Revenue_Leakage` — Dollars billed but never collected
- `Rndrng_Prvdr_Type` — Medical specialty
- `HCPCS_Desc` — Procedure description

**Full dataset:** 671,400 Texas provider-procedure records (available locally via setup notebook)

---

## How to Run Locally

### Prerequisites
- Python 3.12+
- Anthropic API key ([get one here](https://console.anthropic.com))

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/Hahmedsid/cms-medicare-AI-Analyst.git
cd cms-medicare-AI-Analyst

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set your API key
$env:ANTHROPIC_API_KEY="your-api-key-here"  # Windows PowerShell
# export ANTHROPIC_API_KEY="your-api-key-here"  # Mac/Linux

# 4. Run the app
streamlit run app.py
```

The app automatically builds the database from `sample_data.csv` on first run.

### Full Dataset (Optional)

To run with the complete 671,400-row Texas dataset:

1. Download the CMS 2023 dataset from [data.cms.gov](https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners/medicare-physician-other-practitioners-by-provider-and-service)
2. Place the CSV in the project folder
3. Run `Healthcare_NL_SQL_Agent.ipynb` to build the full database

---

## Project Structure

```
cms-medicare-AI-Analyst/
├── app.py                          # Streamlit frontend
├── agent.py                        # Claude AI agent (NL → SQL → narrative)
├── Healthcare_NL_SQL_Agent.ipynb   # Development notebook with full pipeline
├── sample_data.csv                 # Houston providers sample (10,000 rows)
├── requirements.txt                # Python dependencies
├── .streamlit/
│   └── config.toml                 # Light theme configuration
├── .env.example                    # Environment variable template
└── .gitignore                      # Excludes large data files and secrets
```

---

## Security

- API key stored as Streamlit secret — never in code or GitHub
- SQL safety guardrail blocks `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`
- `.gitignore` excludes all CSV, database, and secret files

---

## Key Design Decisions

**Schema injection** — The full database schema is injected into Claude's system prompt on every request. This prevents hallucinated column names and enforces correct SQLite syntax.

**Structured JSON output** — Claude returns `{ sql, explanation, chart_type }` as JSON, making parsing reliable and eliminating fragile text extraction.

**Smart chart detection** — The app auto-detects the best visualization based on data shape: dates → line, user asks for percentage → pie, everything else → horizontal bar.

**User intent priority** — If the user explicitly requests a chart type ("show as bar chart"), that always overrides auto-detection.

---

## About the Author

**Hassaan Ahmed Siddiqui** — BI Analyst with 5+ years of experience in SQL, Tableau, Power BI, and data modeling. Currently building AI-enabled analytics solutions that bridge enterprise BI and agentic AI.

- 🔗 [LinkedIn](https://linkedin.com/in/hassaan-ahmed-siddiqui)
- 🐙 [GitHub](https://github.com/Hahmedsid)
- 📧 hassaan.a.ahmed@gmail.com

---

## License

MIT License — free to use, modify, and distribute.

---

*Built with real CMS Medicare data • Powered by Claude AI • Deployed on Streamlit Community Cloud*

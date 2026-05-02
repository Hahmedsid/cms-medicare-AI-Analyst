"""
agent.py — The Claude-powered brain of the Healthcare NL to SQL Agent.

Functions:
  is_safe_sql()        — blocks destructive SQL keywords
  generate_sql()       — converts plain English question to SQL using Claude
  execute_sql()        — runs SQL against cms_texas.db
  generate_narrative() — generates plain English summary of results
  run_agent()          — orchestrates all three in sequence
"""

import json
import sqlite3
import re
import anthropic

import os
import sqlite3
import pandas as pd

def ensure_database():
    """
    If cms_texas.db doesn't exist, build it from sample_data.csv.
    This runs automatically on Streamlit Cloud where only the CSV is available.
    """
    if os.path.exists("cms_texas.db"):
        return  # Database already exists — nothing to do

    if not os.path.exists("sample_data.csv"):
        raise FileNotFoundError(
            "Neither cms_texas.db nor sample_data.csv found. "
            "Please run the setup notebook first."
        )

    print("Building database from sample_data.csv...")

    df = pd.read_csv("sample_data.csv", dtype=str)

    # Convert numeric columns
    numeric_cols = [
        "Tot_Benes", "Tot_Srvcs", "Avg_Sbmtd_Chrg",
        "Avg_Mdcr_Alowd_Amt", "Avg_Mdcr_Pymt_Amt",
        "Tot_Sbmtd_Chrg", "Tot_Mdcr_Alowd_Amt", "Tot_Mdcr_Pymt_Amt",
        "Reimbursement_Rate_Pct", "Revenue_Leakage"
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    conn = sqlite3.connect("cms_texas.db")
    df.to_sql("cms_billing", conn, if_exists="replace", index=False)

    # Create indexes
    cur = conn.cursor()
    cur.execute("CREATE INDEX IF NOT EXISTS idx_type ON cms_billing (Rndrng_Prvdr_Type)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_city ON cms_billing (Rndrng_Prvdr_City)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_hcpcs ON cms_billing (HCPCS_Cd)")
    conn.commit()
    conn.close()

    print(f"✓ Database built from sample_data.csv ({len(df):,} rows)")


# Run on import — builds DB from CSV if needed
ensure_database()

# ── Configuration ─────────────────────────────────────────────────────────────

DB_PATH = "cms_texas.db"
client  = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from environment

# ── Schema Prompt ─────────────────────────────────────────────────────────────

SCHEMA_PROMPT = """
You are a healthcare business intelligence analyst assistant.
You have access to a SQLite database called cms_texas.db.

It contains one table called cms_billing with real Texas Medicare
billing data for 2023 focused on Houston providers.
The table has 10,000 rows — one row per provider per procedure code.

TABLE: cms_billing

PROVIDER INFORMATION:
  Rndrng_NPI                 — Provider unique ID number (NPI)
  Rndrng_Prvdr_Last_Org_Name — Provider last name or organization name
  Rndrng_Prvdr_First_Name    — Provider first name
  Rndrng_Prvdr_Type          — Medical specialty
                               Examples: 'Cardiology', 'Internal Medicine',
                               'Ophthalmology', 'Diagnostic Radiology',
                               'Nurse Practitioner', 'Clinical Laboratory',
                               'Ambulatory Surgical Center'
  Rndrng_Prvdr_City          — City name
                               Examples: 'Houston', 'Dallas', 'San Antonio',
                               'Austin', 'Fort Worth', 'El Paso'
  Rndrng_Prvdr_State_Abrvtn  — Always 'TX' in this database
  Rndrng_Prvdr_Zip5          — 5-digit ZIP code

PROCEDURE INFORMATION:
  HCPCS_Cd                   — Procedure billing code (e.g. '99213')
  HCPCS_Desc                 — Plain English procedure name
                               e.g. 'Office/outpatient visit, established'
  Place_Of_Srvc              — Where service was performed
                               'F' = facility (hospital)
                               'O' = office
                               When displaying Place_Of_Srvc, always use
                               CASE WHEN Place_Of_Srvc = 'F' THEN 'Facility'
                               WHEN Place_Of_Srvc = 'O' THEN 'Office' END
                               AS setting — never show raw F or O codes

VOLUME COLUMNS:
  Tot_Benes                  — Total unique Medicare patients served
  Tot_Srvcs                  — Total number of services billed

AVERAGE DOLLAR COLUMNS (per service):
  Avg_Sbmtd_Chrg             — Average amount charged per service
  Avg_Mdcr_Alowd_Amt         — Average Medicare allowed per service
  Avg_Mdcr_Pymt_Amt          — Average Medicare payment per service

DERIVED TOTAL DOLLAR COLUMNS (average x Tot_Srvcs):
  Tot_Sbmtd_Chrg             — Total amount billed to Medicare
  Tot_Mdcr_Alowd_Amt         — Total amount Medicare allowed
  Tot_Mdcr_Pymt_Amt          — Total amount Medicare actually paid

REVENUE CYCLE METRICS (pre-calculated, ready to query directly):
  Reimbursement_Rate_Pct     — Percentage of billed amount Medicare paid
                               Formula: Tot_Mdcr_Pymt_Amt / Tot_Sbmtd_Chrg * 100
                               Low % = poor reimbursement
                               High % = strong reimbursement
  Revenue_Leakage            — Dollars billed but never collected
                               Formula: Tot_Sbmtd_Chrg - Tot_Mdcr_Pymt_Amt
                               Higher value = more money left uncollected

STRICT SQL RULES:
  1. This is SQLite — never use MySQL or PostgreSQL syntax
  2. Always alias aggregations: SUM(Tot_Sbmtd_Chrg) AS total_billed
  3. City filter always use LIKE: WHERE Rndrng_Prvdr_City LIKE '%Houston%'
  4. Specialty filter always use LIKE: WHERE Rndrng_Prvdr_Type LIKE '%Cardiology%'
  5. Always GROUP BY when using SUM() or AVG() across categories
  6. Always ORDER BY the main metric DESC unless asked otherwise
  7. Always LIMIT to 10 rows maximum unless a specific number is requested
  8. Round dollar amounts to 2 decimals: ROUND(SUM(Tot_Sbmtd_Chrg), 2)
  9. Round percentages to 1 decimal: ROUND(AVG(Reimbursement_Rate_Pct), 1)
  10. NEVER use DROP, DELETE, UPDATE, INSERT or ALTER — read only
  11. For procedure-level queries, GROUP BY HCPCS_Desc only — never group by both HCPCS_Cd and HCPCS_Desc together
  12. Never GROUP BY more than one column unless the question specifically asks for a breakdown
  13. Always cast ZIP codes as text: CAST(Rndrng_Prvdr_Zip5 AS TEXT) AS zip_code

BUSINESS CONTEXT:
  Revenue leakage = gap between what providers bill and what Medicare pays.
  Reimbursement rate = efficiency of collections. Industry average is 25-35%.
  Specialties below 20% reimbursement rate have significant collection problems.
  Ambulatory Surgical Centers and Diagnostic Radiology typically bill high
  but receive low reimbursement because Medicare pays a fixed fee schedule.
"""

# ── Safety guardrail ──────────────────────────────────────────────────────────

BLOCKED_KEYWORDS = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "TRUNCATE"]

def is_safe_sql(sql: str) -> bool:
    upper = sql.upper()
    return not any(keyword in upper for keyword in BLOCKED_KEYWORDS)


# ── generate_sql() ────────────────────────────────────────────────────────────

def generate_sql(user_question: str) -> dict:
    instruction = """
Convert the user's question into a SQL query for the cms_billing table.

Respond ONLY with a valid JSON object in exactly this format —
no text before it, no text after it, no markdown code fences:
{
  "sql": "SELECT ... FROM cms_billing ...",
  "explanation": "One plain sentence describing what this SQL finds",
  "chart_type": "bar"
}

For chart_type choose one of:
  "bar"   — comparing categories (specialties, cities, providers)
  "line"  — trends over time
  "pie"   — part of a whole (max 6 categories)
  "table" — detailed row-level data or more than 6 categories
"""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=SCHEMA_PROMPT,
        messages=[{
            "role": "user",
            "content": f"{instruction}\n\nUser question: {user_question}"
        }]
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError(f"Claude returned invalid JSON:\n{raw}")

    if not is_safe_sql(result["sql"]):
        raise ValueError("Generated SQL contains blocked keywords. Rejected.")

    return result


# ── execute_sql() ─────────────────────────────────────────────────────────────

def execute_sql(sql: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    try:
        cur.execute(sql)
        raw_rows = cur.fetchall()
        columns  = [desc[0] for desc in cur.description] if cur.description else []
        rows     = [list(row) for row in raw_rows]
    except sqlite3.Error as e:
        conn.close()
        raise ValueError(f"SQL execution failed: {e}\n\nQuery:\n{sql}")

    conn.close()
    return {"columns": columns, "rows": rows, "row_count": len(rows)}


# ── generate_narrative() ──────────────────────────────────────────────────────

def generate_narrative(user_question: str, sql: str, query_result: dict) -> str:
    preview_rows   = query_result["rows"][:10]
    result_preview = {
        "columns"    : query_result["columns"],
        "sample_rows": preview_rows,
        "total_rows" : query_result["row_count"]
    }

    prompt = f"""
The user asked this question about Texas Medicare billing data:
"{user_question}"

We ran this SQL query:
{sql}

The results ({len(preview_rows)} of {query_result['row_count']} total rows):
{json.dumps(result_preview, indent=2)}

Write a concise 2-3 sentence executive summary of these results.

Your summary must:
1. State the single most important finding with specific numbers
2. Highlight any notable outlier or pattern worth attention
3. End with one actionable business takeaway

Write in plain business language — no SQL, no technical jargon.
Write as if presenting to a hospital CFO or revenue cycle director.
Do NOT start with "The query" or "Based on the data" or "The results show".
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text.strip()


# ── run_agent() ───────────────────────────────────────────────────────────────

def run_agent(user_question: str) -> dict:
    sql_result   = generate_sql(user_question)
    query_result = execute_sql(sql_result["sql"])
    narrative    = generate_narrative(
        user_question,
        sql_result["sql"],
        query_result
    )

    return {
        "question"   : user_question,
        "sql"        : sql_result["sql"],
        "explanation": sql_result["explanation"],
        "chart_type" : sql_result["chart_type"],
        "columns"    : query_result["columns"],
        "rows"       : query_result["rows"],
        "row_count"  : query_result["row_count"],
        "narrative"  : narrative
    }
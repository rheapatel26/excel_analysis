"""
llm_agent.py – Gemini-powered intelligence layer for ClaimIQ
Uses: google-generativeai (classic SDK — correctly supports gemini-1.5-flash free tier)
Model: gemini-1.5-flash  (free: 15 RPM, 1500 req/day)
"""

from __future__ import annotations
import json
import traceback
import os
from dotenv import load_dotenv
import pandas as pd
import numpy as np

load_dotenv()

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


# ─── Helpers ─────────────────────────────────────────────────────────────────

CHAT_MODEL  = "gemini-2.5-flash-lite"
SAFETY_OFF  = [
    {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH",        "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",  "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT",  "threshold": "BLOCK_NONE"},
]

def _model(api_key: str | None = None):
    if not HAS_GENAI:
        raise RuntimeError("google-generativeai not installed. Run: pip install google-generativeai")
    
    # Fallback to .env key 'Insure'
    final_key = api_key or os.getenv('Insure')
    if not final_key:
        raise ValueError("No Gemini API key provided. Add 'Insure=...' to .env or pass it via UI.")
        
    genai.configure(api_key=final_key)
    return genai.GenerativeModel(
        model_name=CHAT_MODEL,
        safety_settings=SAFETY_OFF,
    )

def _gen_config(temperature=0.4, max_tokens=1200):
    return genai.types.GenerationConfig(
        temperature=temperature,
        max_output_tokens=max_tokens,
    )

def _lakhs(n: float) -> str:
    if n >= 1e7: return f"₹{n/1e7:.2f} Cr"
    if n >= 1e5: return f"₹{n/1e5:.2f} L"
    return f"₹{n:,.0f}"


# ─── 1. CONSULTANT NARRATIVE ─────────────────────────────────────────────────

NARRATIVE_PROMPT = """You are a Senior Insurance & Claims Intelligence Consultant with 15 years of experience
advising TPAs, insurance companies, and corporate HR departments on group mediclaim portfolios.

Write a 4–6 paragraph executive summary in the style of a McKinsey healthcare cost advisory report.
Use markdown bold (**text**) for key metrics. Use flowing paragraphs, NOT bullet points.
Tone: authoritative, precise, slightly urgent where warranted.

CLAIM PORTFOLIO DATA:
{data_brief}

Write the executive summary now:"""


def generate_narrative(kpis, hospital_data, trend_data, fraud_flags, disease_data, file_name, api_key):
    top_hospitals = hospital_data[:5] if hospital_data else []
    top_diseases  = disease_data[:5]  if disease_data  else []

    trend_summary = ""
    if len(trend_data) >= 2:
        first, last = trend_data[0], trend_data[-1]
        delta = last["count"] - first["count"]
        trend_summary = (f"Claim volume changed from {first['count']} in {first['month']} "
                         f"to {last['count']} in {last['month']} (Δ {delta:+d}).")

    data_brief = f"""FILE: {file_name}
Total Claims: {kpis.get('total_claims',0):,}  |  Total Incurred: {_lakhs(kpis.get('total_incurred',0))}
Avg Claim: {_lakhs(kpis.get('avg_claim',0))}  |  Max Claim: {_lakhs(kpis.get('max_claim',0))}
Cashless: {kpis.get('cashless_count',0)} ({kpis.get('cashless_pct',0)}%)  |  Reimbursement: {kpis.get('reimb_count',0)}
Approved: {kpis.get('approved_count',0)} ({kpis.get('approval_rate',0)}%)  |  Rejected: {kpis.get('rejected_count',0)}
Total Billed: {_lakhs(kpis.get('total_billed',0))}  |  Deductions: {_lakhs(kpis.get('total_deductions',0))}

Top Hospitals: {json.dumps(top_hospitals, indent=2)}
Top Diseases:  {json.dumps(top_diseases,  indent=2)}
Trend: {trend_summary}
Fraud/Outlier flags: {len(fraud_flags)} | Sample signals: {[f.get('signals',[]) for f in fraud_flags[:3]]}"""

    try:
        resp = _model(api_key).generate_content(
            NARRATIVE_PROMPT.format(data_brief=data_brief),
            generation_config=_gen_config(0.4, 1200),
        )
        return resp.text.strip()
    except Exception as e:
        return f"[Gemini narrative unavailable: {e}] — Template narrative shown instead."


# ─── 2. TEXT-TO-PANDAS AGENT ─────────────────────────────────────────────────

# ─── 2. TEXT-TO-PANDAS AGENT (BROKER INTELLIGENCE) ───────────────────────────

PANDAS_PROMPT = """You are a Senior Insurance Broker Analyst. Your goal is to help your clients (HR Managers and CFOs) understand their claim data to manage costs and risk.

DataFrame `df` schema:
{schema}

Semantic column roles: {column_map}

Health Impact / Chronic Context:
- Long-term: Diabetes, Hypertension, Cardiac, Cancer, Kidney, Respiratory.
- Look for recurrence (repeat member IDs for same diagnosis).

STEP 1: Write a Python/Pandas script to answer: "{question}"
- Use only `pandas` and `numpy`. `df` is already loaded.
- Store results in a variable `result`.
- If the question is purely descriptive/domain-based (not needing code), set result to None.

Respond ONLY with valid JSON:
{{"code": "<python code>", "reasoning": "<one sentence logic>"}}"""

BROKER_INSIGHT_PROMPT = """You are a Senior Insurance Broker Analyst.
Original Question: "{question}"

Data Result from analysis:
{data_summary}

Write a professional, insight-led response for an Insurance Broker to give their client.
- Do NOT just repeat numbers; interpret what they mean for the portfolio's health or finances.
- Highlight risks (e.g. high inflation, chronic burden) or opportunities (e.g. wellness programs).
- Keep it concise (2-3 sentences), authoritative, and actionable.
- Do NOT mention "the data shows" or "in result" — talk like a consultant who knows the facts."""


def text_to_pandas(question, df, api_key, column_map=None):
    schema_lines = [
        f"  {col!r} ({str(df[col].dtype)}): {str(df[col].dropna().head(3).tolist())[:80]}"
        for col in df.columns
    ]
    schema = "\n".join(schema_lines)

    try:
        # Pass 1: Code Generation
        resp = _model(api_key).generate_content(
            PANDAS_PROMPT.format(
                schema=schema,
                column_map=json.dumps(column_map or {}, indent=2),
                question=question,
            ),
            generation_config=_gen_config(0.1, 500),
        )
        raw = resp.text.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            raw = raw.rsplit("```", 1)[0].strip()
        parsed      = json.loads(raw)
        code        = parsed.get("code", "")
        reasoning   = parsed.get("reasoning", "")
    except Exception as e:
        return {"code": "", "explanation": "", "result_html": "", "error": f"Logic generation failed: {e}"}

    # ── Sandboxed execution ──────────────────────────────────────────────────
    sandbox = {"df": df.copy(), "pd": pd, "np": np}
    result = None
    exec_error = None
    if code:
        try:
            exec(compile(code, "<gemini_code>", "exec"), sandbox)   # noqa: S102
            result = sandbox.get("result")
        except Exception as exc:
            exec_error = f"Execution error: {exc}"
            result = None

    # ── Pass 2: Broker Insight Interpretation ───────────────────────────────
    # Summarise result for LLM (Limit context to 2000 chars)
    data_summary = "N/A (No data found or execution error)"
    if result is not None:
        if isinstance(result, (pd.DataFrame, pd.Series)):
            data_summary = result.head(10).to_string()
        else:
            data_summary = str(result)
    
    try:
        insight_resp = _model(api_key).generate_content(
            BROKER_INSIGHT_PROMPT.format(
                question=question,
                data_summary=data_summary[:2000]
            ),
            generation_config=_gen_config(0.4, 400),
        )
        explanation = insight_resp.text.strip()
    except Exception:
        explanation = reasoning or "Interpreted result from analysis."

    # ── Serialise to HTML ────────────────────────────────────────────────────
    if isinstance(result, pd.DataFrame):
        html = result.head(50).to_html(classes="llm-result-table", border=0, index=True)
    elif isinstance(result, pd.Series):
        html = result.head(50).to_frame().to_html(classes="llm-result-table", border=0)
    elif isinstance(result, dict):
        html = pd.Series(result).to_frame(name="value").to_html(classes="llm-result-table", border=0)
    elif result is not None:
        html = f"<div class='llm-scalar'>{result}</div>"
    else:
        html = f"<div class='llm-scalar'>{exec_error or 'No data found.'}</div>"

    return {"code": code, "explanation": explanation, "result_html": html, "error": exec_error}


# ─── 3. POLICY RAG Q&A ───────────────────────────────────────────────────────

POLICY_PROMPT = """You are an expert insurance policy interpreter.

Policy Document Excerpts:
{context}

Question: {question}

Answer by citing relevant clause(s) from the excerpts above.
Use **bold** for key policy terms. Always cite the page number. Be concise."""


def answer_policy_question(question, retrieved_chunks, api_key):
    if not retrieved_chunks:
        return "No relevant policy sections found. Please upload a policy PDF first."

    context = "\n\n---\n\n".join(
        f"Excerpt {i} [Page {c.get('page','?')}]:\n{c['text']}"
        for i, c in enumerate(retrieved_chunks, 1)
    )

    try:
        resp = _model(api_key).generate_content(
            POLICY_PROMPT.format(context=context, question=question),
            generation_config=_gen_config(0.2, 800),
        )
        return resp.text.strip()
    except Exception as e:
        return f"Error generating answer: {e}"

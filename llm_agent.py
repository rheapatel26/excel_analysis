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

CHAT_MODEL  = "gemini-pro"
SAFETY_OFF  = [
    {"category": "HARM_CATEGORY_HARASSMENT",        "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH",        "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",  "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT",  "threshold": "BLOCK_NONE"},
]
import logging

# Setup local logger
logger = logging.getLogger("ClaimIQ.LLM")

def _model(api_key: str | None = None):
    if not HAS_GENAI:
        raise RuntimeError("google-generativeai not installed. Run: pip install google-generativeai")
    
    final_key = api_key or os.getenv('GEMINI_API_KEY')
    if not final_key:
        raise ValueError("No Gemini API key provided. Add 'GEMINI_API_KEY=...' to .env.")
        
    genai.configure(api_key=final_key)
    
    # confirmed available on this account:
    candidates = [
        "models/gemini-2.0-flash", 
        "models/gemini-2.5-flash", 
        "models/gemini-pro-latest", 
        "models/gemini-flash-latest"
    ]
    
    for m_name in candidates:
        try:
            model = genai.GenerativeModel(model_name=m_name, safety_settings=SAFETY_OFF)
            model.generate_content("hi", generation_config=genai.types.GenerationConfig(max_output_tokens=1))
            logger.info(f"✅ Verified working model: {m_name}")
            return model
        except Exception as e:
            logger.warning(f"⚠️ Model {m_name} failed verification: {e}")
            continue
            
    return genai.GenerativeModel(model_name="models/gemini-2.0-flash", safety_settings=SAFETY_OFF)

def _gen_config(temperature=0.0, max_tokens=1200):
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
            generation_config=_gen_config(0.0, 1200),
        )
        return resp.text.strip()
    except Exception as e:
        return f"[Gemini narrative unavailable: {e}] — Template narrative shown instead."


# ─── 2. TEXT-TO-PANDAS AGENT ─────────────────────────────────────────────────

# ─── 2. TEXT-TO-PANDAS AGENT (BROKER INTELLIGENCE) ───────────────────────────

PANDAS_PROMPT = """You are "Share India Intelligence", a Senior Insurance Analyst.
Your goal is to help clients understand their claims data with the depth of a consultant and the conversational ease of GPT.

DATA SCHEMA:
{schema}

COLUMN ROLES:
{column_map}

USER QUESTION: "{question}"

CONTEXT FROM PREVIOUS MESSAGES:
{history}

### INSTRUCTIONS:
1. If the question requires data analysis, write a concise Python script using `pandas`. Store the result in `result`.
2. If the user is just greeting you (e.g., "Hey", "Hello"), or asking a general question NOT requiring data, set "code" to null.
3. IMPORTANT: Do NOT use plotting libraries.

Respond ONLY with valid JSON:
{{
  "code": "<python code or null>",
  "reasoning": "<one sentence logic>",
  "explanation": "<natural conversational response if no code needed, else leave empty>"
}}"""

BROKER_INSIGHT_PROMPT = """You are a Senior Insurance Broker Consultant.
The client asked: "{question}"
The data analysis produced this result:
{data_summary}

Write a professional, insight-led response.
- Interpret the numbers. For example, if an average claim is high, mention the financial impact.
- Be authoritative and concise (2-3 sentences).
- Do NOT use phrases like "based on the data" or "the result is". Talk directly to the client.
- If there's an error or no data, politely explain why and suggest what they might look for instead."""


def text_to_pandas(question, df, api_key, column_map=None, history=""):
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
                history=history
            ),
            generation_config=_gen_config(0.0, 500),
        )
        if not resp.text:
            return {"code": "", "explanation": "The AI model returned an empty response. This might be due to safety filters or an invalid API key.", "result_html": "", "error": "Empty response from Gemini."}

        raw = resp.text.strip()
        # More robust JSON extraction
        if "{" in raw and "}" in raw:
            raw = raw[raw.find("{"):raw.rfind("}")+1]
        
        parsed      = json.loads(raw)
        code        = parsed.get("code")
        reasoning   = parsed.get("reasoning", "Conversational response")
        
        # Conversational bypass (Greetings/General Chat)
        if not code or str(code).lower() == 'null':
            return {
                "code": None,
                "explanation": parsed.get("explanation", "I am ready to help you analyze your claims data."),
                "reasoning": reasoning,
                "result_html": None
            }
    except Exception as e:
        return {"code": "", "explanation": f"I couldn't generate the analysis for that question. (Error: {str(e)})", "result_html": "", "error": f"LLM Error: {str(e)}"}

    # ── Sandboxed execution (Restricted) ─────────────────────────────────────
    safe_builtins = {
        'print': print, 'len': len, 'range': range, 'dict': dict, 'list': list,
        'set': set, 'int': int, 'float': float, 'str': str, 'bool': bool,
        'round': round, 'abs': abs, 'sum': sum, 'min': min, 'max': max,
        'enumerate': enumerate, 'zip': zip, 'any': any, 'all': all,
    }
    sandbox = {
        "df": df.copy(),
        "pd": pd,
        "np": np,
        "__builtins__": safe_builtins
    }
    result = None
    exec_error = None
    if code:
        try:
            # Execute with restricted builtins to prevent system access
            exec(compile(code, "<gemini_code>", "exec"), sandbox)   # noqa: S102
            result = sandbox.get("result")
        except Exception as exc:
            exec_error = f"Execution error: {exc}"
            result = None

    # ── Pass 2: Broker Insight Interpretation ───────────────────────────────
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
            generation_config=_gen_config(0.0, 400),
        )
        explanation = insight_resp.text.strip()
        if not explanation:
            explanation = reasoning or "I've analyzed the data for you."
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
        # Format numbers nicely in the UI
        formatted_val = result
        if isinstance(result, (int, float)):
            formatted_val = f"{result:,.2f}"
        html = f"<div class='text-4xl font-black text-[#001D4A] tracking-tight py-4'>{formatted_val}</div>"
    else:
        html = f"<div class='text-slate-500 italic py-2'>{exec_error or 'No specific data found for this query.'}</div>"

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
            generation_config=_gen_config(0.0, 800),
        )
        return resp.text.strip()
    except Exception as e:
        return f"Error generating answer: {e}"

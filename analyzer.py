"""
analyzer.py – Agentic Claim Analysis Engine
Handles multiple Excel file formats (.xlsx, .xlsb) and auto-detects column roles.
"""

import pandas as pd
import numpy as np
import os
import re
import logging
from datetime import datetime

# Setup local logger
logger = logging.getLogger("ClaimIQ.Analyzer")

class MappingError(Exception):
    """Raised when critical columns cannot be mapped in the Excel file."""
    pass


# ─── Column role aliases ──────────────────────────────────────────────────────
ALIASES = {
    # exact real column names listed first for priority
    "claim_id":      ["claim_number", "ccn_no", "claim no", "claim reference", "claim ref", "claimno", "claim_id",
                      "claim number", "claimnumber", "sr no", "serial no", "s.no",
                      "claim id", "reference no", "ref no", "claim sl no", "claim_nu", "claim_num"],
    "employee_name": ["patient_name", "insured", "employee name", "member name",
                      "employee_name", "patient name", "name of insured", "name",
                      "claimant name", "policyholder name", "member"],
    # 'Hospital' exact match first; 'Hospital Type' is blocklisted inside _find_col
    "hospital":      ["hospital_name", "hospital", "provider name", "facility name",
                      "hospitalname", "hospital_name", "name of hospital",
                      "service provider", "network hospital"],
    "city":          ["hospital_city", "city", "claim location", "hospital city", "location",
                      "city name", "hospital location"],
    "state":         ["hospital_state", "state", "hospital state", "statename", "state name"],
    "claim_type":    ["ccn_type_name", "claim type", "claimtype", "type of claim", "claim_type",
                      "reimbursement or cashless", "type", "cashless/reimbursement",
                      "cashless or reimbursement", "claim category"],
    # Pay Status / Claim Close Status are the settled/rejected flags in the MIS
    "status":        ["final_claim_status", "pay status", "claim close status", "claim status", "final claim status",
                      "final status", "claim_status", "decision", "settlement status", "status",
                      "current status", "claim decision", "approval status"],
    "incurred_amt":  ["incurred_amt", "incurred amt", "incurred amount", "ic_amt",
                      "paid claim amount", "settled amount", "approved amount",
                      "auth amount", "final approved amount", "net payable", "amount payable",
                      "claim amount", "amount", "total amount", "net amount",
                      "claim amt", "paid amount", "payable amount",
                      "sanctioned amount", "net claim amount", "net paid",
                      "total claim amount", "ic amount", "incurred",
                      "disbursed amount", "approved amt", "paid amt",
                      "claim value", "settlement amount", "total paid"],
    # 'Total Bill' exact match; blocklist 'Hospital Bill No'
    "billed_amt":    ["claimed_amount", "total_bill_amt_recd", "total bill", "claimed amt", "billed amount", "bill amount",
                      "total bill amount", "gross amount", "hospital billed amount",
                      "claimed amount", "initial claimed amount", "total claimed",
                      "sum claimed", "billed amt", "hospital bill amount",
                      "estimated amount", "pre auth amount", "preauth amount"],
    "admission_date":["dateof_admission", "actual doa", "expected doa", "admission date", "date of admission",
                      "doa", "hospitalization date", "admission_date", "treatment from date",
                      "date of hospitalization", "claim date", "intimation date",
                      "date of loss", "loss date", "event date", "date",
                      "from date", "treatment date", "registration date",
                      "claim intimation date", "date of claim"],
    "discharge_date":["dateof_discharge", "actual dod", "expected dod", "discharge date", "date of discharge",
                      "dod", "discharge_date", "treatment to date",
                      "to date", "date of discharge from hospital"],
    "icd_code":      ["icd_code_level_1", "icd code", "icd_code", "diagnosis code", "icd10", "icd 10"],
    "diagnosis":     ["final_diagnosis", "provisional diagnosis", "diagnosis", "disease",
                      "ailment", "diagnosis name", "disease name", "primary diagnosis",
                      "nature of illness", "nature of disease", "ailment description",
                      "cause", "cause of claim", "peril"],
    "disease_cat":   ["disease category", "revd disease category", "disease cat",
                      "chapter", "icd chapter", "disease chapter", "broad category"],
    "gender":        ["gender", "sex", "patient gender", "member gender"],
    "age":           ["age", "patient age", "member age", "insured age", "age at admission"],
    "relation":      ["relation", "relationship", "member relation", "insured relation",
                      "relation with employee", "proposer relation"],
    "sum_insured":   ["sum insured", "coverage", "policy sum insured", "si",
                      "cover amount", "sum assured"],
    "deduction_amt": ["other deduction", "deduction", "deductions", "total deduction",
                      "disallowed amount", "non payable", "deducted amount",
                      "disallowance", "co-pay", "copay"],
    "reason":        ["reason", "remark", "repudiation reason", "denial reason", "non_pay_reason",
                      "claim_approval_remark", "documents_remarks", "orphan remark", "query remark",
                      "general remarks", "insured disallow amt reason", "hospital disallow amt reason",
                      "remarks", "comments", "observation"],
}

ICD_CHAPTERS = {
    "A": "Infectious & Parasitic Diseases",
    "B": "Infectious & Parasitic Diseases",
    "C": "Neoplasms",
    "D": "Blood Diseases",
    "E": "Endocrine / Metabolic",
    "F": "Mental & Behavioural",
    "G": "Nervous System",
    "H": "Eye / Ear",
    "I": "Circulatory System",
    "J": "Respiratory System",
    "K": "Digestive System",
    "L": "Skin Diseases",
    "M": "Musculoskeletal",
    "N": "Genitourinary System",
    "O": "Pregnancy / Childbirth",
    "P": "Perinatal Conditions",
    "Q": "Congenital Anomalies",
    "R": "Symptoms / Signs",
    "S": "Injury / Trauma",
    "T": "Poisoning / External",
    "Z": "Health Status / Contact",
}


# ─── Helpers ─────────────────────────────────────────────────────────────────

# Columns that should never be matched even if they contain a target substring
_BLOCKLIST = {
    "hospital type", "hospital bill no", "hospital bill number",
    "bill no", "claim no.", "hospital id", "hospital qualifier",
}

def _find_col(df: pd.DataFrame, role: str):
    """Return first column name matching role aliases, exact-match first then substring."""
    targets = [a.lower().strip() for a in ALIASES.get(role, [])]
    # Normalize current columns: strip, lower, and remove internal extra spaces
    cols_normalized = {re.sub(r'\s+', ' ', str(c).lower().strip()): c for c in df.columns}
    
    # 1) Exact match (highest priority)
    for t in targets:
        if t in cols_normalized and t not in _BLOCKLIST:
            return cols_normalized[t]
            
    # 2) Partial match (contains target string)
    for t in targets:
        if len(t) < 3: continue 
        for col_norm, col_orig in cols_normalized.items():
            if t in col_norm and col_norm not in _BLOCKLIST:
                return col_orig
                
    # 3) Semantic fallbacks for critical financial/date roles
    if role == "incurred_amt":
        # Look for columns with 'amt', 'paid', or 'settled' if nothing found
        for col_norm, col_orig in cols_normalized.items():
            if any(k in col_norm for k in ["paid", "payable", "incurred", "settled", "auth"]) and "bill" not in col_norm:
                return col_orig
    elif role == "admission_date":
        for col_norm, col_orig in cols_normalized.items():
            if any(k in col_norm for k in ["doa", "admission", "hosp", "date"]) and "discharge" not in col_norm:
                return col_orig
                
    return None


def _to_numeric(series: pd.Series) -> pd.Series:
    if series.dtype == object:
        # Strip commas and whitespace before conversion
        clean_series = series.astype(str).str.replace(r'[^\d.]', '', regex=True)
        return pd.to_numeric(clean_series, errors="coerce").fillna(0)
    return pd.to_numeric(series, errors="coerce").fillna(0)


def _to_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", dayfirst=True)


def _icd_chapter(code: str) -> str:
    if not isinstance(code, str):
        return "Unknown"
    letter = code.strip().upper()[0] if code.strip() else "?"
    return ICD_CHAPTERS.get(letter, f"Other ({letter})")


def _month_label(ts) -> str:
    try:
        return ts.strftime("%b %Y")
    except Exception:
        return "Unknown"


CHRONIC_KEYWORDS = [
    "DIABETES", "HYPERTENSION", "CANCER", "NEOPLASM", "CARDIAC", "HEART",
    "KIDNEY", "DIALYSIS", "ASTHMA", "COPD", "THYROID", "ARTHRITIS",
    "CHOLESTEROL", "HIV", "AIDS", "HEPATITIS", "EPILEPSY", "ALZHEIMER",
    "PARKINSON", "DIALYSIS", "CHEMOTHERAPY", "RADIOTHERAPY", "CHRONIC"
]

def _is_chronic(diagnosis: str) -> bool:
    if not isinstance(diagnosis, str):
        return False
    diag_up = diagnosis.upper()
    return any(k in diag_up for k in CHRONIC_KEYWORDS)


# ─── Main parser ─────────────────────────────────────────────────────────────

def read_file(path: str) -> dict[str, pd.DataFrame]:
    """Read Excel file and return {sheet_name: DataFrame}."""
    ext = os.path.splitext(path)[1].lower()
    
    # Check if html disguised as xls
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            head = f.read(2048).lower()
            if "<html" in head or "<table" in head or "<?xml" in head and "<workbook" not in head:
                dfs = pd.read_html(path)
                if dfs: return {"Sheet1": dfs[0]}
    except Exception:
        pass

    engine = "pyxlsb" if ext == ".xlsb" else ("openpyxl" if ext == ".xlsx" else "xlrd")
    
    try:
        xl = pd.ExcelFile(path, engine=engine)
    except (ValueError, Exception) as e:
        # Fallback for CSV/TSV files mislabeled as .xls (very common)
        try:
            # Try aggressive auto-delimiter and encoding detection
            for enc in ['utf-8', 'latin1', 'cp1252', 'utf-16']:
                try:
                    df = pd.read_csv(path, sep=None, engine='python', encoding=enc)
                    if len(df.columns) > 3:
                        return {"Sheet1": df}
                except:
                    continue
        except:
            pass
            
        if "Excel file format cannot be determined" in str(e) or "Expected BOF record" in str(e):
            try:
                dfs = pd.read_html(path)
                if dfs: return {"Sheet1": dfs[0]}
            except Exception:
                pass
        raise e

    sheets = {}
    for name in xl.sheet_names:
        try:
            raw = xl.parse(name, header=None)
            header_row = 0
            for i, row in raw.iterrows():
                non_null = row.dropna()
                if len(non_null) >= 6 and all(isinstance(v, str) or (not isinstance(v, float)) for v in non_null[:6]):
                    header_row = i
                    break
            df = xl.parse(name, header=header_row, engine=engine)
            df.columns = [str(c).strip() for c in df.columns]
            df = df.dropna(how="all")
            if len(df) > 0:
                sheets[name] = df
        except Exception:
            pass
    return sheets


def _best_sheet(sheets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Pick the sheet that has the most claim-relevant columns."""
    scores = {}
    for name, df in sheets.items():
        score = sum(1 for role in ALIASES if _find_col(df, role) is not None)
        scores[name] = score
    best = max(scores, key=scores.get)
    return sheets[best]


# ─── Analysis functions ───────────────────────────────────────────────────────

def kpis(df: pd.DataFrame, cols: dict) -> dict:
    total_claims = len(df)

    inc_col = cols.get("incurred_amt")
    incurred = _to_numeric(df[inc_col]) if inc_col else pd.Series([0] * len(df))
    total_incurred = float(incurred.sum())
    avg_claim = float(incurred.mean()) if total_claims > 0 else 0.0
    max_claim = float(incurred.max()) if total_claims > 0 else 0.0

    # Cashless % - Smart detection
    type_col = cols.get("claim_type")
    ipd_col = next((c for c in df.columns if "IPD" in str(c) and "/" in str(c)), None)
    
    cashless_mask = pd.Series([False] * len(df))
    if type_col:
        cashless_mask |= df[type_col].astype(str).str.upper().str.contains("CASHLESS", na=False)
    
    # Smart Fallback: IPD/Day Care are almost always cashless in institutional reports
    if ipd_col:
        cashless_mask |= df[ipd_col].astype(str).str.upper().isin(["IPD", "DAY CARE", "DAYCARE"])
        
    cashless_count = int(cashless_mask.sum())
    reimb_count = total_claims - cashless_count
    cashless_pct = round(cashless_count / total_claims * 100, 1) if total_claims > 0 else 0

    # Approval rate
    status_col = cols.get("status")
    approved_count = 0
    rejected_count = 0
    if status_col:
        statuses = df[status_col].astype(str).str.upper()
        # Institutional approvals: Paid, Settled, Authorised, AL Issued, Closed with payment
        approved_count = int((statuses.str.contains(
            r"APPROVED|SETTLED|PAID|AUTHORISED|AL ISSUED|CLOSED WITH PAY|WITH PAY|APPROVE", regex=True)).sum())
        # Institutional rejections: Denial, Repudiated, Rejected, Closed without payment
        rejected_count = int((statuses.str.contains(
            r"REJECT|REPUDIAT|WITHOUT PAY|DENIED|DENIAL|CLOSED WITHOUT", regex=True)).sum())
    approval_rate = round(approved_count / total_claims * 100, 1) if total_claims > 0 else 0

    # Deductions
    ded_col = cols.get("deduction_amt")
    total_deductions = float(_to_numeric(df[ded_col]).sum()) if ded_col else 0.0

    # Billed
    bill_col = cols.get("billed_amt")
    total_billed = float(_to_numeric(df[bill_col]).sum()) if bill_col else total_incurred

    return {
        "total_claims": total_claims,
        "total_incurred": round(total_incurred, 2),
        "avg_claim": round(avg_claim, 2),
        "max_claim": round(max_claim, 2),
        "cashless_count": cashless_count,
        "reimb_count": reimb_count,
        "cashless_pct": cashless_pct,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "approval_rate": approval_rate,
        "total_deductions": round(total_deductions, 2),
        "total_billed": round(total_billed, 2),
    }


def hospital_breakdown(df: pd.DataFrame, cols: dict, top_n: int = 10) -> list:
    hosp_col = cols.get("hospital")
    inc_col = cols.get("incurred_amt")
    if not hosp_col:
        return []
    tmp = df[[hosp_col]].copy()
    if inc_col:
        tmp["amt"] = _to_numeric(df[inc_col])
    else:
        tmp["amt"] = 1
    tmp[hosp_col] = tmp[hosp_col].astype(str).str.strip().str.title()
    grp = tmp.groupby(hosp_col).agg(count=(hosp_col, "count"), total_amt=("amt", "sum")).reset_index()
    grp = grp.sort_values("total_amt", ascending=False).head(top_n)
    return [
        {"hospital": r[hosp_col], "count": int(r["count"]), "total_amt": round(float(r["total_amt"]), 2)}
        for _, r in grp.iterrows()
    ]


def monthly_trend(df: pd.DataFrame, cols: dict) -> list:
    date_col = cols.get("admission_date")
    inc_col = cols.get("incurred_amt")
    if not date_col:
        return []
    tmp = df[[date_col]].copy()
    tmp["date"] = _to_date(df[date_col])
    if inc_col:
        tmp["amt"] = _to_numeric(df[inc_col])
    else:
        tmp["amt"] = 1
    tmp = tmp.dropna(subset=["date"])
    tmp["month"] = tmp["date"].dt.to_period("M")
    grp = tmp.groupby("month").agg(count=("date", "count"), total_amt=("amt", "sum")).reset_index()
    grp = grp.sort_values("month")
    return [
        {"month": str(r["month"]), "count": int(r["count"]), "total_amt": round(float(r["total_amt"]), 2)}
        for _, r in grp.iterrows()
    ]


def city_breakdown(df: pd.DataFrame, cols: dict, top_n: int = 10) -> list:
    city_col = cols.get("city")
    inc_col = cols.get("incurred_amt")
    if not city_col:
        return []
    tmp = df[[city_col]].copy()
    if inc_col:
        tmp["amt"] = _to_numeric(df[inc_col])
    else:
        tmp["amt"] = 1
    tmp[city_col] = tmp[city_col].astype(str).str.strip().str.title()
    grp = tmp.groupby(city_col).agg(count=(city_col, "count"), total_amt=("amt", "sum")).reset_index()
    grp = grp.sort_values("count", ascending=False).head(top_n)
    return [
        {"city": r[city_col], "count": int(r["count"]), "total_amt": round(float(r["total_amt"]), 2)}
        for _, r in grp.iterrows()
    ]


def disease_breakdown(df: pd.DataFrame, cols: dict) -> list:
    icd_col = cols.get("icd_code")
    cat_col = cols.get("disease_cat")
    inc_col = cols.get("incurred_amt")

    if cat_col:
        grp_col = cat_col
        # Fix fragmentation warning by creating a clean copy or using local series
        disease_series = df[cat_col].astype(str).str.strip()
    elif icd_col:
        disease_series = df[icd_col].astype(str).apply(_icd_chapter)
        grp_col = "_cat"
    else:
        return []

    tmp = pd.DataFrame({"_cat": disease_series})
    if inc_col:
        tmp["amt"] = _to_numeric(df[inc_col])
    else:
        tmp["amt"] = 1

    grp = tmp.groupby("_cat").agg(count=("_cat", "count"), total_amt=("amt", "sum")).reset_index()
    grp = grp[grp["_cat"].str.lower() != "nan"]
    grp = grp.sort_values("count", ascending=False)
    return [
        {"category": r["_cat"], "count": int(r["count"]), "total_amt": round(float(r["total_amt"]), 2)}
        for _, r in grp.iterrows()
    ]


def chronic_breakdown(df: pd.DataFrame, cols: dict) -> list:
    diag_col = cols.get("diagnosis")
    inc_col = cols.get("incurred_amt")
    if not diag_col:
        return []
    
    tmp = df.copy()
    tmp["is_chronic"] = tmp[diag_col].apply(_is_chronic)
    
    chronic_only = tmp[tmp["is_chronic"]].copy()
    if chronic_only.empty:
        return []
        
    if inc_col:
        chronic_only.loc[:, "amt"] = _to_numeric(chronic_only[inc_col])
    else:
        chronic_only.loc[:, "amt"] = 1
        
    grp = chronic_only.groupby(diag_col).agg(
        count=(diag_col, "count"), 
        total_amt=("amt", "sum")
    ).reset_index()
    
    grp = grp.sort_values("total_amt", ascending=False).head(10)
    return [
        {"illness": str(r[diag_col]), "count": int(r["count"]), "total_amt": round(float(r["total_amt"]), 2)}
        for _, r in grp.iterrows()
    ]


def outlier_detection(df: pd.DataFrame, cols: dict) -> list:
    inc_col = cols.get("incurred_amt")
    if not inc_col:
        return []
    amounts = _to_numeric(df[inc_col])
    mean = amounts.mean()
    std = amounts.std()
    if std == 0:
        return []
    z_scores = (amounts - mean) / std
    outlier_mask = z_scores > 2.5

    result = []
    for idx in df[outlier_mask].index:
        row = df.loc[idx]
        entry = {
            "_idx": int(idx),
            "claim_id": str(row.get(cols.get("claim_id", ""), idx)),
            "employee": str(row.get(cols.get("employee_name", ""), "—")),
            "hospital": str(row.get(cols.get("hospital", ""), "—")),
            "amount": float(amounts.loc[idx]),
            "z_score": round(float(z_scores.loc[idx]), 2),
        }
        result.append(entry)
    # sort by z_score desc
    result.sort(key=lambda x: x["z_score"], reverse=True)
    return result[:20]


def high_value_claims(df: pd.DataFrame, cols: dict, threshold: float = 200000) -> list:
    inc_col = cols.get("incurred_amt")
    if not inc_col:
        return []
    
    amounts = _to_numeric(df[inc_col])
    high_val_mask = amounts > threshold
    
    result = []
    emp_col = cols.get("employee_name")
    hosp_col = cols.get("hospital")
    claim_id_col = cols.get("claim_id")
    
    for idx in df[high_val_mask].index:
        row = df.loc[idx]
        result.append({
            "_idx": int(idx),
            "claim_id": str(row.get(claim_id_col, idx)) if claim_id_col else str(idx),
            "employee": str(row.get(emp_col, "—")) if emp_col else "—",
            "hospital": str(row.get(hosp_col, "—")) if hosp_col else "—",
            "amount": float(amounts.loc[idx]),
        })
    result.sort(key=lambda x: x["amount"], reverse=True)
    return result[:30]


def fraud_flags(df: pd.DataFrame, cols: dict) -> list:
    """Heuristic fraud/anomaly signals."""
    flags = []
    inc_col = cols.get("incurred_amt")
    bill_col = cols.get("billed_amt")
    admit_col = cols.get("admission_date")
    disch_col = cols.get("discharge_date")
    hosp_col = cols.get("hospital")
    status_col = cols.get("status")
    emp_col = cols.get("employee_name")
    claim_id_col = cols.get("claim_id")
    reason_col = cols.get("reason")

    amounts = _to_numeric(df[inc_col]) if inc_col else None
    billed = _to_numeric(df[bill_col]) if bill_col else None

    # Approval rate check
    status_vals = df[status_col].astype(str).str.upper() if status_col else pd.Series([""] * len(df))

    for idx, row in df.iterrows():
        signals = []
        amt = float(amounts.loc[idx]) if amounts is not None else 0
        bil = float(billed.loc[idx]) if billed is not None else 0
        stat = str(status_vals.loc[idx])
        
        # Signal 1: incurred > billed (unusual)
        if bil > 0 and amt > bil * 1.05:
            signals.append(f"Incurred (₹{amt:,.0f}) exceeds billed (₹{bil:,.0f})")

        # Signal 2: zero-day stay with high amount
        if admit_col and disch_col:
            adm = _to_date(pd.Series([row.get(admit_col)]))[0]
            dis = _to_date(pd.Series([row.get(disch_col)]))[0]
            if pd.notna(adm) and pd.notna(dis):
                stay = (dis - adm).days
                if stay == 0 and amt > 50000:
                    signals.append(f"0-day stay with ₹{amt:,.0f} claim")
                elif stay < 0:
                    signals.append("Discharge before admission date")

        # Signal 3: high bill-to-approved ratio (> 3x)
        if bil > 0 and amt > 0 and bil / amt > 3:
            signals.append(f"Bill/Approved ratio: {bil/amt:.1f}x")

        # Signal 4: Unsettled without reason or marked as fraud if unsettled
        is_unsettled = any(kw in stat for kw in ["REJECT", "REPUDIAT", "WITHOUT PAY", "DENIED", "CLOSED WITHOUT"])
        if is_unsettled:
            reason = str(row.get(reason_col, "")).strip() if reason_col else ""
            if not reason or reason.lower() in ["nan", "none", "0", "0.0"]:
                signals.append("Unsettled claim without reason")
            # Heuristic: Mark as fraud if no reason provided for rejection
            if not reason:
                 signals.insert(0, "POTENTIAL FRAUD: Missing Rejection Reason")

        if signals:
            flags.append({
                "_idx": int(idx),
                "claim_id": str(row.get(claim_id_col, idx)) if claim_id_col else str(idx),
                "employee": str(row.get(emp_col, "—")) if emp_col else "—",
                "hospital": str(row.get(hosp_col, "—")) if hosp_col else "—",
                "amount": amt,
                "signals": signals,
                "reason": str(row.get(reason_col, "")) if reason_col else "—"
            })

    return flags[:30]


def status_distribution(df: pd.DataFrame, cols: dict) -> list:
    status_col = cols.get("status")
    inc_col = cols.get("incurred_amt")
    if not status_col:
        return []
    
    tmp = df[[status_col]].copy()
    if inc_col:
        tmp["amt"] = _to_numeric(df[inc_col])
    else:
        tmp["amt"] = 0
    
    tmp[status_col] = tmp[status_col].astype(str).str.strip()
    grp = tmp.groupby(status_col).agg(count=(status_col, "count"), total_amt=("amt", "sum")).reset_index()
    grp = grp[~grp[status_col].str.lower().isin(["nan", "none"])]
    
    return [
        {"status": r[status_col], "count": int(r["count"]), "total_amt": round(float(r["total_amt"]), 2)}
        for _, r in grp.iterrows()
    ]


def claim_type_dist(df: pd.DataFrame, cols: dict) -> list:
    type_col = cols.get("claim_type")
    ipd_col = next((c for c in df.columns if "IPD" in str(c) and "/" in str(c)), None)
    
    cashless_mask = pd.Series([False] * len(df))
    if type_col:
        cashless_mask |= df[type_col].astype(str).str.upper().str.contains("CASHLESS", na=False)
    if ipd_col:
        cashless_mask |= df[ipd_col].astype(str).str.upper().isin(["IPD", "DAY CARE", "DAYCARE"])
        
    cashless_count = int(cashless_mask.sum())
    reimb_count = len(df) - cashless_count
    
    return [
        {"type": "CASHLESS", "count": cashless_count},
        {"type": "REIMBURSEMENT", "count": reimb_count}
    ]


def gender_breakdown(df: pd.DataFrame, cols: dict) -> list:
    g_col = cols.get("gender")
    if not g_col:
        return []
    dist = df[g_col].astype(str).str.strip().str.title().value_counts()
    return [{"gender": k, "count": int(v)} for k, v in dist.items() if k.lower() not in ["nan", "none"]]


def age_breakdown(df: pd.DataFrame, cols: dict) -> list:
    age_col = cols.get("age")
    if not age_col:
        return []
    ages = _to_numeric(df[age_col])
    bins = [0, 18, 30, 45, 60, 200]
    labels = ["0–18", "19–30", "31–45", "46–60", "60+"]
    cut = pd.cut(ages, bins=bins, labels=labels, right=True)
    dist = cut.value_counts().sort_index()
    return [{"group": str(k), "count": int(v)} for k, v in dist.items()]


def relation_distribution(df: pd.DataFrame, cols: dict) -> list:
    rel_col = cols.get("relation")
    if not rel_col:
        return []
    
    rels = df[rel_col].astype(str).str.upper().str.strip()
    
    # Map to groups: Self, Dependent (Son, Daughter, Child, etc.)
    def group_rel(r):
        r = str(r) if not isinstance(r, str) else r
        if r == "SELF": return "Self"
        if any(x in r for x in ["SON", "DAUGHTER", "CHILD", "SPOUSE", "MOTHER", "FATHER", "IN-LAW"]): return "Dependents"
        return "Other"
    
    mapped = rels.apply(group_rel)
    dist = mapped.value_counts()
    
    return [
        {"relation": k, "count": int(v)} 
        for k, v in dist.items() if k != "Other"
    ]


def ipd_vs_daycare_breakdown(df: pd.DataFrame, cols: dict) -> list:
    """Detect IPD vs Day Care from available columns."""
    # Look for indicators in 'Room Desc', 'Room Category', 'Diagnosis', 'Claim Type'
    possible_cols = [cols.get("claim_type"), "Room Desc", "Availed Room Category H", "Ip No"]
    # Check all columns for keywords — must ensure text_data never contains NaN
    text_data = pd.Series([""] * len(df), index=df.index)
    for c in df.columns:
        if c in _BLOCKLIST: continue
        col_str = df[c].astype(str).fillna("").str.upper()
        text_data = text_data.str.cat(col_str, sep=" ", na_rep="")
    text_data = text_data.fillna("").astype(str)

    def detect(txt):
        try:
            if not txt or pd.isna(txt): return "Other"
            t = str(txt).upper()
            if "DAY CARE" in t or "DAYCARE" in t: return "Day Care"
            if "IPD" in t or "INPATIENT" in t: return "IPD"
        except:
            pass
        return "Other"

    detected = text_data.apply(detect)
    dist = detected.value_counts()
    
    return [
        {"type": k, "count": int(v)}
        for k, v in dist.items() if k != "Other"
    ]


def ai_narrative(kpi: dict, hosp: list, trend: list, fl: list, disease: list) -> str:
    """Template-based executive narrative (works without any API key)."""
    total = kpi["total_claims"]
    incurred = kpi["total_incurred"]
    avg = kpi["avg_claim"]
    cashless_pct = kpi["cashless_pct"]
    approval_rate = kpi["approval_rate"]
    outlier_count = len(fl)

    top_hosp = hosp[0]["hospital"] if hosp else "N/A"
    top_hosp_claims = hosp[0]["count"] if hosp else 0
    top_hosp_amt = hosp[0]["total_amt"] if hosp else 0

    top_disease = disease[0]["category"] if disease else "N/A"

    # Trend insight
    trend_insight = ""
    if len(trend) >= 2:
        first = trend[0]
        last = trend[-1]
        if last["count"] > first["count"]:
            pct_change = round((last["count"] - first["count"]) / first["count"] * 100, 1)
            trend_insight = f"Claim volume grew by **{pct_change}%** from {first['month']} to {last['month']}."
        else:
            pct_change = round((first["count"] - last["count"]) / first["count"] * 100, 1)
            trend_insight = f"Claim volume declined by **{pct_change}%** from {first['month']} to {last['month']}."

    narrative = f"""
**Executive Summary**

This policy covers a total of **{total:,} claims** with a cumulative incurred liability of **₹{incurred:,.0f}** \
({_lakhs(incurred)}). The average claim size is **₹{avg:,.0f}**, indicating {"high-cost" if avg > 50000 else "moderate"} \
utilisation patterns.

**Claim Type Split:** {cashless_pct}% of claims are cashless, with the remaining {100 - cashless_pct:.1f}% filed as \
reimbursements. {"A high cashless ratio suggests strong network hospital usage." if cashless_pct > 60 else "A high reimbursement ratio may signal limited network penetration or member preference for non-empanelled hospitals."}

**Approval Rate:** {approval_rate}% of claims were approved or settled. \
{"This is a healthy approval rate." if approval_rate > 75 else "This approval rate warrants a review of rejection reasons to improve claimant experience."}

**Top Hospital:** **{top_hosp}** accounts for {top_hosp_claims} claims worth ₹{top_hosp_amt:,.0f}, making it the \
highest-utilisation provider. Scrutiny of this provider's billing patterns is recommended.

**Disease Burden:** The leading disease category is **{top_disease}**, which drives the highest claim frequency. \
Targeted wellness programs for this condition may reduce future costs.

{trend_insight}

**Risk Signals:** {outlier_count} claims were flagged as potential anomalies \
(unusually high amounts, billing irregularities, or short-stay high-value claims). \
These require further investigation before final settlement.
""".strip()

    return narrative


def _lakhs(amount: float) -> str:
    if amount >= 1e7:
        return f"₹{amount/1e7:.2f} Cr"
    elif amount >= 1e5:
        return f"₹{amount/1e5:.2f} L"
    else:
        return f"₹{amount:,.0f}"


def _detect_body_part(row: pd.Series, icd_col: str, diag_col: str) -> str:
    """Heuristic mapping of diagnosis to body part."""
    code = str(row.get(icd_col, "")).upper().strip() if isinstance(row.get(icd_col, ""), str) else ""
    diag = str(row.get(diag_col, "")).upper() if isinstance(row.get(diag_col, ""), str) else str(row.get(diag_col, "")).upper() if row.get(diag_col) is not None else ""
    # Ensure diag is always a string
    if not isinstance(diag, str):
        diag = str(diag) if diag is not None else ""
    
    # Keyword priority
    if any(x in diag for x in ["BRAIN", "MIND", "PSYCH", "HEAD", "SKULL", "MIGRAINE", "CONVULSION", "EYE", "EAR", "THROAT", "DENTAL"]): return "head"
    if any(x in diag for x in ["HEART", "CARDIAC", "CORONARY", "VALVE", "INFARCTION", "CHEST PAIN"]): return "heart"
    if any(x in diag for x in ["LUNG", "PULMONARY", "RESPIRATORY", "CHEST", "PNEUMONIA", "ASTHMA", "BRONCH"]): return "lungs"
    if any(x in diag for x in ["STOMACH", "DIGESTIVE", "GASTRO", "LIVER", "STOOL", "ABDOMEN", "APPENDIX", "HERNIA", "INTESTINE"]): return "stomach"
    if any(x in diag for x in ["KIDNEY", "URINARY", "RENAL", "BLADDER", "STONE"]): return "kidneys"
    if any(x in diag for x in ["BONE", "FRACTURE", "MUSCLE", "JOINT", "ARTHRITIS", "SPINE", "BACK", "NECK", "KNEE", "HIP"]): return "bones"
    if any(x in diag for x in ["BLOOD", "ANEMIA", "LEUKEMIA", "VESSEL", "ARTER"]): return "vessels"
    if any(x in diag for x in ["SKIN", "DERMA", "BURN", "ULCER", "WOUND"]): return "skin"
    if any(x in diag for x in ["HAND", "LEG", "ARM", "FOOT", "LIMB", "HAND", "FINGER", "TOE"]): return "limbs"
    if any(x in diag for x in ["PREGNANCY", "DELIVERY", "LABOUR", "PELVIC", "UTERUS", "OVAR"]): return "pelvis"

    # ICD Chapter fallback
    letter = code[0] if code else "?"
    mapping = {
        "A": "lymph", "B": "lymph",
        "C": "lymph", "D": "vessels",
        "E": "stomach", "F": "head",
        "G": "head", "H": "head",
        "I": "heart", "J": "lungs",
        "K": "stomach", "L": "skin",
        "M": "bones", "N": "kidneys",
        "O": "pelvis", "S": "limbs", "T": "limbs"
    }
    return mapping.get(letter, "body")


def get_details_table(df: pd.DataFrame, cols: dict, max_rows: int = 1000) -> list:
    """Return all columns for the first N rows for the audit ledger."""
    # Replace NaNs with empty strings for JSON compatibility
    subset = df.head(max_rows).copy().fillna("")
    # Ensure all column names are strings for JSON keys
    subset.columns = [str(c) for c in subset.columns]
    return subset.to_dict(orient="records")


# ─── Top-level entry point ────────────────────────────────────────────────────

def analyze(path: str) -> dict:
    """Full analysis pipeline. Returns a JSON-serialisable dict."""
    sheets = read_file(path)
    df = _best_sheet(sheets)
    # Reset index to 0-based to prevent KeyError when header rows were skipped
    df = df.reset_index(drop=True)

    # Auto-detect columns
    cols = {role: _find_col(df, role) for role in ALIASES}

    # ── Strict Validation ─────────────────────────────────────────────────────
    # We require at least these 3 roles for any meaningful analysis
    critical_roles = ["claim_id", "incurred_amt", "admission_date"]
    missing_critical = [r for r in critical_roles if not cols.get(r)]
    
    if missing_critical:
        readable = [r.replace('_', ' ').title() for r in missing_critical]
        raise MappingError(
            f"Missing required columns: {', '.join(readable)}. "
            "Please ensure your Excel file contains these headers (or close matches)."
        )

    # Diagnostic logging
    detected_count = sum(1 for v in cols.values() if v)
    logger.info(f"📊 Column Mapping: Detected {detected_count} out of {len(ALIASES)} known roles.")
    logger.info(f"📋 Available columns in sheet: {list(df.columns)}")

    # Run all analyses
    kpi = kpis(df, cols)
    hosp = hospital_breakdown(df, cols)
    trend = monthly_trend(df, cols)
    cities = city_breakdown(df, cols)
    diseases = disease_breakdown(df, cols)
    outliers = outlier_detection(df, cols)
    fl = fraud_flags(df, cols)
    high_vals = high_value_claims(df, cols)
    status_dist = status_distribution(df, cols)
    type_dist = claim_type_dist(df, cols)
    gender_dist = gender_breakdown(df, cols)
    age_dist = age_breakdown(df, cols)
    try:
        relation_dist = relation_distribution(df, cols)
    except Exception:
        relation_dist = []
    try:
        ipd_dc = ipd_vs_daycare_breakdown(df, cols)
    except Exception:
        ipd_dc = []
    try:
        chronic = chronic_breakdown(df, cols)
    except Exception:
        chronic = []
    narrative = ai_narrative(kpi, hosp, trend, fl, diseases)
    details = get_details_table(df, cols)

    return {
        "file": os.path.basename(path),
        "kpis": kpi,
        "hospital_breakdown": hosp,
        "monthly_trend": trend,
        "city_breakdown": cities,
        "disease_breakdown": diseases,
        "chronic_breakdown": chronic,
        "outliers": outliers,
        "fraud_flags": fl,
        "high_value_claims": high_vals,
        "ipd_vs_daycare": ipd_dc,
        "relation_distribution": relation_dist,
        "status_distribution": status_dist,
        "claim_type_distribution": type_dist,
        "gender_breakdown": gender_dist,
        "age_breakdown": age_dist,
        "ai_narrative": narrative,
        "details": details,
        "column_map": {k: v for k, v in cols.items() if v},
    }

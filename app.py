"""
app.py – Flask server for Agentic AI Claim Intelligence Platform
New endpoints: /api/chat, /api/upload-policy, /api/policy-qa, /api/narrative
Run with: python app.py
"""

import os
import json
import tempfile
import math
import pandas as pd
import logging
from collections import OrderedDict
from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS
from analyzer import analyze, MappingError
from dotenv import load_dotenv

load_dotenv()

try:
    from supabase import create_client, Client
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY") # using service role key
    supabase: Client = create_client(supabase_url, supabase_key) if supabase_url and supabase_key else None
except ImportError:
    supabase = None

# ─── Logging Setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ClaimIQ")

def scrub_result(obj):
    if isinstance(obj, dict):
        return {k: scrub_result(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [scrub_result(v) for v in obj]
    elif pd.isna(obj):
        return None
    elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj

app = Flask(__name__, template_folder="templates", static_folder="static")

# CORS setup - allow local dev + deployed Vercel frontend
CORS(app, resources={r"/api/*": {"origins": "*"}})

app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB

@app.route("/health")
def health():
    return "OK", 200

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

SAMPLE_FILES = [
    
    "Claims Summary_API HOLDINGS_040202026.xlsb",
    "Claims Summary_Aarman Solutions_04022026.xlsb",
    "OG-26-1908-8403-00000070 Claim MIS.xlsx",
]

# ── Cache Config ─────────────────────────────────────────────────────────────
_df_store = OrderedDict() # Keyed by file name
MAX_CACHE_SIZE = 5

def _get_df(store_key: str):
    if store_key in _df_store:
        _df_store.move_to_end(store_key)
        return _df_store[store_key]
    return None


def _put_df(store_key: str, df, column_map: dict):
    if store_key in _df_store:
        _df_store.move_to_end(store_key)
    
    _df_store[store_key] = {"df": df.copy(), "column_map": column_map}
    
    if len(_df_store) > MAX_CACHE_SIZE:
        oldest_key, _ = _df_store.popitem(last=False)
        logger.info(f"🧠 Memory Management: Evicted '{oldest_key}' from cache.")


# ─── Existing endpoints ───────────────────────────────────────────────────────

@app.route("/")
def index():
    return jsonify({
        "status": "online",
        "message": "Claim Intelligence API is running. Please access the frontend via the React dev server (e.g. http://localhost:5173)."
    }), 200


@app.route("/api/analyze", methods=["POST"])
def analyze_upload():
    logger.info("📢 Analysis request received")
    if "file" not in request.files:
        logger.error("❌ No file in request")
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename:
        logger.error("❌ Empty filename")
        return jsonify({"error": "Empty filename"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    logger.info(f"📂 Processing file: {f.filename} (ext: {ext})")
    if ext not in (".xlsx", ".xlsb", ".xls"):
        logger.error(f"❌ Unsupported extension: {ext}")
        return jsonify({"error": "Only .xlsx / .xlsb / .xls files are supported"}), 400

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        f.save(tmp.name)
        tmp_path = tmp.name
        logger.info(f"💾 Saved to temp: {tmp_path}")

    try:
        from analyzer import read_file, _best_sheet, ALIASES, _find_col
        logger.info("🔍 Running analysis engine...")
        result = analyze(tmp_path)
        result["file"] = f.filename
        logger.info("✅ Analysis engine finished")

        # Cache the DataFrame for NL querying
        logger.info("⚙️ Caching DataFrame for chat...")
        sheets = read_file(tmp_path)
        df = _best_sheet(sheets)
        cols = {role: _find_col(df, role) for role in ALIASES}
        col_map = {k: v for k, v in cols.items() if v}
        _put_df(f.filename, df, col_map)
        
        if supabase:
            try:
                try:
                    supabase.storage.get_bucket("datasets")
                except:
                    supabase.storage.create_bucket("datasets")
                
                # 1. Upload the raw file
                with open(tmp_path, 'rb') as f_up:
                    supabase.storage.from_("datasets").upload(f.filename, f_up, file_options={"upsert": "true"})
                
                # 2. Cache the analysis result as JSON
                result_json = json.dumps(scrub_result(result))
                supabase.storage.from_("datasets").upload(f"{f.filename}.json", result_json.encode('utf-8'), file_options={"upsert": "true", "content-type": "application/json"})
                
                logger.info(f"✅ Uploaded {f.filename} and analysis cache to Supabase")
            except Exception as e:
                logger.error(f"⚠️ Failed to upload to Supabase: {e}")

        return jsonify(scrub_result(result))
    except MappingError as me:
        logger.warning(f"⚠️ Validation failure: {me}")
        return jsonify({"error": str(me)}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        os.unlink(tmp_path)


@app.route("/api/sample", methods=["GET"])
def analyze_sample():
    """
    Returns the list of sample files. 
    Frontend will now be responsible for analyzing them one-by-one or as needed.
    """
    logger.info(f"📁 Listing samples in {DATA_DIR}")
    results = []
    for fname in SAMPLE_FILES:
        path = os.path.join(DATA_DIR, fname)
        if os.path.exists(path):
            # Just return metadata for now to avoid time-consuming bulk analysis
            results.append({
                "file": fname,
                "status": "ready",
                "path": path,
                "size": os.path.getsize(path)
            })
        else:
            logger.warning(f"⚠️ Missing sample file: {fname}")

    if not results:
        # Diagnostic info
        ls = os.listdir(DATA_DIR)
        return jsonify({
            "error": "No sample files found",
            "debug": {
                "DATA_DIR": DATA_DIR,
                "dir_contents": ls
            }
        }), 404
    return jsonify({"files": results})


@app.route("/api/sample/analyze/<filename>", methods=["GET"])
def analyze_specific_sample(filename):
    """Bridge for lazy analysis of sample files."""
    from analyzer import read_file, _best_sheet, ALIASES, _find_col
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return jsonify({"error": f"File not found: {filename}"}), 404
    try:
        logger.info(f"🔍 Analyzing sample: {filename}")
        result = analyze(path)
        result["file"] = filename

        # Cache df for NL querying
        sheets = read_file(path)
        df = _best_sheet(sheets)
        cols = {role: _find_col(df, role) for role in ALIASES}
        col_map = {k: v for k, v in cols.items() if v}
        _put_df(filename, df, col_map)
        
        return jsonify(scrub_result(result))
    except MappingError as me:
        logger.warning(f"⚠️ Validation failure for {filename}: {me}")
        return jsonify({"error": str(me)}), 400
    except Exception as e:
        logger.error(f"🔥 Error analyzing {filename}: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/sample/<filename>", methods=["GET"])
def analyze_single_sample(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return jsonify({"error": f"File not found: {filename}"}), 404
    try:
        result = analyze(path)
        return jsonify(scrub_result(result))
    except MappingError as me:
        return jsonify({"error": str(me)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/files", methods=["GET"])
def list_sample_files():
    available = [f for f in SAMPLE_FILES if os.path.exists(os.path.join(DATA_DIR, f))]
    return jsonify({"files": available})


# ─── NEW: LLM Narrative ───────────────────────────────────────────────────────

@app.route("/api/narrative", methods=["POST"])
def llm_narrative():
    """
    Body: { api_key, file, kpis, hospital_breakdown, monthly_trend,
            fraud_flags, disease_breakdown }
    Returns: { narrative: str }
    """
    data = request.get_json(force=True)
    api_key = data.get("api_key", "").strip()
    if not api_key:
        return jsonify({"error": "api_key is required"}), 400

    try:
        from llm_agent import generate_narrative
        narrative = generate_narrative(
            kpis          = data.get("kpis", {}),
            hospital_data = data.get("hospital_breakdown", []),
            trend_data    = data.get("monthly_trend", []),
            fraud_flags   = data.get("fraud_flags", []),
            disease_data  = data.get("disease_breakdown", []),
            file_name     = data.get("file", "unknown"),
            api_key       = api_key,
        )
        return jsonify({"narrative": narrative})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── NEW: Text-to-Pandas Chat ─────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Body: { api_key, question, file }
    Returns: { code, explanation, result_html, error }
    """
    data = request.get_json(force=True)
    api_key  = data.get("api_key", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()
    question = data.get("question", "").strip()
    file_key = data.get("file", "")
    history_raw = data.get("history", [])
    
    # Format history for LLM
    history_str = ""
    for msg in history_raw[-5:]: # Last 5 messages for context
        role = "User" if msg.get("role") == "user" else "Assistant"
        content = msg.get("content", "")
        history_str += f"{role}: {content}\n"

    if not api_key:
        return jsonify({"error": "GEMINI_API_KEY is not set in .env"}), 400
    if not question:
        return jsonify({"error": "question is required"}), 400

    stored = _get_df(file_key)
    if stored is None:
        # Try to load from sample files
        for fname in SAMPLE_FILES:
            path = os.path.join(DATA_DIR, fname)
            if os.path.exists(path) and (not file_key or fname == file_key):
                from analyzer import read_file, _best_sheet, ALIASES, _find_col
                sheets = read_file(path)
                df = _best_sheet(sheets)
                cols = {role: _find_col(df, role) for role in ALIASES}
                col_map = {k: v for k, v in cols.items() if v}
                _put_df(fname, df, col_map)
                stored = _get_df(fname)
                break

    if stored is None and supabase is not None and file_key:
        try:
            logger.info(f"🔄 Attempting to download {file_key} from Supabase")
            res = supabase.storage.from_("datasets").download(file_key)
            if res:
                import tempfile
                tmp_path = os.path.join(tempfile.gettempdir(), file_key)
                with open(tmp_path, 'wb') as f:
                    f.write(res)
                from analyzer import read_file, _best_sheet, ALIASES, _find_col
                sheets = read_file(tmp_path)
                df = _best_sheet(sheets)
                cols = {role: _find_col(df, role) for role in ALIASES}
                col_map = {k: v for k, v in cols.items() if v}
                _put_df(file_key, df, col_map)
                stored = _get_df(file_key)
                logger.info(f"✅ Restored {file_key} from Supabase cache")
        except Exception as e:
            logger.error(f"Failed to download from supabase: {e}")

    if stored is None:
        return jsonify({"error": "No dataset loaded. Please analyze a file first."}), 400

    try:
        from llm_agent import text_to_pandas
        result = text_to_pandas(
            question   = question,
            df         = stored["df"],
            api_key    = api_key,
            column_map = stored.get("column_map"),
            history    = history_str,
        )
        logger.info(f"📤 Chat Response Generated: {result.get('explanation', '')[:100]}...")
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── NEW: PDF Policy Upload ───────────────────────────────────────────────────

@app.route("/api/upload-policy", methods=["POST"])
def upload_policy():
    """
    Multipart: file (PDF), api_key (form field)
    Returns: { store_id, chunks_count }
    """
    api_key = request.form.get("api_key", "").strip()
    if not api_key:
        return jsonify({"error": "api_key is required"}), 400
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    ext = os.path.splitext(f.filename)[1].lower()
    if ext != ".pdf":
        return jsonify({"error": "Only PDF files are supported"}), 400

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        f.save(tmp.name)
        tmp_path = tmp.name

    try:
        from pdf_rag import ingest_pdf, _cache_path, _file_hash
        import json as _json
        store_id = ingest_pdf(tmp_path, api_key)
        cache = _cache_path(store_id)
        store = _json.loads(cache.read_text(encoding="utf-8"))
        return jsonify({"store_id": store_id, "chunks_count": len(store), "filename": f.filename})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        os.unlink(tmp_path)


# ─── NEW: Policy Q&A ─────────────────────────────────────────────────────────

@app.route("/api/policy-qa", methods=["POST"])
def policy_qa():
    """
    Body: { api_key, question, store_id, top_k? }
    Returns: { answer, sources: [{page,score,snippet}] }
    """
    data     = request.get_json(force=True)
    api_key  = data.get("api_key", "").strip()
    question = data.get("question", "").strip()
    store_id = data.get("store_id", "").strip()
    top_k    = int(data.get("top_k", 5))

    if not api_key:
        return jsonify({"error": "api_key is required"}), 400
    if not question or not store_id:
        return jsonify({"error": "question and store_id are required"}), 400

    try:
        from pdf_rag import retrieve
        from llm_agent import answer_policy_question

        chunks = retrieve(question, api_key, store_id, top_k=top_k)
        answer = answer_policy_question(question, chunks, api_key)

        sources = [
            {"page": c["page"], "score": round(c["score"], 3),
             "snippet": c["text"][:200] + "…"}
            for c in chunks
        ]
        return jsonify({"answer": answer, "sources": sources})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── NEW: Download PPT ────────────────────────────────────────────────────────

@app.route("/api/download-ppt", methods=["POST"])
def download_ppt():
    """
    Accepts an Excel file upload, runs analysis, and returns an editable .pptx file.
    """
    logger.info("📢 PPT download request received")
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".xlsx", ".xlsb", ".xls"):
        return jsonify({"error": "Only .xlsx / .xlsb / .xls files are supported"}), 400

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        f.save(tmp.name)
        tmp_path = tmp.name

    try:
        logger.info(f"🔍 Running analysis for PPT: {f.filename}")
        result = analyze(tmp_path)
        result["file"] = f.filename

        logger.info("📊 Generating PPT...")
        from ppt_generator import generate_ppt
        ppt_buffer = generate_ppt(result)

        safe_name = os.path.splitext(f.filename)[0]
        download_name = f"{safe_name}_Report.pptx"

        from flask import send_file
        logger.info(f"✅ PPT generated: {download_name}")
        return send_file(
            ppt_buffer,
            mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            as_attachment=True,
            download_name=download_name
        )
    except Exception as e:
        logger.error(f"🔥 ERROR in download_ppt: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    finally:
        os.unlink(tmp_path)


# ─── NEW: Restore Analysis ────────────────────────────────────────────────────

@app.route("/api/restore", methods=["POST"])
def restore_analysis():
    """
    Body: { file }
    Restores analysis data from memory or Supabase.
    """
    data = request.get_json(force=True)
    file_key = data.get("file", "").strip()
    if not file_key:
        return jsonify({"error": "file name is required"}), 400

    if supabase is not None:
        try:
            logger.info(f"🔄 Checking cloud cache for {file_key}...")
            # Try to get the cached JSON first
            try:
                cached_data = supabase.storage.from_("datasets").download(f"{file_key}.json")
                if cached_data:
                    logger.info(f"🚀 Instant restore from JSON cache: {file_key}")
                    return jsonify(json.loads(cached_data))
            except:
                logger.info(f"Cache miss for {file_key}.json, falling back to full restore.")

            # Fallback: Download raw file and re-analyze
            res = supabase.storage.from_("datasets").download(file_key)
            if res:
                with tempfile.NamedTemporaryFile(suffix=os.path.splitext(file_key)[1], delete=False) as tmp:
                    tmp.write(res)
                    tmp_path = tmp.name
                
                try:
                    from analyzer import read_file, _best_sheet, ALIASES, _find_col
                    result = analyze(tmp_path)
                    result["file"] = file_key
                    
                    # Re-cache for chat
                    sheets = read_file(tmp_path)
                    df = _best_sheet(sheets)
                    cols = {role: _find_col(df, role) for role in ALIASES}
                    col_map = {k: v for k, v in cols.items() if v}
                    _put_df(file_key, df, col_map)
                    
                    # Update cloud cache
                    result_scrubbed = scrub_result(result)
                    supabase.storage.from_("datasets").upload(f"{file_key}.json", json.dumps(result_scrubbed).encode('utf-8'), file_options={"upsert": "true"})
                    
                    logger.info(f"✅ Successfully restored and re-cached {file_key}")
                    return jsonify(result_scrubbed)
                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
        except Exception as e:
            logger.error(f"Failed to restore from supabase: {e}")
            return jsonify({"error": f"Failed to restore: {str(e)}"}), 500

    return jsonify({"error": "Dataset not found in cloud storage"}), 404


# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("🚀 Claim Intelligence Platform starting on http://localhost:5001")
    app.run(debug=True, port=5001, host="0.0.0.0")

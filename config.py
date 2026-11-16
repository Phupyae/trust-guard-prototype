"""Central configuration. Every tunable number lives here so the team can
adjust behaviour without hunting through modules."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent
KNOWLEDGE_BASE_DIR = ROOT / "knowledge_base"
METADATA_FILE = KNOWLEDGE_BASE_DIR / "policy_metadata.json"


def _secret(name: str, default: str = "") -> str:
    """Read from env first, then Streamlit secrets (for Streamlit Cloud)."""
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st
        return st.secrets.get(name, default)
    except Exception:
        return default


ANTHROPIC_API_KEY = _secret("ANTHROPIC_API_KEY")
GEMINI_API_KEY = _secret("GEMINI_API_KEY")
LLM_PROVIDER = _secret("LLM_PROVIDER", "gemini").lower()
EMBEDDING_MODEL = _secret("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

# --- Two models, one provider (mentor guidance) ---
# Both agents use the SAME provider and the SAME policy repository. They differ in model
# tier, because of who they serve:
#   Agent 1 answers every employee question, so it runs on the cheapest, fastest tier.
#   TrustGuard checks each answer once, so it can afford a stronger tier.
# Override either with TRUSTGUARD_MODEL / AGENT1_MODEL in .env.
# Gemini defaults fit the FREE tier (500 requests/day per model): Agent 1 on the older
# 3.1 Flash-Lite generation (like an assistant already in production, which lags behind
# because every model change must pass model-risk review), TrustGuard on the newer 3.5
# Flash-Lite. With a paid key, a full tier split is one line in .env:
#   TRUSTGUARD_MODEL=gemini-3.8-flash   (free tier allows only ~20 requests/day for Flash)
STRONG_MODELS = {"gemini": "gemini-3.5-flash-lite", "claude": "claude-sonnet-5-5"}
CHEAP_MODELS = {"gemini": "gemini-3.1-flash-lite", "claude": "claude-haiku-5-5"}
TRUSTGUARD_MODEL = _secret("TRUSTGUARD_MODEL", "") or STRONG_MODELS.get(LLM_PROVIDER, "")
AGENT1_MODEL = _secret("AGENT1_MODEL", "") or CHEAP_MODELS.get(LLM_PROVIDER, "")
# Kept so old .env files still work, but no longer used: GEMINI_MODEL / CLAUDE_MODEL used
# to set ONE model for both agents, which is what the mentor asked us to change.
GEMINI_MODEL = TRUSTGUARD_MODEL if LLM_PROVIDER == "gemini" else CHEAP_MODELS["gemini"]
CLAUDE_MODEL = TRUSTGUARD_MODEL if LLM_PROVIDER == "claude" else CHEAP_MODELS["claude"]

GEMINI_MAX_OUTPUT_TOKENS = int(_secret("GEMINI_MAX_OUTPUT_TOKENS", "8192"))

# --- Retrieval ---
TOP_K = 3  # passages shown to the verifier per claim
# Minimum similarity for a passage to count as "relevant at all".
# Below this for every passage -> INSUFFICIENT_EVIDENCE without calling the LLM.
# Different embedders produce different score ranges, so each has its own threshold.
MIN_RELEVANCE = {"sentence-transformers": 0.30, "tfidf": 0.08}

# The governed policy repository: every document has an owner, version, status and dates.
# Superseded versions are KEPT (as in any document management system) so TrustGuard can
# check which version was in effect on a date and explain outdated answers. Whether a
# document can be used as evidence is decided per question by policy_validation.py.
GOVERNED_STATUSES = {"Approved", "Superseded"}
SEARCHABLE_STATUSES = {"Approved"}  # "current only" view (Agent 1's AGENT1_KB_SCOPE=approved)

# --- Agent 1: Banking AI Assistant ---
# Agent 1 simulates a typical deployed assistant, tuned for cost and speed because it
# serves every employee: cheapest model tier, and it reads only a few passages.
# It reads the SAME policy repository as TrustGuard, but like most simple assistants it
# indexes the text only: no version, status or effective-date filtering.
#   all      = the whole governed repository, including superseded versions (default)
#   approved = current versions only (a well-maintained assistant; use for the ablation)
#   none     = no documents at all; the LLM answers from general knowledge
AGENT1_KB_SCOPE = _secret("AGENT1_KB_SCOPE", "all").lower()
AGENT1_TOP_K = int(_secret("AGENT1_TOP_K", "2"))

# --- Input checks (modules/input_guard.py) ---
MAX_QUESTION_CHARS = 500
MIN_SECONDS_BETWEEN_QUESTIONS = 2
MAX_QUESTIONS_PER_MINUTE = 8

# --- Re-verification of TrustGuard's suggested correction (modules/reverify.py) ---
# Method C: a small natural-language-inference model (not a chatbot). Set ENABLE_NLI=false
# if it can't be installed/downloaded (e.g. low-memory hosting); methods A and B still run.
ENABLE_NLI = _secret("ENABLE_NLI", "true").lower() == "true"
NLI_MODEL = _secret("NLI_MODEL", "cross-encoder/nli-deberta-v3-xsmall")
NLI_ENTAIL_THRESHOLD = float(_secret("NLI_ENTAIL_THRESHOLD", "0.5"))
RULES_DIR = KNOWLEDGE_BASE_DIR / "rules"

# --- Logs (verification results, failures, blocked inputs, employee feedback) ---
LOG_DIR = Path(_secret("LOG_DIR", str(ROOT / "logs")))

# --- Extraction ---
MAX_CLAIMS = 10

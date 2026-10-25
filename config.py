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
LLM_PROVIDER = _secret("LLM_PROVIDER", "claude").lower()
CLAUDE_MODEL = _secret("CLAUDE_MODEL", "claude-haiku-5-5")
GEMINI_API_KEY = _secret("GEMINI_API_KEY")
# Flash-Lite: the free tier's daily request allowance is much higher for Flash-Lite
# than for Flash, and one verification uses ~3-4 requests.
GEMINI_MODEL = _secret("GEMINI_MODEL", "gemini-3.5-flash-lite")
EMBEDDING_MODEL = _secret("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

# --- Retrieval ---
TOP_K = 3  # passages shown to the verifier per claim
# Minimum similarity for a passage to count as "relevant at all".
# Below this for every passage -> INSUFFICIENT_EVIDENCE without calling the LLM.
# Different embedders produce different score ranges, so each has its own threshold.
MIN_RELEVANCE = {"sentence-transformers": 0.30, "tfidf": 0.08}

# Only search documents whose status is in this set. Superseded policies stay in
# the knowledge base (for the version-checking bonus feature) but aren't evidence.
SEARCHABLE_STATUSES = {"Approved"}

# --- Extraction ---
MAX_CLAIMS = 10

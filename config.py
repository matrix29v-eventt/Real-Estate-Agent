"""Central configuration: paths, environment loading and shared constants."""

from __future__ import annotations

import os
from pathlib import Path

try:  # python-dotenv is optional at import time so tests can run without it
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv missing is not fatal
    pass

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"


def db_path() -> Path:
    """Resolve the SQLite location at call time so tests can override it."""
    override = os.getenv("REALESTATE_DB")
    if override:
        return Path(override)
    return DATA_DIR / "realestate.db"


# --- LLM configuration -------------------------------------------------------
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "auto").strip().lower()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5").strip()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1").strip()
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "90"))

# --- Market constants --------------------------------------------------------
# The synthetic inventory models the Thiruvananthapuram (Trivandrum) market.
KNOWN_LOCATIONS = [
    "Kazhakkoottam",
    "Technopark",
    "Sreekaryam",
    "Akkulam",
    "Ulloor",
    "Pattom",
    "Kowdiar",
    "Vazhuthacaud",
    "Peroorkada",
    "Kesavadasapuram",
    "Thampanoor",
    "Poojappura",
]

# Areas that are commonly referred to together by buyers ("near Technopark").
LOCATION_NEIGHBOURS = {
    "technopark": ["Kazhakkoottam", "Sreekaryam", "Akkulam", "Ulloor"],
    "kazhakkoottam": ["Technopark", "Sreekaryam", "Akkulam"],
    "sreekaryam": ["Kazhakkoottam", "Ulloor", "Technopark"],
    "akkulam": ["Kazhakkoottam", "Technopark", "Ulloor"],
    "ulloor": ["Sreekaryam", "Pattom", "Akkulam"],
    "pattom": ["Kesavadasapuram", "Ulloor", "Kowdiar"],
    "kowdiar": ["Vazhuthacaud", "Pattom", "Peroorkada"],
    "vazhuthacaud": ["Kowdiar", "Thampanoor", "Poojappura"],
    "peroorkada": ["Kowdiar", "Poojappura"],
    "kesavadasapuram": ["Pattom", "Ulloor"],
    "thampanoor": ["Vazhuthacaud", "Poojappura"],
    "poojappura": ["Vazhuthacaud", "Peroorkada", "Thampanoor"],
}

PROPERTY_TYPES = ["Apartment", "Villa", "Plot", "Builder Floor"]
FURNISHING_OPTIONS = ["Unfurnished", "Semi-Furnished", "Fully-Furnished"]

LAKH = 100_000  # 1 lakh in rupees
CRORE = 10_000_000

APP_TITLE = "Real Estate Lead Qualification Agent"

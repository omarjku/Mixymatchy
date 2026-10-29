"""Paths and settings, read from the environment (.env at the repo root)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA_DIR = (ROOT / os.getenv("DATA_DIR", "data")).resolve()
PATIENT_ID = os.getenv("PATIENT_ID", "patient-0000-0001")
PATIENT_DIR = DATA_DIR / PATIENT_ID
CACHE_DIR = ROOT / "cache"
RULEBOOK_DIR = ROOT / "rulebook"
CASES_DIR = ROOT / "cases"

EXTRACT_MODEL = os.getenv("EXTRACT_MODEL", "claude-opus-5-5")
PARSE_MODEL = os.getenv("PARSE_MODEL", "claude-haiku-5-5")

# Present-tense questions are answered as of the latest document.
AS_OF_DEFAULT = "2016-04-15"

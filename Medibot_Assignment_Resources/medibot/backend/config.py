import os
from pathlib import Path

# Paths configuration
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = PROJECT_ROOT.parent / "mediassist_data" / "mediassist_data"
DB_PATH = DATA_DIR / "db" / "mediassist.db"
QDRANT_STORAGE_PATH = BACKEND_DIR / "qdrant_db"

# Ensure directories exist
QDRANT_STORAGE_PATH.mkdir(parents=True, exist_ok=True)

# RBAC configuration
RBAC_MATRIX = {
    "general": ["doctor", "nurse", "billing_executive", "technician", "admin"],
    "clinical": ["doctor", "admin"],
    "nursing": ["nurse", "doctor", "admin"],
    "billing": ["billing_executive", "admin"],
    "equipment": ["technician", "admin"],
}

# Supported Roles
ROLES = ["doctor", "nurse", "billing_executive", "technician", "admin"]

# SQL RAG access roles
SQL_RAG_ROLES = ["billing_executive", "admin"]

# Demo accounts username and passwords
DEMO_ACCOUNTS = {
    "dr.mehta": {"password": "doctor", "role": "doctor"},
    "nurse.priya": {"password": "nurse", "role": "nurse"},
    "billing.ravi": {"password": "billing_executive", "role": "billing_executive"},
    "tech.anand": {"password": "technician", "role": "technician"},
    "admin.sys": {"password": "admin", "role": "admin"},
}

# Vector Store configurations
COLLECTION_NAME = "medibot_chunks"
DENSE_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DENSE_DIMENSION = 384
SPARSE_MODEL_NAME = "prithivida/Splade_PP_en_v1"  # Splade model from fastembed
RERANK_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# LLM configurations
# Will fall back to Groq Llama 3.3 or similar if not specified
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")

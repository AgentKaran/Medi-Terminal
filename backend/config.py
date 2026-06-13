import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from the project root (parent of backend folder)
base_dir = Path(__file__).resolve().parent.parent
env_path = base_dir / ".env"
load_dotenv(dotenv_path=env_path)

# API Keys and Models
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
EMBED_MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Paths
DB_PATH = os.getenv("DB_PATH", str(base_dir / "mediassist_data" / "db" / "mediassist.db"))
QDRANT_PATH = os.getenv("QDRANT_PATH", str(base_dir / "mediassist_data" / "qdrant_db"))
DATA_DIR = base_dir / "mediassist_data"

# JWT Auth Settings
JWT_SECRET = os.getenv("JWT_SECRET", "super_secret_clinical_key_99")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))

# Role Definitions and Collections Mapping
ROLE_COLLECTIONS = {
    "doctor": ["general", "clinical", "nursing"],
    "nurse": ["general", "nursing"],
    "billing_executive": ["general", "billing"],
    "technician": ["general", "equipment"],
    "admin": ["general", "clinical", "nursing", "billing", "equipment"]
}

# Demo Credentials (password equals the role name)
DEMO_USERS = {
    "dr.mehta": "doctor",
    "nurse.priya": "nurse",
    "billing.ravi": "billing_executive",
    "tech.anand": "technician",
    "admin.sys": "admin"
}

# User to Role Mapping
USER_ROLES = {
    "dr.mehta": "doctor",
    "nurse.priya": "nurse",
    "billing.ravi": "billing_executive",
    "tech.anand": "technician",
    "admin.sys": "admin"
}

# Collection metadata details for RBAC refusal messages
COLLECTION_DISPLAY_NAMES = {
    "general": "general (HR, leave policy, FAQs)",
    "clinical": "clinical (treatment protocols, drug formulary, diagnostic guidelines)",
    "nursing": "nursing (procedures, ICU guidelines)",
    "billing": "billing (insurance codes, claim procedures)",
    "equipment": "equipment (manuals, calibration guides)"
}

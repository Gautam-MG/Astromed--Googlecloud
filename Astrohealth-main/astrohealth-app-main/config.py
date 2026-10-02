# =======================================================================
# AMEYA INNOVATIONS - SHARED CONFIGURATION MATRIX
# Environment configurations are securely pulled dynamically from runtime environments.
# =======================================================================
import os

# ── Prokerala API Credentials ──────────────────────
# Pulled safely from local system environment variables at runtime.
PROKERALA_CLIENT_ID     = os.environ.get("PROKERALA_CLIENT_ID", "3064f8fb-ccd73ab85d4")
PROKERALA_CLIENT_SECRET = os.environ.get("PROKERALA_CLIENT_SECRET")

# ── Gemini / LLM Configuration ─────────────────────
# Credentials mapped exclusively from isolated environment profiles.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL   = "gemini-2.5-flash"
LLM_PROVIDER   = "gemini"

# =======================================================================
# AMEYA INNOVATIONS - SHARED CONFIGURATION MATRIX
# Environment configurations are securely pulled dynamically from runtime environments.
# =======================================================================
import os

# Secrets are read only from the environment. There are no credential defaults.
PROKERALA_CLIENT_ID     = os.environ.get("PROKERALA_CLIENT_ID", "")
PROKERALA_CLIENT_SECRET = os.environ.get("PROKERALA_CLIENT_SECRET", "")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
LLM_PROVIDER   = "gemini"

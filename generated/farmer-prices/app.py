"""Generated USSD app: serves the verified bundle with the Revenant runtime.

Env: CALLBACK_TOKEN (required), UPSTREAM_BASE (REST upstream), AT_USERNAME / AT_API_KEY (SMS).
Secrets are read from the environment only and never stored in this folder.
"""
import json
import os
from pathlib import Path

from revenant.runtime.app import build_router

bundle = json.loads((Path(__file__).parent / "bundle.json").read_text())
app = build_router(bundle, os.environ["CALLBACK_TOKEN"], upstream_base=os.environ.get("UPSTREAM_BASE", ""))

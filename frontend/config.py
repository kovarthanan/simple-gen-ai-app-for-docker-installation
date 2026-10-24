"""Frontend settings (read from environment variables)."""
from __future__ import annotations

import os

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "180"))
REVIEWER_API_KEY = os.getenv("REVIEWER_API_KEY", "")
APP_TITLE = "Hybrid RAG"
# Shown as the tick on confidence meters; keep in sync with the backend policy
REVIEW_THRESHOLD = float(os.getenv("HITL_CONFIDENCE_THRESHOLD") or 0.6)

# Mirrors ENTITY_TYPES in the backend; used by the review editor
ENTITY_TYPES = ["Person", "Organization", "Location", "Product", "Technology",
                "Concept", "Event", "Date", "Document", "Other"]

# Design tokens. Colour carries provenance everywhere in the UI:
#   lapis = passages from the vector DB, saffron = knowledge-graph facts,
#   rose = needs a human, teal = approved / passed.
COLORS = {
    "fog": "#EEF1F6",
    "paper": "#FFFFFF",
    "ink": "#1A2233",
    "muted": "#5B6578",
    "line": "#D9DEE8",
    "lapis": "#2F5BEA",
    "saffron": "#D9860F",
    "rose": "#C8385F",
    "teal": "#12876F",
}

# Categorical colours for entity types (charts, graph explorer). They deliberately avoid
# lapis / saffron / rose so entity types never read as "passage", "graph fact" or "needs review".
LABEL_PALETTE = ["#7A4FD6", "#0F7C8C", "#B4592A", "#6E8B1F", "#A23E9C",
                 "#3F7CAC", "#C7A008", "#4B5A73", "#8C6D5A", "#2E9E5B"]

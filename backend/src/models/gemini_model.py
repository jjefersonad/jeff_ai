"""Google Gemini model configuration with retry and fallback support."""

import os

from langchain_google_genai import ChatGoogleGenerativeAI

from src.composition.env import load_env

load_env()

# Default instances
gemini_model = ChatGoogleGenerativeAI(
    model=os.getenv("GOOGLE_MODEL", "gemini-2.5-flash"),
    api_key=os.getenv("GOOGLE_API_KEY"),
    temperature=0.0,
    num_ctx=8192,
    timeout=30000,
)

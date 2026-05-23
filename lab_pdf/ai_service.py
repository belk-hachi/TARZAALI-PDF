"""
Gemini AI integration service.

Handles PDF extraction via the Google Gemini API.
The prompt content and request structure are NOT changed — only the
client lifecycle management has been refactored (singleton pattern).
"""

import os
import re
import json
import logging
from datetime import datetime

from google import genai
from google.genai import types

from .config import app_config, LOGS_DIR

logger = logging.getLogger(__name__)


class AIService:
    """Singleton Gemini AI client for PDF data extraction.

    Creates the genai.Client lazily on first use and reuses it
    for subsequent requests with the same API key. If the key
    changes (after a config save), the client is recreated.
    """

    def __init__(self):
        self._client = None
        self._api_key = None

    def _get_client(self, api_key):
        """Get or create a genai.Client, recreating if the key changed."""
        if self._client is None or self._api_key != api_key:
            self._client = genai.Client(api_key=api_key)
            self._api_key = api_key
        return self._client

    def extract_from_pdf(self, pdf_path, prompt, model_name=None):
        """Send a PDF file to Gemini for data extraction.

        Args:
            pdf_path: Path to the PDF file on disk.
            prompt: The extraction prompt text.
            model_name: Override model name. Defaults to config value.

        Returns:
            Parsed JSON dict from the AI response.

        Raises:
            Exception: If API key is missing, API call fails,
                       or response is not valid JSON.
        """
        config = app_config.load()
        api_key = config.get("api_key")
        if model_name is None:
            model_name = config.get("model", "gemini-2.5-flash")

        if not api_key:
            raise Exception(
                "Clé API Gemini manquante. Veuillez coller votre clé dans "
                "les paramètres ou 'gemini_key.txt' et relancer l'extraction."
            )

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        try:
            client = self._get_client(api_key)
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(
                        data=pdf_bytes, mime_type="application/pdf"
                    ),
                    types.Part.from_text(text=prompt),
                ],
            )
            raw_text = response.text.strip()
        except Exception as e:
            raise Exception(f"Gemini API call failed: {str(e)}")

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            raw_text = re.sub(r'^```(?:json)?\s*\n?', '', raw_text)
            raw_text = re.sub(r'\n?```\s*$', '', raw_text)

        try:
            result = json.loads(raw_text)
            _save_ai_log(
                prompt,
                f"[PDF sent directly: {os.path.basename(pdf_path)}]",
                result,
            )
            return result
        except json.JSONDecodeError as e:
            _save_ai_log(
                prompt,
                f"[PDF sent directly: {os.path.basename(pdf_path)}]",
                {"ERROR": "Invalid JSON", "RAW": raw_text},
            )
            raise Exception(
                f"L'IA a retourné un JSON invalide. Erreur : {str(e)}\n"
                f"Réponse brute :\n{raw_text}"
            )

    def list_models(self, api_key):
        """Fetch available Gemini models filtered for preferred versions.

        Returns a list of dicts with 'name' and 'display_name'.
        """
        try:
            client = self._get_client(api_key)
            include_keywords = ["flash"]
            exclude_keywords = [
                "tts", "nano", "image", "lite", "1.5", "2.0"
            ]

            models = [
                m for m in client.models.list()
                if "generateContent" in m.supported_actions
                and any(k in m.name.lower() for k in include_keywords)
                and not any(
                    k in m.name.lower() for k in exclude_keywords
                )
            ]

            return [
                {"name": m.name, "display_name": m.display_name}
                for m in models
            ]
        except Exception as e:
            logger.error("Failed to list models: %s", e)
            raise


def _save_ai_log(prompt, input_text, output_json):
    """Save the prompt, input text, and AI response to a log file.

    Log files are written to the logs/ directory for debugging.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_id = str(os.urandom(4).hex())
    log_filename = f"ai_log_{timestamp}_{log_id}.json"
    log_path = os.path.join(LOGS_DIR, log_filename)

    log_data = {
        "timestamp": datetime.now().isoformat(),
        "prompt": prompt,
        "input_text": input_text,
        "output_json": output_json,
    }

    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)
    logger.info("AI transaction saved to %s", log_filename)


# Module-level singleton
ai_service = AIService()

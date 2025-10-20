from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import requests

from app.ai.prompt import build_together_messages, build_vlm_payload
from app.util.config import AppConfig


class VLMClient:
    """Client that sends sampled frames and transcript to a multimodal endpoint."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.provider = (config.vlm_provider or "http").lower()

        if self.provider == "together":
            self._setup_together_client()
        else:
            self._setup_http_client()

    def _setup_http_client(self) -> None:
        if not self.config.vlm_endpoint:
            raise RuntimeError("VLM endpoint is not configured. Set VLM_ENDPOINT in the environment or config.")
        self.endpoint = self.config.vlm_endpoint
        self.api_key = self.config.vlm_api_key

    def _setup_together_client(self) -> None:
        try:
            from together import Together
        except ImportError as exc:  # pragma: no cover - handled at runtime
            raise RuntimeError(
                "The 'together' package is required for Together.ai integration. Install it via 'pip install together'."
            ) from exc

        api_key = self.config.vlm_api_key or os.getenv("TOGETHER_API_KEY")
        if not api_key:
            raise RuntimeError("Together API key not configured. Set TOGETHER_API_KEY or VLM_API_KEY.")

        os.environ.setdefault("TOGETHER_API_KEY", api_key)
        self._together_client = Together(api_key=api_key)
        self._together_model = self.config.vlm_model or "openai/gpt-oss-20b"

    def infer(self, transcript: str, images_b64: List[str], history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        if self.provider == "together":
            return self._infer_together(transcript, images_b64, history)
        return self._infer_http(transcript, images_b64, history)

    def _infer_http(self, transcript: str, images_b64: List[str], history: Optional[List[Dict[str, str]]]) -> Dict[str, Any]:
        payload = build_vlm_payload(self.config, transcript, images_b64, history=history)
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if "openrouter.ai" in self.endpoint:
            headers.setdefault("HTTP-Referer", "https://glasses.local")
            headers.setdefault("X-Title", "Glasses Assistant")

        response = requests.post(self.endpoint, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        data = response.json()
        return {"payload": payload, "response": data, "text": extract_text_from_response(data)}

    def _infer_together(self, transcript: str, images_b64: List[str], history: Optional[List[Dict[str, str]]]) -> Dict[str, Any]:
        messages = build_together_messages(self.config, transcript, images_b64, history=history)
        response = self._together_client.chat.completions.create(model=self._together_model, messages=messages)

        response_dict = response.model_dump() if hasattr(response, "model_dump") else _object_to_dict(response)
        text = extract_text_from_response(response_dict)
        payload = {"model": self._together_model, "messages": messages}
        return {"payload": payload, "response": response_dict, "text": text}


def extract_text_from_response(data: Dict[str, Any]) -> str:
    """Attempt to locate the assistant text in a few common response formats."""
    if "text" in data and isinstance(data["text"], str):
        return data["text"]
    if "result" in data and isinstance(data["result"], str):
        return data["result"]
    if "message" in data and isinstance(data["message"], str):
        return data["message"]
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0]
        if isinstance(choice, dict):
            message = choice.get("message", {})
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, list) and content:
                    first = content[0]
                    if isinstance(first, dict) and "text" in first:
                        return first["text"]
            if "text" in choice and isinstance(choice["text"], str):
                return choice["text"]
    return json.dumps(data)


def _object_to_dict(response: Any) -> Dict[str, Any]:
    try:
        return dict(response)
    except Exception:
        if hasattr(response, "__dict__"):
            return dict(response.__dict__)
    return {"raw": str(response)}

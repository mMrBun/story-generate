import base64
import time

import requests

from .config import Settings


class FluxImageGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()
        self.last_request_at = 0.0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self.last_request_at
        remaining = self.settings.flux_request_delay_seconds - elapsed
        if remaining > 0:
            print(f"Waiting {remaining:.2f}s before Flux request...")
            time.sleep(remaining)

    def generate(self, prompt: str, width: int, height: int) -> bytes:
        self._wait()
        response = self.session.post(
            self.settings.cloudflare_flux_url,
            headers={
                "Authorization": f"Bearer {self.settings.cloudflare_api_token}",
                "Content-Type": "application/json",
            },
            json={
                "prompt": prompt,
                "width": width,
                "height": height,
                "steps": self.settings.flux_steps,
            },
            timeout=180,
        )
        self.last_request_at = time.monotonic()
        response.raise_for_status()
        payload = response.json()

        image_payload = None
        result = payload.get("result")
        if isinstance(result, dict):
            image_payload = result.get("image") or result.get("b64_json")
        elif isinstance(result, str):
            image_payload = result
        image_payload = image_payload or payload.get("image") or payload.get("b64_json")

        if not isinstance(image_payload, str) or not image_payload.strip():
            raise RuntimeError(f"Flux returned unexpected payload keys: {payload.keys()}")

        if image_payload.startswith("data:image"):
            image_payload = image_payload.split(",", 1)[1]
        return base64.b64decode(image_payload)

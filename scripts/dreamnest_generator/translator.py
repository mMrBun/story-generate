import time

import requests

from .config import Settings

DEEPLX_LANGUAGE_CODES = {
    "zh-Hans": "zh",
    "en": "en",
    "ja": "ja",
    "ko": "ko",
}


class DeepLXTranslator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = requests.Session()
        self.last_request_at = 0.0
        self.next_url_index = 0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self.last_request_at
        remaining = self.settings.deeplx_request_delay_seconds - elapsed
        if remaining > 0:
            print(f"Waiting {remaining:.2f}s before DeepLX request...")
            time.sleep(remaining)

    def translate(self, text: str, source_language: str, target_language: str) -> str:
        if target_language == source_language:
            return text

        chunks = self._split_text(text)
        translated_chunks = [
            self._translate_chunk(chunk, source_language, target_language)
            for chunk in chunks
        ]
        return "\n\n".join(chunk for chunk in translated_chunks if chunk.strip()).strip()

    def _translate_chunk(self, text: str, source_language: str, target_language: str) -> str:
        source_code = DEEPLX_LANGUAGE_CODES.get(source_language, source_language)
        target_code = DEEPLX_LANGUAGE_CODES.get(target_language, target_language)
        last_error: Exception | None = None

        for attempt in range(1, self.settings.deeplx_max_retries + 1):
            endpoint = self._next_endpoint()
            try:
                self._wait()
                response = self.session.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {self.settings.deeplx_token}",
                        "Content-Type": "application/json",
                        # Cloudflare Worker / upstream DeepL occasionally gets stuck on a reused
                        # connection after a 5xx. Force one request per connection for stability.
                        "Connection": "close",
                    },
                    json={"text": text, "from": source_code, "to": target_code},
                    timeout=120,
                )
                self.last_request_at = time.monotonic()

                if response.status_code >= 400:
                    body = response.text[:500].replace("\n", " ")
                    raise RuntimeError(f"DeepLX HTTP {response.status_code}: {body}")

                payload = response.json()
                translated = payload.get("data") or payload.get("translation") or payload.get("result")
                if isinstance(translated, dict):
                    translated = translated.get("text") or translated.get("translation")
                if not isinstance(translated, str) or not translated.strip():
                    raise RuntimeError(f"DeepLX returned unexpected payload: {payload}")
                return translated.strip()
            except Exception as exc:
                last_error = exc
                self._reset_session()
                if attempt >= self.settings.deeplx_max_retries:
                    break

                wait_seconds = self._retry_wait_seconds(attempt)
                print(
                    f"DeepLX translation attempt {attempt}/{self.settings.deeplx_max_retries} "
                    f"failed for {source_language}->{target_language}: {exc}. "
                    f"Retrying in {wait_seconds:.1f}s..."
                )
                time.sleep(wait_seconds)

        raise RuntimeError(
            f"DeepLX translation failed after {self.settings.deeplx_max_retries} attempts "
            f"for {source_language}->{target_language}: {last_error}"
        )

    def _next_endpoint(self) -> str:
        endpoints = [url for url in self.settings.deeplx_urls if url.strip()] or [self.settings.deeplx_url]
        endpoint = endpoints[self.next_url_index % len(endpoints)]
        self.next_url_index += 1
        return endpoint

    def _retry_wait_seconds(self, attempt: int) -> float:
        # A Cloudflare Worker 5xx often means the upstream path is temporarily poisoned.
        # Use a long cooldown plus exponential backoff rather than hammering the same Worker.
        return self.settings.deeplx_error_cooldown_seconds + self.settings.deeplx_retry_delay_seconds * (2 ** (attempt - 1))

    def _reset_session(self) -> None:
        try:
            self.session.close()
        finally:
            self.session = requests.Session()

    def _split_text(self, text: str) -> list[str]:
        normalized = text.strip()
        if not normalized:
            return [normalized]

        max_chars = self.settings.deeplx_max_chars_per_request
        if max_chars <= 0 or len(normalized) <= max_chars:
            return [normalized]

        paragraphs = [part.strip() for part in normalized.splitlines() if part.strip()]
        chunks: list[str] = []
        current = ""

        for paragraph in paragraphs:
            if len(paragraph) > max_chars:
                if current:
                    chunks.append(current)
                    current = ""
                chunks.extend(paragraph[index:index + max_chars] for index in range(0, len(paragraph), max_chars))
                continue

            candidate = paragraph if not current else f"{current}\n\n{paragraph}"
            if len(candidate) <= max_chars:
                current = candidate
            else:
                chunks.append(current)
                current = paragraph

        if current:
            chunks.append(current)

        return chunks or [normalized]

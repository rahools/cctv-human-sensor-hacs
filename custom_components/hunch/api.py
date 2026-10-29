from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp
from aiohttp import ClientSession, ClientTimeout, DigestAuthMiddleware, encode_basic_auth
from yarl import URL

from .const import (
    AUTH_AUTO,
    AUTH_BASIC,
    AUTH_DIGEST,
    CONF_AUTH_TYPE,
    CONF_PASSWORD,
    CONF_SERVER_URL,
    CONF_SNAPSHOT_URL,
    CONF_TOKEN,
    CONF_USERNAME,
    CONF_VERIFY_TLS,
    MAX_SNAPSHOT_BYTES,
)


class HunchConnectionError(Exception):
    pass


class HunchAuthenticationError(HunchConnectionError):
    pass


class HunchResponseError(HunchConnectionError):
    pass


def normalize_url(value: str, *, server: bool = False) -> str:
    try:
        url = URL(value.strip())
    except ValueError as error:
        raise ValueError("invalid_url") from error
    if url.scheme not in {"http", "https"} or not url.host:
        raise ValueError("invalid_url")
    if url.user is not None or url.password is not None:
        raise ValueError("credentials_in_url")
    return str(url).rstrip("/") if server else str(url)


class HunchClient:
    def __init__(self, session: ClientSession, config: dict[str, Any]) -> None:
        self._session = session
        self._base_url = config[CONF_SERVER_URL]
        self._token = config.get(CONF_TOKEN) or None
        self._verify_tls = config.get(CONF_VERIFY_TLS, True)

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = dict(extra or {})
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    async def status(self) -> dict[str, Any]:
        try:
            async with self._session.get(
                f"{self._base_url}/v1/status",
                headers=self._headers(),
                ssl=self._verify_tls,
                timeout=ClientTimeout(total=8),
            ) as response:
                if response.status == 401:
                    raise HunchAuthenticationError
                if response.status != 200:
                    raise HunchResponseError(f"Server returned HTTP {response.status}")
                data = await response.json()
        except (TimeoutError, aiohttp.ClientError, ValueError) as error:
            raise HunchConnectionError from error
        if not data.get("server_id") or not data.get("ready"):
            raise HunchResponseError("Server is not ready")
        return data

    async def detect(self, image: bytes, threshold: float) -> tuple[bool, float]:
        try:
            async with self._session.post(
                f"{self._base_url}/v1/detections/human",
                data=image,
                headers=self._headers({"Content-Type": "image/jpeg", "X-Decision-Threshold": str(threshold)}),
                ssl=self._verify_tls,
                timeout=ClientTimeout(total=25),
            ) as response:
                if response.status == 401:
                    raise HunchAuthenticationError
                if response.status != 200:
                    raise HunchResponseError(f"Detection returned HTTP {response.status}")
                data = await response.json()
                return bool(data["human"]), float(data["confidence"])
        except (HunchAuthenticationError, HunchResponseError):
            raise
        except (TimeoutError, aiohttp.ClientError, KeyError, TypeError, ValueError) as error:
            raise HunchConnectionError from error


@dataclass(slots=True)
class Snapshot:
    data: bytes
    content_type: str


class SnapshotClient:
    def __init__(self, session: ClientSession, config: dict[str, Any]) -> None:
        self._session = session
        self._url = config[CONF_SNAPSHOT_URL]
        self._auth_type = config.get(CONF_AUTH_TYPE, AUTH_AUTO)
        self._username = config.get(CONF_USERNAME, "")
        self._password = config.get(CONF_PASSWORD, "")
        self._verify_tls = config.get(CONF_VERIFY_TLS, True)

    async def fetch(self) -> Snapshot:
        response = await self._request()
        if response.status == 401 and self._auth_type == AUTH_AUTO and self._username:
            response.release()
            response = await self._request(basic=True)
        try:
            if response.status == 401:
                raise HunchAuthenticationError
            if response.status != 200:
                raise HunchResponseError(f"Snapshot returned HTTP {response.status}")
            content_type = response.content_type.lower()
            if content_type not in {"image/jpeg", "image/png", "application/octet-stream"}:
                raise HunchResponseError("Snapshot URL did not return a JPEG or PNG")
            body = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                body.extend(chunk)
                if len(body) > MAX_SNAPSHOT_BYTES:
                    raise HunchResponseError("Snapshot is too large")
            if not body:
                raise HunchResponseError("Snapshot is empty")
            return Snapshot(bytes(body), content_type)
        finally:
            response.release()

    async def _request(self, basic: bool = False):
        headers: dict[str, str] = {}
        middlewares: tuple[DigestAuthMiddleware, ...] = ()
        if self._username and self._auth_type != "none":
            if basic or self._auth_type == AUTH_BASIC:
                headers["Authorization"] = encode_basic_auth(self._username, self._password)
            elif self._auth_type in {AUTH_AUTO, AUTH_DIGEST}:
                middlewares = (DigestAuthMiddleware(login=self._username, password=self._password),)
        try:
            return await self._session.get(
                self._url,
                headers=headers,
                middlewares=middlewares,
                ssl=self._verify_tls,
                timeout=ClientTimeout(total=8),
            )
        except (TimeoutError, aiohttp.ClientError) as error:
            raise HunchConnectionError from error

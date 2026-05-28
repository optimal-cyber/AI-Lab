"""SAM.gov Entity Management API v3 client + parsing + PII redaction.

GET https://api.sam.gov/entity-information/v3/entities
    ?api_key=...&ueiSAM=... | &cageCode=...
    &includeSections=entityRegistration,coreData,assertions,pointsOfContact

Resilience (requirement: 10s timeout; retry 429/5xx w/ exp backoff; circuit
breaker opens after 5 consecutive failures). Parsing is defensive — the v3
payload nests deeply and sections are optional, so missing fields degrade to
None rather than raising. POC email/phone are redacted unless the caller is an
admin AND explicitly requests PII (threat model T-MCP-I).
"""

from __future__ import annotations

import re
from typing import Any, List, Optional

import httpx
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                      wait_exponential)

from .models import NaicsEntry, PointOfContact, SamEntity

SAM_V3_URL = "https://api.sam.gov/entity-information/v3/entities"
_UEI_RE = re.compile(r"^[A-Z0-9]{12}$")
_CAGE_RE = re.compile(r"^[A-Z0-9]{5}$")
_POC_KEYS = [
    "governmentBusinessPOC", "electronicBusinessPOC",
    "pastPerformancePOC", "governmentBusinessAlternatePOC",
]


class CircuitOpenError(RuntimeError):
    """Raised when the breaker is open — upstream is presumed unhealthy."""


class RetryableHTTPError(RuntimeError):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"retryable upstream status {status_code}")


class CircuitBreaker:
    def __init__(self, max_failures: int = 5):
        self.max_failures = max_failures
        self.consecutive_failures = 0
        self.open = False

    def before(self) -> None:
        if self.open:
            raise CircuitOpenError(
                f"SAM.gov circuit open after {self.consecutive_failures} failures")

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.open = False

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.max_failures:
            self.open = True


def classify_identifier(value: str) -> str:
    """Return 'uei', 'cage', or raise ValueError."""
    v = (value or "").strip().upper()
    if _UEI_RE.match(v):
        return "uei"
    if _CAGE_RE.match(v):
        return "cage"
    raise ValueError(
        "identifier must be a 12-char UEI or a 5-char CAGE code")


def _g(d: Any, *path: str) -> Any:
    """Safely walk nested dicts; return None on any miss."""
    cur = d
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def parse_entity(payload: dict) -> Optional[SamEntity]:
    data = (payload or {}).get("entityData") or []
    if not data:
        return None
    e = data[0]
    reg = e.get("entityRegistration", {}) or {}
    core = e.get("coreData", {}) or {}

    # business types (codes + descriptions)
    btypes: List[str] = []
    for bt in (_g(core, "businessTypes", "businessTypeList") or []):
        desc = bt.get("businessTypeDesc") or bt.get("businessTypeCode")
        if desc:
            btypes.append(desc)

    # NAICS (under assertions.goodsAndServices in v3)
    naics: List[NaicsEntry] = []
    primary = _g(e, "assertions", "goodsAndServices", "primaryNaics")
    naics_list = _g(e, "assertions", "goodsAndServices", "naicsList") or []
    for n in naics_list:
        code = n.get("naicsCode")
        if not code:
            continue
        naics.append(NaicsEntry(code=str(code),
                                description=n.get("naicsDescription"),
                                primary=(str(code) == str(primary))))

    # points of contact
    pocs: List[PointOfContact] = []
    poc_root = e.get("pointsOfContact", {}) or {}
    for key in _POC_KEYS:
        poc = poc_root.get(key)
        if not isinstance(poc, dict):
            continue
        name = " ".join(p for p in [poc.get("firstName"), poc.get("lastName")] if p)
        pocs.append(PointOfContact(
            type=key,
            name=name or None,
            title=poc.get("title"),
            email=poc.get("email"),
            phone=poc.get("usPhone") or poc.get("nonUSPhone"),
        ))

    return SamEntity(
        uei=reg.get("ueiSAM"),
        cage_code=reg.get("cageCode"),
        legal_business_name=reg.get("legalBusinessName"),
        registration_status=reg.get("registrationStatus"),
        registration_date=reg.get("registrationDate"),
        registration_expiration_date=reg.get("registrationExpirationDate"),
        business_types=btypes,
        naics=naics,
        points_of_contact=pocs,
    )


def redact_entity(entity: SamEntity, include_pii: bool, is_admin: bool) -> SamEntity:
    """Mask POC email/phone unless include_pii AND caller is admin (T-MCP-I)."""
    allow = bool(include_pii and is_admin)
    redacted_pocs = []
    for poc in entity.points_of_contact:
        if allow:
            redacted_pocs.append(poc)
        else:
            redacted_pocs.append(poc.model_copy(update={
                "email": "[REDACTED]" if poc.email else None,
                "phone": "[REDACTED]" if poc.phone else None,
            }))
    return entity.model_copy(update={"points_of_contact": redacted_pocs,
                                     "pii_included": allow})


class SAMClient:
    def __init__(self, api_key: str, timeout: float = 10.0,
                 breaker: Optional[CircuitBreaker] = None,
                 client: Optional[httpx.AsyncClient] = None):
        self.api_key = api_key
        self.timeout = timeout
        self.breaker = breaker or CircuitBreaker(max_failures=5)
        self._client = client  # injectable for tests

    async def _do_request(self, params: dict) -> dict:
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        owns = self._client is None
        try:
            resp = await client.get(SAM_V3_URL, params=params)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise RetryableHTTPError(resp.status_code)
            resp.raise_for_status()
            return resp.json()
        finally:
            if owns:
                await client.aclose()

    @retry(
        retry=retry_if_exception_type(RetryableHTTPError),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def _request_with_retry(self, params: dict) -> dict:
        return await self._do_request(params)

    async def lookup(self, uei_or_cage: str) -> Optional[SamEntity]:
        kind = classify_identifier(uei_or_cage)
        ident = uei_or_cage.strip().upper()
        params = {
            "api_key": self.api_key,
            "includeSections": "entityRegistration,coreData,assertions,pointsOfContact",
        }
        params["ueiSAM" if kind == "uei" else "cageCode"] = ident

        self.breaker.before()
        try:
            payload = await self._request_with_retry(params)
        except Exception:
            self.breaker.record_failure()
            raise
        self.breaker.record_success()
        return parse_entity(payload)

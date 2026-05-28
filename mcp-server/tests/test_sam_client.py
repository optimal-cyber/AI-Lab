import httpx
import pytest

from src import sam_client as sc


# ---- circuit breaker (unit) ------------------------------------------------
class TestCircuitBreaker:
    def test_opens_after_five(self):
        b = sc.CircuitBreaker(max_failures=5)
        for _ in range(5):
            b.record_failure()
        assert b.open
        with pytest.raises(sc.CircuitOpenError):
            b.before()

    def test_success_resets(self):
        b = sc.CircuitBreaker(max_failures=5)
        b.record_failure()
        b.record_failure()
        b.record_success()
        assert b.consecutive_failures == 0 and not b.open

    def test_closed_allows(self):
        sc.CircuitBreaker().before()  # no raise


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ---- lookup integration (MockTransport, no network) ------------------------
class TestLookup:
    @pytest.mark.asyncio
    async def test_success(self, sam_payload):
        def handler(request):
            assert "ueiSAM" in request.url.params or "cageCode" in request.url.params
            return httpx.Response(200, json=sam_payload)

        client = sc.SAMClient(api_key="k", client=_client(handler))
        entity = await client.lookup("ZQGGHJH74DW7")
        assert entity.legal_business_name == "OPTIMAL, LLC"
        assert client.breaker.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_retry_then_success(self, sam_payload):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(429, json={"error": "rate"})
            return httpx.Response(200, json=sam_payload)

        client = sc.SAMClient(api_key="k", client=_client(handler))
        entity = await client.lookup("14HQ0")
        assert entity is not None
        assert calls["n"] == 2  # retried once

    @pytest.mark.asyncio
    async def test_breaker_open_short_circuits(self):
        def handler(request):  # must not be called
            raise AssertionError("transport should not be hit when breaker is open")

        b = sc.CircuitBreaker(max_failures=1)
        b.open = True
        client = sc.SAMClient(api_key="k", breaker=b, client=_client(handler))
        with pytest.raises(sc.CircuitOpenError):
            await client.lookup("ZQGGHJH74DW7")

    @pytest.mark.asyncio
    async def test_invalid_identifier(self):
        client = sc.SAMClient(api_key="k", client=_client(lambda r: httpx.Response(200, json={})))
        with pytest.raises(ValueError):
            await client.lookup("not-an-id")

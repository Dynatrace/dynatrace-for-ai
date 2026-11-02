"""Reading every request attribute the tenant holds, over a transport that answers per id."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ..clients.transports import AttributeStub, ConfigReader, RateLimited, RequestAttributeConfig

# The per-id leg costs one request per request attribute and the endpoint rate-limits it, so a
# few at a time is enough: the transport's own backoff stays the exception rather than the rule.
_CONCURRENCY = 4


def read_request_attributes(reader: ConfigReader) -> tuple[RequestAttributeConfig, ...]:
    """Every request attribute the tenant holds, body included, in the order it listed them."""
    stubs = reader.list_stubs()
    with ThreadPoolExecutor(max_workers=_CONCURRENCY) as pool:
        # Mapped rather than collected as the reads complete: the order is the list endpoint's,
        # whatever order the answers arrive in, so two runs over an unchanged tenant produce the
        # same sequence and can be compared line for line.
        return tuple(pool.map(lambda stub: _read_one(reader, stub), stubs))


def _read_one(reader: ConfigReader, stub: AttributeStub) -> RequestAttributeConfig:
    """One body, or the reason there is none.

    A configuration the endpoint cannot render costs its own row and nothing more: a stored tag
    the backend cannot parse makes its own read fail for as long as it exists, and a run that
    gave up on it would never get through this tenant at all. A rate limit is the exception -
    it says nothing about this request attribute, so it is left to end the run.
    """
    try:
        return RequestAttributeConfig(stub.id, stub.name, reader.read_body(stub.id))
    except RateLimited:
        raise
    except Exception as failure:  # pylint: disable=broad-exception-caught
        return RequestAttributeConfig(stub.id, stub.name, {}, read_error=str(failure))

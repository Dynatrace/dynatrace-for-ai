"""What the rest of the tool sees of the two tenant transports.

The protocols live beside the values they exchange so a fake can satisfy them without importing a
real client, and so nothing above this module has to know that one transport speaks to the classic
host and the other to the platform host. Each transport owns its own base URL.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class RateLimited(Exception):
    """The tenant has stopped answering reads for now, and waiting it out did not work.

    Its own family because it says nothing about the request attribute being read: a read that
    fails this way is a statement about the run, and the run stops.
    """


@dataclass(frozen=True)
class AttributeStub:
    """What the list endpoint says about one request attribute: its id and its name, and no more.

    The stub carries no `enabled`, so no count of what is enabled can be taken from a listing -
    only from the bodies a per-id read returns.
    """

    id: str
    name: str


@dataclass(frozen=True)
class RequestAttributeConfig:
    """One request attribute as Config v1 returned it, body included.

    Or as it refused to: a body the endpoint would not answer with leaves `read_error` set and
    the body empty, so a request attribute that cannot be read is still a row rather than a gap
    in a list nothing can notice.
    """

    id: str
    name: str
    body: dict[str, Any]
    read_error: str | None = None

    @property
    def enabled(self) -> bool:
        return self.body.get("enabled") is True


@dataclass(frozen=True)
class DqlAnswer:
    """The rows a query came back with, and whether they are all of them.

    The platform reports when it capped a result set, and a capped answer cannot be told from a
    whole one by its rows alone - so completeness travels with the answer rather than being asked
    about afterwards.
    """

    records: list[dict[str, Any]]
    complete: bool


class ConfigReader(Protocol):
    """Reads request attributes from Config v1, which takes two calls to do.

    The two legs stay separate rather than hiding behind one method: list access does not prove
    body access, a connection check has to try each, and only the caller can decide what a
    single unreadable body should cost.
    """

    def list_stubs(self) -> list[AttributeStub]: ...

    def read_body(self, attribute_id: str) -> dict[str, Any]: ...


class QueryRunner(Protocol):
    """Runs DQL against Grail and blocks until the query finishes."""

    def answer(self, query: str, *, deadline_seconds: float = ...) -> DqlAnswer: ...

    def execute(self, query: str, *, deadline_seconds: float = ...) -> list[dict[str, Any]]: ...

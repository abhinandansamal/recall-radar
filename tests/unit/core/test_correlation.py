"""Tests for correlation IDs (US-002)."""

import asyncio

from rr_core.correlation import (
    bind_correlation_id,
    correlation_scope,
    get_correlation_id,
    new_correlation_id,
)


def test_new_ids_are_unique_hex() -> None:
    first, second = new_correlation_id(), new_correlation_id()
    assert first != second
    assert len(first) == 32
    int(first, 16)  # raises ValueError if not hexadecimal


def test_no_id_before_binding() -> None:
    assert get_correlation_id() is None


def test_bind_given_id() -> None:
    assert bind_correlation_id("abc") == "abc"
    assert get_correlation_id() == "abc"


def test_bind_creates_id_when_missing() -> None:
    cid = bind_correlation_id()
    assert get_correlation_id() == cid


def test_scope_restores_previous_id() -> None:
    bind_correlation_id("outer")
    with correlation_scope("inner") as cid:
        assert cid == "inner"
        assert get_correlation_id() == "inner"
    assert get_correlation_id() == "outer"


def test_scope_without_previous_id() -> None:
    with correlation_scope() as cid:
        assert get_correlation_id() == cid
    assert get_correlation_id() is None


async def test_each_task_keeps_its_own_id() -> None:
    async def worker(cid: str) -> list[str | None]:
        seen = []
        with correlation_scope(cid):
            seen.append(get_correlation_id())
            await asyncio.sleep(0)  # let the other task run in between
            seen.append(get_correlation_id())
        return seen

    first, second = await asyncio.gather(worker("task-a"), worker("task-b"))
    assert first == ["task-a", "task-a"]
    assert second == ["task-b", "task-b"]

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack

import pyreqwest
import pytest
from pyreqwest.client import ClientBuilder
from pyreqwest.logging import flush_logs
from pyreqwest.logging._internal import Timestamper

from tests.servers.server_subprocess import SubprocessServer
from tests.utils import wait_for


@pytest.mark.parametrize("level", [logging.DEBUG, logging.INFO])
@pytest.mark.parametrize("enabled", [True, False])
async def test_connection_verbose_logging(
    echo_server: SubprocessServer, caplog: pytest.LogCaptureFixture, level: int, enabled: bool
):
    caplog.set_level(level)

    async with ClientBuilder().connection_verbose(enabled).build() as client:
        assert (await client.get(echo_server.url).build().send()).status == 200

        if enabled and level <= logging.DEBUG:
            target = "reqwest::connect"
            record = next(rec for rec in caplog.records if rec.name == target)
            assert (
                hasattr(record, "_pyreqwest_log_timestamp")
                and hasattr(record, "_pyreqwest_start_time")
                and hasattr(record, "_pyreqwest_timestamper_applied")
                and hasattr(pyreqwest, "_start_time_ns")
            )
            assert record._pyreqwest_log_timestamp > 0
            assert record._pyreqwest_start_time > 0
            assert record._pyreqwest_start_time == pyreqwest._start_time_ns
            assert record.created == (record._pyreqwest_log_timestamp / 1e9)
            assert record.relativeCreated == (record._pyreqwest_log_timestamp - record._pyreqwest_start_time) / 1e6
            assert record._pyreqwest_timestamper_applied is True
            assert any(isinstance(f, Timestamper) for f in logging.getLogger(target).filters)
        else:
            assert not caplog.records


@pytest.mark.parametrize("flush_kind", ["body_read", "response_close", "client_close", "manual"])
async def test_connection_verbose_logging__streamed_request(
    echo_body_parts_server: SubprocessServer, caplog: pytest.LogCaptureFixture, flush_kind: str
):
    caplog.set_level(logging.DEBUG)

    buf_limit = 100
    parts = [str(i).encode() * buf_limit for i in range(10)]

    async def gen() -> AsyncGenerator[bytes, None]:
        for part in parts:
            yield part

    async def assert_logs() -> None:
        assert any(rec.name == "reqwest::connect" for rec in caplog.records)

    client = ClientBuilder().connection_verbose(True).build()
    req_ctx = AsyncExitStack()
    resp = await req_ctx.enter_async_context(
        client.post(echo_body_parts_server.url)
        .body_stream(gen())
        .streamed_read_buffer_limit(buf_limit)
        .build_streamed()
    )

    assert resp.status == 200
    await asyncio.sleep(0.1)
    assert not caplog.records

    if flush_kind == "body_read":
        assert await resp.bytes() == b"".join(parts)
        await wait_for(assert_logs)
    elif flush_kind == "response_close":
        await req_ctx.aclose()
        await wait_for(assert_logs)
    elif flush_kind == "client_close":
        await client.close()
        await assert_logs()
    else:
        assert flush_kind == "manual"
        flush_logs()
        await assert_logs()

    await req_ctx.aclose()
    await client.close()

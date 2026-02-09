import importlib
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from pyreqwest.client import ClientBuilder
from pyreqwest.http import Url
from syrupy import SnapshotAssertion  # type: ignore[attr-defined]

from examples._utils import CallableExample, collect_examples, run_example
from tests.utils import IS_CI, IS_OSX, IS_WINDOWS, docker_container, wait_for

EXAMPLE_FUNCS: list[tuple[str, CallableExample]] = [
    (p.stem, func)
    for p in (Path(__file__).parent.parent / "examples").iterdir()
    if p.suffix == ".py" and not p.name.startswith("_")
    for func in collect_examples(importlib.import_module(f"examples.{p.stem}"))
]
assert EXAMPLE_FUNCS
HTTPBIN_IMAGE = (
    "ghcr.io/mccutchen/go-httpbin:2.18.3@sha256:3992f3763e9ce5a4307eae0a869a78b4df3931dc8feba74ab823dd2444af6a6b"
)
HTTPBIN_CONTAINER = "httpbin-test-runner"


@pytest.fixture(scope="session")
async def httpbin() -> AsyncGenerator[Url, None]:
    async with docker_container(HTTPBIN_IMAGE, HTTPBIN_CONTAINER) as host_port:

        async def wait_server() -> Url:
            url = Url(f"http://localhost:{host_port}")
            async with ClientBuilder().build() as client:
                assert (await client.get(url / "get").build().send()).status == 200
            return url

        yield await wait_for(wait_server)


@pytest.mark.parametrize(("module", "func"), EXAMPLE_FUNCS)
@pytest.mark.skipif(IS_CI and (IS_OSX or IS_WINDOWS), reason="No docker setup in CI for OSX/Windows")
async def test_examples(
    capsys: pytest.CaptureFixture[str],
    httpbin: Url,
    snapshot: SnapshotAssertion,
    monkeypatch: pytest.MonkeyPatch,
    module: str,
    func: CallableExample,
) -> None:
    monkeypatch.setenv("HTTPBIN", str(httpbin))

    await run_example(func)

    normalized = capsys.readouterr().out.replace(f":{httpbin.port}/", ":<PORT>/")
    assert normalized == snapshot

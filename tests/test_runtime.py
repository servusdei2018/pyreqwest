import subprocess
import sys
from pathlib import Path

import pytest

from tests.servers.server_subprocess import SubprocessServer


@pytest.mark.parametrize("set_default", [False, True])
def test_runtime_config(echo_server: SubprocessServer, set_default: bool) -> None:
    test = Path(__file__).parent / "runtime_isolated_test.py"
    process = subprocess.run(  # noqa: S603
        [sys.executable, str(test), str(echo_server.url), str(set_default)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if process.returncode != 0:
        print(process.stderr)
    assert process.returncode == 0
    assert process.stdout.strip() == "OK"

"""Pytest configuration: path setup + fixtures compartidos."""
import os
import sys
import socket
import time
import subprocess
import threading

import pytest

# Add project root to path
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture(scope="session")
def mock_server():
    """Levanta el mock server para toda la sesión de tests."""
    from tests.mock_server import MockServer
    srv = MockServer("127.0.0.1", 1744)
    srv.start()
    # Wait for it to be listening
    for _ in range(50):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.2)
            s.connect(("127.0.0.1", 1744))
            s.close()
            break
        except OSError:
            time.sleep(0.05)
    else:
        pytest.fail("mock server no arrancó")
    yield srv
    srv.stop()


@pytest.fixture
def ps4_client(mock_server):
    """Cliente PS4DBG conectado al mock server (uno por test)."""
    from lib import PS4DBG
    # Resetear memoria simulada del mock server para que cada test empiece limpio
    mock_server.memories.clear()
    mock_server.notify_count = 0
    mock_server.last_notify = None
    c = PS4DBG("127.0.0.1", 1744, timeout=5.0)
    assert c.connect(), "no pudo conectar al mock"
    yield c
    c.disconnect()

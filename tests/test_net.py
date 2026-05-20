"""Hardened net module: URL validation rejects private/loopback hosts."""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from pa.net import UnsafeURLError, validate_url


def _mock_resolve(addr: str):
    return lambda host, port: [(socket.AF_INET, 0, 0, "", (addr, port))]


def test_rejects_non_http_scheme():
    with pytest.raises(UnsafeURLError):
        validate_url("file:///etc/passwd")
    with pytest.raises(UnsafeURLError):
        validate_url("gopher://example.com")


def test_rejects_empty():
    with pytest.raises(UnsafeURLError):
        validate_url("")


def test_rejects_literal_loopback():
    with pytest.raises(UnsafeURLError):
        validate_url("http://127.0.0.1:8765/")
    with pytest.raises(UnsafeURLError):
        validate_url("http://[::1]/")


def test_rejects_literal_rfc1918():
    for addr in ("10.0.0.1", "192.168.1.1", "172.16.5.5"):
        with pytest.raises(UnsafeURLError):
            validate_url(f"http://{addr}/")


def test_rejects_link_local():
    with pytest.raises(UnsafeURLError):
        validate_url("http://169.254.169.254/latest/meta-data/")


def test_rejects_hostname_resolving_to_private():
    with (
        patch("socket.getaddrinfo", side_effect=_mock_resolve("10.0.0.5")),
        pytest.raises(UnsafeURLError),
    ):
        validate_url("http://internal.example.com/")


def test_accepts_public_address():
    with patch("socket.getaddrinfo", side_effect=_mock_resolve("93.184.216.34")):
        # example.com's actual IP — should pass the public check.
        assert validate_url("http://example.com/") == "http://example.com/"


def test_accepts_literal_public_ip():
    assert validate_url("http://1.1.1.1/") == "http://1.1.1.1/"

"""Contrato do entrypoint Streamable HTTP, exercitado em memória."""
import logging

import httpx
import pytest
from fastmcp import FastMCP

from backend.derivatives.mcp import derivatives_server as server

PROD = "derivatives_chain"


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    for name in ("CONTEXT", "PROVIDER_MODE", "MCP_PORT"):
        monkeypatch.delenv("QUIMERA_DERIV_" + name, raising=False)

@pytest.mark.parametrize("override", [None, "9321"])
async def test_entrypoint_bind_and_http_guard(monkeypatch, override):
    if override:
        monkeypatch.setenv("QUIMERA_DERIV_MCP_PORT", override)
    for key, value in {"MCP_HOST": "0.0.0.0", "MCP_PATH": "/else", "READINESS": "C"}.items():
        monkeypatch.setenv("QUIMERA_DERIV_" + key, value)
    captured = {}

    def intercept(instance, **kwargs):
        captured.update(kwargs)
        captured["instance"] = instance

    monkeypatch.setattr(FastMCP, "run", intercept)
    assert server.main() == 0
    port = int(override or 8814)
    assert (captured["transport"], captured["host"], captured["port"], captured["path"]) == (
        "streamable-http", "127.0.0.1", port, "/mcp",
    )
    app = captured["instance"].http_app(**{key: captured[key] for key in
                                           ("transport", "path", "middleware")})
    host = f"127.0.0.1:{port}"
    alias = f"localhost:{port}"
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=f"http://{host}"
    ) as client:
        for authority in (host, alias):
            for origin in ([], [("Origin", f"http://{authority}")]):
                response = await client.post("/mcp", headers=[
                    ("Host", authority), ("Accept", "application/json, text/event-stream"), *origin
                ], json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                    "protocolVersion": "2025-11-25", "capabilities": {},
                    "clientInfo": {"name": "offline", "version": "1"}}})
                assert response.status_code == 200 and "quimera-derivatives" in response.text
        async def unreadable_body():
            pytest.fail("o guard leu o corpo recusado")
            yield b""  # gerador assíncrono para HTTPX

        for headers in (
            [("host", "external.invalid")], [("host", "127.0.0.1")],
            [("host", "127.0.0.1:1")], [("host", host), ("host", host)],
            [("origin", "null")], [("origin", "https://" + host)],
            [("origin", "http://external.invalid")], [("origin", "http://" + alias)],
            [("origin", "http://127.0.0.1:1")], [("origin", "http://" + host + "/path")],
            [("origin", "http://" + host)] * 2, [("origin", "")],
        ):
            response = await client.post("/mcp", headers=headers, content=unreadable_body())
            assert (response.status_code, response.content) == (403, b"")
        request = client.build_request("POST", "/mcp", content=unreadable_body())
        del request.headers["Host"]
        response = await client.send(request)
        assert (response.status_code, response.content) == (403, b"")


async def test_protocol_validation_never_echoes_supplied_input(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("QUIMERA_DERIV_CONTEXT", "test")
    monkeypatch.setenv("QUIMERA_DERIV_FIXTURE_DIR", "tests/fixtures/derivatives/synthetic")
    args = {}
    monkeypatch.setattr(FastMCP, "run", lambda instance, **kw: args.update(
        instance=instance, **kw,
    ))
    assert server.main() == 0
    app = args["instance"].http_app(
        path=args["path"], middleware=args["middleware"], json_response=True,
    )
    marker = "CANARIO_PROTOCOLO_SINTETICO_987"
    cases = [
        {"name": marker, "arguments": {}},
        {"name": PROD, "arguments": marker},
        {"name": PROD, "arguments": [marker]},
        {"name": PROD, "arguments": {}, "_meta": marker},
        {"name": PROD, "arguments": {"symbol": marker, "due_date": []}},
        {"name": PROD, "arguments": {marker: "extra"}},
    ]
    bodies = []
    async with app.router.lifespan_context(app), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8814",
    ) as client:
        headers = {"Accept": "application/json, text/event-stream"}
        init = await client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-11-25", "capabilities": {},
                "clientInfo": {"name": "wire", "version": "1"},
            },
        })
        assert init.status_code == 200
        headers["Mcp-Session-Id"] = init.headers["mcp-session-id"]
        headers["MCP-Protocol-Version"] = "2025-11-25"
        await client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })
        for i, params in enumerate(cases, 2):
            result = await client.post("/mcp", headers=headers, json={
                "jsonrpc": "2.0", "id": i, "method": "tools/call", "params": params,
            })
            bodies.append(result.text)
            if i == 2:
                assert result.status_code == 200 and result.json()["result"]["isError"] is True
                continue
            assert result.status_code == 400
            assert result.json() == {
                "jsonrpc": "2.0", "id": i,
                "error": {"code": -32600, "message": "Invalid request"},
            }
        notification = await client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "method": "notifications/progress",
            "params": {"progress": marker},
        })
        assert notification.status_code == 400 and marker not in notification.text
        closed = await client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 20, "method": "tools/call",
            "params": {"name": PROD, "arguments": {"symbol": "", "due_date": marker}},
        })
        assert closed.status_code == 200 and "LIVE_NOT_ACTIVATED" in closed.text
        assert marker not in closed.text
        for expiry, expected in (("2026-11-19", "DEMO_TEST_DATA"), (marker, "INVALID_ARGUMENTS")):
            demo = await client.post("/mcp", headers=headers, json={
                "jsonrpc": "2.0", "id": 21, "method": "tools/call",
                "params": {"name": "derivatives_chain_demo",
                           "arguments": {"symbol": "BOVA11", "due_date": expiry}},
            })
            assert demo.status_code == 200 and expected in demo.text
            assert marker not in demo.text
        bad_id = await client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": True, "method": "tools/call",
            "params": {"name": PROD, "arguments": {}},
        })
        assert bad_id.status_code == 400 and bad_id.json()["id"] is None
        oversized = await client.post("/mcp", headers=headers, content=b"x" * (64 * 1024 + 1))
    assert marker not in caplog.text
    assert all(marker not in body for body in bodies)
    assert oversized.status_code == 413


def test_invalid_startup_fails_before_serving(monkeypatch, capsys, caplog):
    marker = "CONFIGURACAO_SINTETICA_INVALIDA"
    monkeypatch.setenv("QUIMERA_DERIV_MCP_PORT", marker)
    monkeypatch.setattr(FastMCP, "run", lambda *a, **kw: pytest.fail("iniciou servidor"))
    assert server.main() == 2
    output = capsys.readouterr()
    assert marker not in output.out + output.err + caplog.text

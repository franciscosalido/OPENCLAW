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
            if isinstance(params["arguments"], dict) and "_meta" not in params:
                # Chamada bem formada fora do contrato: erro de tool em HTTP 200, para a
                # sessao do agente sobreviver; nome e argumentos originais nao voltam.
                assert result.status_code == 200
                payload = result.json()["result"]
                assert payload["isError"] is True
                assert payload["content"] == [{"type": "text", "text": "INVALID_TOOL_CALL"}]
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


async def _session(app, port=8814):
    """Abre uma sessao MCP em memoria e devolve (cliente, headers) ja inicializados."""
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                               base_url=f"http://127.0.0.1:{port}")
    headers = {"Accept": "application/json, text/event-stream"}
    init = await client.post("/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-11-25", "capabilities": {},
            "clientInfo": {"name": "revisao", "version": "1"}}})
    assert init.status_code == 200
    headers["Mcp-Session-Id"] = init.headers["mcp-session-id"]
    headers["MCP-Protocol-Version"] = "2025-11-25"
    await client.post("/mcp", headers=headers, json={
        "jsonrpc": "2.0", "method": "notifications/initialized"})
    return client, headers


def _entrypoint_app(monkeypatch, context):
    monkeypatch.setenv("QUIMERA_DERIV_CONTEXT", context)
    monkeypatch.setenv("QUIMERA_DERIV_FIXTURE_DIR", "tests/fixtures/derivatives/synthetic")
    args = {}
    monkeypatch.setattr(FastMCP, "run", lambda instance, **kw: args.update(
        instance=instance, **kw))
    assert server.main() == 0
    assert args["show_banner"] is False, "o banner do FastMCP consulta o PyPI"
    return args["instance"].http_app(path=args["path"], middleware=args["middleware"],
                                     json_response=True)


@pytest.mark.parametrize("context", ["prod", "test"])
async def test_rejected_tool_call_keeps_the_session_alive(monkeypatch, context):
    """Um erro de chamada do agente nao pode derrubar a sessao (HTTP 400 derruba)."""
    app = _entrypoint_app(monkeypatch, context)
    rejected = [
        {"name": PROD, "arguments": {"symbol": "BOVA11", "due_date": "2026-11-19",
                                     "mode": "offline_fixture"}},
        {"name": PROD, "arguments": {"symbol": 11, "due_date": "2026-11-19"}},
        {"name": PROD, "arguments": {"symbol": "BOVA11"}},
        {"name": "ferramenta_que_nao_existe", "arguments": {}},
        {"name": "derivatives_health", "arguments": {"x": "1"}},
    ]
    if context == "prod":
        rejected.append({"name": "derivatives_chain_demo",
                         "arguments": {"symbol": "BOVA11", "due_date": "2026-11-19"}})
    async with app.router.lifespan_context(app):
        client, headers = await _session(app)
        answers = []
        try:
            for i, params in enumerate(rejected, 2):
                result = await client.post("/mcp", headers=headers, json={
                    "jsonrpc": "2.0", "id": i, "method": "tools/call", "params": params})
                assert result.status_code == 200, params
                answers.append(result.json()["result"])
                alive = await client.post("/mcp", headers=headers, json={
                    "jsonrpc": "2.0", "id": 100 + i, "method": "tools/call",
                    "params": {"name": PROD, "arguments": {"symbol": "BOVA11",
                                                           "due_date": "2026-11-19"}}})
                assert alive.status_code == 200 and "LIVE_NOT_ACTIVATED" in alive.text
        finally:
            await client.aclose()
    expected = {"isError": True, "content": [{"type": "text", "text": "INVALID_TOOL_CALL"}]}
    for answer in answers:
        assert {key: answer[key] for key in expected} == expected
    # A demo desabilitada e indistinguivel de uma tool inexistente.
    assert all(answer == answers[0] for answer in answers)


async def test_request_id_is_echoed_only_when_short(monkeypatch):
    app = _entrypoint_app(monkeypatch, "prod")
    async with app.router.lifespan_context(app):
        client, headers = await _session(app)
        try:
            for request_id, echoed in (("abc", "abc"), (7, 7), ("Z" * 64, "Z" * 64),
                                       ("Z" * 65, None), ("Z" * 5000, None), (1.5, None)):
                result = await client.post("/mcp", headers=headers, json={
                    "jsonrpc": "2.0", "id": request_id, "method": 5})
                assert result.status_code == 400
                assert result.json()["id"] == echoed
                assert len(result.content) < 400
        finally:
            await client.aclose()


@pytest.mark.parametrize("context", ["prod", "test"])
async def test_guard_contract_matches_the_registered_tools(monkeypatch, context):
    """A guarda repete o schema das tools: este teste acusa qualquer divergencia."""
    from backend.derivatives.mcp.http_guard import _valid_call

    app = _entrypoint_app(monkeypatch, context)
    del app
    demo = context == "test"
    instance = server.create_derivatives_server(
        server.load_derivatives_mcp_config({"QUIMERA_DERIV_CONTEXT": context}))
    tools = {tool.name: tool.parameters for tool in await instance.list_tools()}
    assert ("derivatives_chain_demo" in tools) is demo
    for name, schema in tools.items():
        arguments = {field: "x" for field in schema.get("properties", {})}
        assert set(schema.get("required", [])) == set(arguments)
        assert all(spec == {"type": "string"} for spec in schema["properties"].values())
        assert _valid_call(name, arguments or None, demo), name
        assert not _valid_call(name, {**arguments, "extra": "x"}, demo), name
    assert not _valid_call("derivatives_chain_demo", {"symbol": "x", "due_date": "x"},
                           False)
    assert not _valid_call("outra", {}, demo)

"""app/llm.py against a real local HTTP server that speaks just enough of Ollama's
OpenAI-compatible API. This exercises the actual openai SDK + httpx stack end to end, so
it catches the bug that matters most this week: the SDK's Bearer header vs Nginx's Basic
auth header.
"""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.llm import (
    DEFAULT_OLLAMA_MODEL,
    LLMConfig,
    build_client,
    generate_answer,
    load_config,
)


class _FakeOllama(BaseHTTPRequestHandler):
    seen: list[dict] = []
    expected_auth: str | None = None
    fail_status: int | None = None

    def log_message(self, *args):  # silence
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        type(self).seen.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})

        if type(self).fail_status:
            self.send_response(type(self).fail_status)
            self.end_headers()
            return

        if type(self).expected_auth and self.headers.get("Authorization") != type(self).expected_auth:
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Ollama"')
            self.end_headers()
            return

        payload = {
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 0,
            "model": body["model"],
            "choices": [
                {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "  30 days.  "}}
            ],
            "usage": {"prompt_tokens": 120, "completion_tokens": 4, "total_tokens": 124},
        }
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def fake_ollama():
    _FakeOllama.seen = []
    _FakeOllama.expected_auth = None
    _FakeOllama.fail_status = None
    server = HTTPServer(("127.0.0.1", 0), _FakeOllama)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", _FakeOllama
    server.shutdown()


def test_load_config_defaults_to_openai():
    cfg = load_config(env={})
    assert cfg.provider == "openai"
    assert cfg.model == "gpt-4o-mini"


def test_load_config_ollama_from_env():
    cfg = load_config(
        env={
            "LLM_PROVIDER": "ollama",
            "OLLAMA_BASE_URL": "https://ollama.example.com/",
            "OLLAMA_BASIC_AUTH_USER": "rag",
            "OLLAMA_BASIC_AUTH_PASSWORD": "pw",
        }
    )
    assert cfg.provider == "ollama"
    assert cfg.model == DEFAULT_OLLAMA_MODEL
    assert cfg.base_url == "https://ollama.example.com"  # trailing slash stripped
    assert (cfg.basic_auth_user, cfg.basic_auth_password) == ("rag", "pw")


def test_explicit_provider_overrides_env():
    assert load_config("ollama", env={"LLM_PROVIDER": "openai"}).provider == "ollama"


def test_unknown_provider_rejected():
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        load_config(env={"LLM_PROVIDER": "bedrock"})


def test_generate_answer_over_the_wire_sends_basic_auth_not_bearer(fake_ollama):
    url, handler = fake_ollama
    handler.expected_auth = "Basic " + base64.b64encode(b"rag:s3cret").decode()
    cfg = LLMConfig(
        provider="ollama",
        model="llama3.2:3b",
        base_url=url,
        basic_auth_user="rag",
        basic_auth_password="s3cret",
    )

    result = generate_answer("How long is the refund window?", ["Refunds: 30 days."], config=cfg)

    assert result.answer == "30 days."  # stripped
    assert (result.input_tokens, result.output_tokens) == (120, 4)
    request = handler.seen[0]
    assert request["path"] == "/v1/chat/completions"
    assert request["auth"] == handler.expected_auth  # Basic, and the SDK's Bearer is gone
    assert request["body"]["model"] == "llama3.2:3b"
    assert request["body"]["temperature"] == 0
    assert "Refunds: 30 days." in request["body"]["messages"][1]["content"]


def test_wrong_credentials_surface_as_auth_error(fake_ollama):
    from openai import AuthenticationError

    url, handler = fake_ollama
    handler.expected_auth = "Basic " + base64.b64encode(b"rag:right").decode()
    cfg = LLMConfig(
        provider="ollama", model="m", base_url=url, basic_auth_user="rag", basic_auth_password="wrong"
    )
    with pytest.raises(AuthenticationError):
        generate_answer("q", ["c"], config=cfg, client=build_client(cfg).with_options(max_retries=0))


def test_no_credentials_configured_sends_no_basic_header(fake_ollama):
    url, handler = fake_ollama
    cfg = LLMConfig(provider="ollama", model="m", base_url=url)
    generate_answer("q", ["c"], config=cfg)
    # SDK falls back to its placeholder Bearer key -- fine for a local, unauthenticated Ollama.
    assert handler.seen[0]["auth"] == "Bearer ollama"


def test_openai_client_uses_default_endpoint():
    client = build_client(LLMConfig(provider="openai", model="gpt-4o-mini", api_key="sk-test"))
    assert "api.openai.com" in str(client.base_url)


def test_model_override_beats_env_for_both_providers():
    env = {"OLLAMA_MODEL": "llama3.2:3b", "OPENAI_MODEL": "gpt-4o-mini"}
    assert load_config("ollama", env=env, model="qwen2.5:14b-instruct").model == "qwen2.5:14b-instruct"
    assert load_config("openai", env=env, model="gpt-4o").model == "gpt-4o"
    assert load_config("ollama", env=env).model == "llama3.2:3b"  # no override -> env


def test_strip_reasoning_removes_think_blocks_only():
    from app.llm import strip_reasoning

    assert strip_reasoning("<think>\nthe context says 30\n</think>\n30 days.") == "30 days."
    assert strip_reasoning("<think>a</think>X<think>b</think> Y") == "X Y"
    assert strip_reasoning("  plain answer  ") == "plain answer"


def test_generate_answer_strips_reasoning_from_model_output():
    from types import SimpleNamespace

    from app.llm import LLMConfig, generate_answer

    reply = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="<think>hmm</think>30 days."))],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=9),
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: reply)))
    result = generate_answer("q", ["c"], config=LLMConfig(provider="ollama", model="qwen3:8b", base_url="http://x"), client=client)
    assert result.answer == "30 days."


def test_max_retries_flows_from_env_into_both_clients():
    for provider in ("openai", "ollama"):
        cfg = load_config(provider, env={"LLM_MAX_RETRIES": "0", "OLLAMA_BASE_URL": "http://x", "OPENAI_API_KEY": "sk-test"})
        assert cfg.max_retries == 0
        assert build_client(cfg).max_retries == 0
    default = load_config("ollama", env={})
    assert default.max_retries is None and build_client(default).max_retries == 2  # SDK default


def test_zero_retries_surfaces_a_503_instead_of_hiding_it(fake_ollama):
    from openai import InternalServerError

    url, handler = fake_ollama
    handler.fail_status = 503
    cfg = LLMConfig(provider="ollama", model="m", base_url=url, max_retries=0)
    with pytest.raises(InternalServerError):
        generate_answer("q", ["c"], config=cfg)
    assert len(handler.seen) == 1  # no retry happened

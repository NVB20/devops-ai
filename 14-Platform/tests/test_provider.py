"""Checks the LLM_PROVIDER switch: each provider gets its own base URL and model, and a typo fails at startup.
Each case imports app.main in a fresh Python, since the provider is read once at import."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROBE = "import json; from app import main; print(json.dumps({'provider': main.PROVIDER, 'model': main.MODEL, 'base_url': str(main.client.base_url)}))"


def load(env: dict) -> subprocess.CompletedProcess:
    # Only the variables under test: a developer's .env must not change the result
    base = {k: v for k, v in __import__("os").environ.items()
            if not k.startswith(("LLM_", "OLLAMA_", "OPENROUTER_"))}
    return subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, env={**base, "OPENROUTER_API_KEY": "x", **env},
                          capture_output=True, text=True, timeout=120)


def test_openrouter_is_the_default():
    out = load({})
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.splitlines()[-1]) == {
        "provider": "openrouter", "model": "openrouter/free", "base_url": "https://openrouter.ai/api/v1/"}


def test_ollama_uses_the_local_server_and_model():
    out = load({"LLM_PROVIDER": "Ollama", "OLLAMA_BASE_URL": "http://host.docker.internal:11434/v1", "OLLAMA_MODEL": "llama3.2:3b"})
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.splitlines()[-1]) == {
        "provider": "ollama", "model": "llama3.2:3b", "base_url": "http://host.docker.internal:11434/v1/"}


def test_an_unknown_provider_fails_at_startup():
    out = load({"LLM_PROVIDER": "openai"})
    assert out.returncode != 0
    assert "LLM_PROVIDER must be one of openrouter, ollama" in out.stderr

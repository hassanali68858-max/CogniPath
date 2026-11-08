import json
import os
import urllib.request
from dotenv import load_dotenv

load_dotenv()  # read settings from .env, even if llm.py is imported first

# Which backend to use: "ollama" (local) or "claude" (Anthropic API)
PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()

# Seconds to wait for the LLM; long texts (like a CV) need more time on a laptop
TIMEOUT = int(os.getenv("LLM_TIMEOUT", "300"))

# Ollama settings
MODEL = os.getenv("LLM_MODEL", "llama3.2:3b")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

# Claude settings (the API key is read from ANTHROPIC_API_KEY in .env)
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")


def ask_ollama(prompt):
    """Send a prompt to the local Ollama model and return its text answer."""
    body = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0},  # deterministic answers
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())["response"].strip()


def ask_claude(prompt):
    """Send a prompt to Claude via the Anthropic API and return its text answer."""
    import anthropic  # imported here so Ollama-only runs do not need it
    client = anthropic.Anthropic(timeout=TIMEOUT)  # uses ANTHROPIC_API_KEY
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in msg.content if block.type == "text").strip()


def ask_llm(prompt):
    """Send a prompt to the configured LLM backend and return its text answer."""
    if PROVIDER == "claude":
        return ask_claude(prompt)
    return ask_ollama(prompt)


if __name__ == "__main__":
    print("Provider:", PROVIDER)
    print(ask_llm("Explain in one sentence what a career advisor does."))
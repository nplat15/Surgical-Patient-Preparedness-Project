"""
Small LLM client used by Modules 2-4.

Pick a provider with environment variables:
    PREOP_LLM_PROVIDER = anthropic | openai | mock      (default: anthropic if ANTHROPIC_API_KEY is set,
                                                          openai if OPENAI_API_KEY is set, otherwise mock)
    PREOP_LLM_MODEL    = model name                      (default for anthropic: claude-sonnet-5-5;
                                                          required for openai)
    ANTHROPIC_API_KEY / OPENAI_API_KEY

"mock" makes no network calls: it answers from the rules-only baseline so the
app and evaluation can be tested without an API key. Mock results are NOT AI results.

Only send synthetic data to cloud LLMs. Do not send MIMIC data to a cloud LLM
without checking PhysioNet's rules for that.
"""
from __future__ import annotations

import json
import os
import re
import time


def default_provider():
    p = os.environ.get("PREOP_LLM_PROVIDER")
    if p:
        return p.lower()
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "mock"


class LLM:
    def __init__(self, provider=None, model=None, temperature=0.0, max_tokens=4000):
        self.provider = (provider or default_provider()).lower()
        self.temperature = temperature
        self.max_tokens = max_tokens
        if self.provider == "anthropic":
            import anthropic  # pip install anthropic
            self.client = anthropic.Anthropic()
            self.model = model or os.environ.get("PREOP_LLM_MODEL", "claude-sonnet-5-5")
        elif self.provider == "openai":
            import openai  # pip install openai
            self.client = openai.OpenAI()
            self.model = model or os.environ.get("PREOP_LLM_MODEL")
            if not self.model:
                raise ValueError("Set PREOP_LLM_MODEL to the OpenAI model you want to use.")
        elif self.provider == "mock":
            self.client, self.model = None, "mock"
        else:
            raise ValueError(f"Unknown provider {self.provider}")

    @property
    def is_mock(self):
        return self.provider == "mock"

    def complete(self, system, user):
        for attempt in range(3):
            try:
                if self.provider == "anthropic":
                    r = self.client.messages.create(model=self.model, max_tokens=self.max_tokens,
                                                    temperature=self.temperature, system=system,
                                                    messages=[{"role": "user", "content": user}])
                    return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
                if self.provider == "openai":
                    r = self.client.chat.completions.create(model=self.model, temperature=self.temperature,
                                                            messages=[{"role": "system", "content": system},
                                                                      {"role": "user", "content": user}])
                    return r.choices[0].message.content
                raise RuntimeError("mock provider has no completion endpoint")
            except Exception:  # network hiccup / rate limit: back off and retry
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))

    def complete_json(self, system, user):
        text = self.complete(system + "\n\nRespond with ONE JSON object only, no other text.", user)
        return parse_json(text)


def parse_json(text):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object in model output: {text[:200]}")
    return json.loads(text[start:end + 1])

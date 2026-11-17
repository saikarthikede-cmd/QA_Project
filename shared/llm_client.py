"""Runtime provider and API key management with multi-provider and round-robin support.

Supported providers:
- Groq (openai/gpt-oss-120b)
- OpenAI (gpt-4o-mini)
- Gemini (gemini-flash-latest / gemini-flash-lite-latest dynamic alias)
- Claude / Anthropic (claude-3-5-sonnet-20241022)
- CodeVector (kimi-k-2-7-code via coding gateway)

Supports comma-separated keys with thread-safe round-robin distribution and automatic
failover across keys on rate limits (429) or spikes in demand (503).
Auto-initializes from .env / environment variables if set.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, List, Optional, Tuple

import dotenv
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

try:
    import anthropic
    from langchain_anthropic import ChatAnthropic
    HAS_ANTHROPIC = True
except ImportError:
    anthropic = None
    ChatAnthropic = None
    HAS_ANTHROPIC = False

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_DEFAULT_MODEL = "openai/gpt-oss-120b"
OPENAI_DEFAULT_MODEL = "gpt-4o-mini"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
# Google provides dynamic model aliases:
# - 'gemini-flash-latest' automatically routes to the newest Gemini Flash model.
# - 'gemini-flash-lite-latest' automatically routes to the newest Flash-Lite model.
# Override with the GEMINI_MODEL env var if a specific version or flash-lite is preferred.
GEMINI_DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
ANTHROPIC_DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

# Discover CodeVector config from .codevector.json if present
CODEVECTOR_CONFIG_PATH = Path(__file__).parent.parent / ".codevector.json"
CODEVECTOR_BASE_URL = "https://coding-gateway.fissionlabs.com/v1"
CODEVECTOR_DEFAULT_MODEL = "kimi-k-2-7-code"

if CODEVECTOR_CONFIG_PATH.exists():
    try:
        with open(CODEVECTOR_CONFIG_PATH, "r", encoding="utf-8") as f:
            cv_cfg = json.load(f)
            gw = cv_cfg.get("gateway", "").rstrip("/")
            if gw:
                CODEVECTOR_BASE_URL = f"{gw}/v1" if not gw.endswith("/v1") else gw
            tools = cv_cfg.get("tools", [])
            for t in tools:
                if t.get("modelSlug"):
                    CODEVECTOR_DEFAULT_MODEL = t["modelSlug"]
                    break
    except Exception:
        pass

DISPLAY_NAME = {
    "groq": "Groq",
    "openai": "OpenAI",
    "gemini": "Gemini",
    "claude": "Claude",
    "anthropic": "Claude",
    "codevector": "CodeVector",
}
PROVIDERS = {
    "groq": (GROQ_DEFAULT_MODEL, GROQ_BASE_URL),
    "openai": (OPENAI_DEFAULT_MODEL, None),
    "gemini": (GEMINI_DEFAULT_MODEL, GEMINI_BASE_URL),
    "claude": (ANTHROPIC_DEFAULT_MODEL, None),
    "anthropic": (ANTHROPIC_DEFAULT_MODEL, None),
    "codevector": (CODEVECTOR_DEFAULT_MODEL, CODEVECTOR_BASE_URL),
}


class SetKeyRequest(BaseModel):
    provider: str
    api_key: str


class RoundRobinChatClient(Runnable):
    """Wraps one or more LLM clients (one per API key) and rotates between them
    in a round-robin order for load balancing, with automatic failover to the next
    key if one hits rate limits (429), capacity spikes (503), or auth errors.
    """

    def __init__(
        self,
        clients: List[Any],
        keys: List[str],
        provider: str,
        index: int = 0,
        lock: Optional[threading.Lock] = None,
    ):
        self.clients = clients
        self.keys = keys
        self.provider = provider
        self._index = index
        self._lock = lock if lock is not None else threading.Lock()

    @property
    def root_client(self):
        """Expose root_client for backwards compatibility or introspection."""
        if self.clients and hasattr(self.clients[0], "root_client"):
            return self.clients[0].root_client
        return None

    def bind(self, **kwargs) -> RoundRobinChatClient:
        bound_clients = [c.bind(**kwargs) for c in self.clients]
        return RoundRobinChatClient(
            clients=bound_clients,
            keys=self.keys,
            provider=self.provider,
            index=self._index,
            lock=self._lock,
        )

    def bind_tools(self, tools: List[dict], **kwargs) -> RoundRobinChatClient:
        bound_clients = [
            c.bind_tools(tools, **kwargs) if hasattr(c, "bind_tools") else c
            for c in self.clients
        ]
        return RoundRobinChatClient(
            clients=bound_clients,
            keys=self.keys,
            provider=self.provider,
            index=self._index,
            lock=self._lock,
        )

    def with_config(self, config: Optional[dict] = None, **kwargs) -> RoundRobinChatClient:
        bound_clients = [
            c.with_config(config, **kwargs) if hasattr(c, "with_config") else c
            for c in self.clients
        ]
        return RoundRobinChatClient(
            clients=bound_clients,
            keys=self.keys,
            provider=self.provider,
            index=self._index,
            lock=self._lock,
        )

    def invoke(self, input: Any, config: Optional[dict] = None, **kwargs) -> Any:
        n = len(self.clients)
        if n == 0:
            raise ValueError("No LLM clients available in round-robin pool.")

        with self._lock:
            start_idx = self._index
            self._index = (self._index + 1) % n

        last_error = None
        for attempt in range(n):
            current_idx = (start_idx + attempt) % n
            client = self.clients[current_idx]
            try:
                if config is not None:
                    return client.invoke(input, config=config, **kwargs)
                return client.invoke(input, **kwargs)
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                status_code = getattr(e, "status_code", None)
                is_failover_worthy = (
                    status_code in (429, 500, 502, 503, 504, 401, 403)
                    or "rate limit" in err_str
                    or "high demand" in err_str
                    or "spikes in demand" in err_str
                    or "unavailable" in err_str
                    or "quota" in err_str
                    or "overloaded" in err_str
                )
                if n > 1 and is_failover_worthy and attempt < n - 1:
                    print(
                        f"[RoundRobin] Key #{current_idx + 1}/{n} failed ({type(e).__name__}: {e}). "
                        f"Failing over to key #{(current_idx + 1) % n + 1}..."
                    )
                    continue
                raise
        if last_error:
            raise last_error


def _build_single_client(provider: str, api_key: str):
    provider = provider.lower()
    if provider in ("claude", "anthropic"):
        if not HAS_ANTHROPIC:
            raise ValueError("Claude / Anthropic support requires 'langchain-anthropic'.")
        return ChatAnthropic(
            model=ANTHROPIC_DEFAULT_MODEL,
            api_key=api_key,
            timeout=60.0,
            max_retries=3,
            temperature=0,
        )

    default_model, base_url = PROVIDERS[provider]
    return ChatOpenAI(
        model=default_model,
        api_key=api_key,
        base_url=base_url,
        timeout=60.0,
        max_retries=3,
        temperature=0,
    )


def _validate_single_key(provider: str, key: str, client: Any) -> None:
    # Bypass network call if key is obviously a mock/test key
    if key.lower().startswith(("test-", "mock-", "dummy-")):
        return
    name = DISPLAY_NAME.get(provider, provider)
    try:
        if provider in ("claude", "anthropic"):
            if HAS_ANTHROPIC and anthropic is not None:
                raw_c = anthropic.Anthropic(api_key=key)
                raw_c.models.list(limit=1)
        elif provider == "codevector":
            # Some custom gateways return 404 or 405 on /models; test via models.list()
            # but allow non-auth failures if the gateway route differs
            if hasattr(client, "root_client") and hasattr(client.root_client, "models"):
                try:
                    client.root_client.models.list()
                except Exception as ex:
                    status = getattr(ex, "status_code", None)
                    if status in (401, 403):
                        raise
        else:
            if hasattr(client, "root_client") and hasattr(client.root_client, "models"):
                client.root_client.models.list()
    except Exception as e:
        auth_err = False
        conn_err = False
        if "AuthenticationError" in type(e).__name__ or getattr(e, "status_code", None) in (401, 403):
            auth_err = True
        elif "APIConnectionError" in type(e).__name__:
            conn_err = True

        if auth_err:
            raise ValueError(f"{name} rejected this key — check it and try again.")
        if conn_err:
            raise ValueError(f"Could not reach {name}. Check your network and try again.")
        msg = getattr(e, "message", str(e))
        raise ValueError(f"{name} returned an error validating this key: {msg}")


def validate_key(
    provider: str, api_key: str, validate_network: bool = True
) -> Tuple[RoundRobinChatClient, str]:
    """Build a LangChain client (with round-robin failover if comma-separated)
    for `provider` and confirm the key(s) work.
    """
    provider = (provider or "").strip().lower()
    if provider not in PROVIDERS:
        raise ValueError(
            f"Unsupported provider: {provider!r}. Choose Groq, OpenAI, Gemini, Claude, or CodeVector."
        )
    canonical_provider = "claude" if provider == "anthropic" else provider

    api_key = (api_key or "").strip()
    if not api_key:
        raise ValueError("API key is required.")

    raw_keys = [k.strip() for k in api_key.split(",") if k.strip()]
    if not raw_keys:
        raise ValueError("API key is required.")

    clients = []
    for k in raw_keys:
        c = _build_single_client(canonical_provider, k)
        if validate_network:
            _validate_single_key(canonical_provider, k, c)
        clients.append(c)

    rr_client = RoundRobinChatClient(
        clients=clients,
        keys=raw_keys,
        provider=canonical_provider,
    )
    return rr_client, canonical_provider


def init_from_env() -> Tuple[Optional[RoundRobinChatClient], Optional[str]]:
    """Check .env and os.environ for configured API keys.
    Returns (RoundRobinChatClient, provider) if found, or (None, None).
    """
    try:
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            dotenv.load_dotenv(dotenv_path=env_path, override=False)
        else:
            dotenv.load_dotenv()
    except Exception:
        pass

    checks = [
        ("groq", ["GROQ_API_KEY", "GROQ_API_KEYS"]),
        ("openai", ["OPENAI_API_KEY", "OPENAI_API_KEYS"]),
        ("gemini", ["GEMINI_API_KEY", "GEMINI_API_KEYS"]),
        ("claude", ["ANTHROPIC_API_KEY", "ANTHROPIC_API_KEYS", "CLAUDE_API_KEY", "CLAUDE_API_KEYS"]),
        ("codevector", ["CODEVECTOR_API_KEY", "CODEVECTOR_API_KEYS"]),
    ]

    for prov, env_names in checks:
        for env_name in env_names:
            val = os.environ.get(env_name, "").strip()
            if val:
                try:
                    client, provider = validate_key(prov, val, validate_network=False)
                    return client, provider
                except Exception as e:
                    print(f"Warning: Failed to initialize {prov} from {env_name}: {e}")
    return None, None


def resolve_model(provider: Optional[str], groq_model: str) -> str:
    """Map a Groq model name to whatever this session's active provider needs."""
    prov = (provider or "").strip().lower()
    if prov == "openai":
        return OPENAI_DEFAULT_MODEL
    if prov == "gemini":
        return GEMINI_DEFAULT_MODEL
    if prov in ("claude", "anthropic"):
        return ANTHROPIC_DEFAULT_MODEL
    if prov == "codevector":
        return CODEVECTOR_DEFAULT_MODEL
    return groq_model

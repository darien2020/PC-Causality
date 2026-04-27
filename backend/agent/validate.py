"""Verify an Anthropic API key by making a tiny, free `count_tokens` call."""
from __future__ import annotations

import anthropic


def _shape_hint(key: str) -> str:
    """Describe the key shape (no secrets leaked) so the user can spot a typo."""
    n = len(key)
    if n == 0:
        return "(empty)"
    prefix = key[: min(11, n)]
    return f"{n} chars, starts with {prefix!r}"


async def validate_anthropic_key(key: str) -> tuple[bool, str | None]:
    # Cheap pre-check: catch obvious copy-paste mistakes before hitting the API.
    if key.startswith("sk-ant-oat"):
        return (
            False,
            "this looks like a Claude Code OAuth token, not an API key. "
            "Generate a key at console.anthropic.com → API Keys (starts with sk-ant-api).",
        )
    if not key.startswith("sk-ant-"):
        return (
            False,
            f"key doesn't start with 'sk-ant-' ({_shape_hint(key)}). "
            "Copy-paste error?",
        )

    try:
        client = anthropic.AsyncAnthropic(api_key=key)
        await client.messages.count_tokens(
            model="claude-haiku-4-5",
            messages=[{"role": "user", "content": "."}],
        )
        return True, None
    except anthropic.AuthenticationError:
        return (
            False,
            f"Anthropic rejected the key as invalid ({_shape_hint(key)}). "
            "Check it at console.anthropic.com → API Keys.",
        )
    except anthropic.PermissionDeniedError:
        return False, "API key lacks permission for the validation model"
    except anthropic.APIConnectionError as e:
        return False, f"network error during validation: {e}"
    except anthropic.APIError as e:
        return False, f"API error: {e}"
    except Exception as e:
        return False, f"unexpected error: {type(e).__name__}: {e}"

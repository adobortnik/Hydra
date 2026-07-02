"""
llm_provider.py — unified interface for chat + tool-calling across providers.

Supported:
  - openai_compat  →  any OpenAI-compatible HTTP API:
                       * OpenAI  (api.openai.com)
                       * DeepSeek (api.deepseek.com)
                       * Groq     (api.groq.com/openai)
                       * Ollama   (localhost:11434/v1)
                       * Anthropic native?  → use 'anthropic' provider instead
  - anthropic      →  Anthropic native API (better tool calling for Claude)

Usage:
    cfg = {"provider": "deepseek", "model": "deepseek-chat",
           "api_key": "...", "base_url": "https://api.deepseek.com/v1"}
    for chunk in stream_chat(cfg, messages, tools):
        ...

Each yielded chunk is one of:
    {"type": "text", "delta": "..."}
    {"type": "tool_call", "id": "...", "name": "...", "args": {...}}
    {"type": "tool_result", "id": "...", "result": {...}}
    {"type": "done", "stop_reason": "..."}
    {"type": "error", "error": "..."}

Tool execution is driven internally — caller passes tool registry
(name → callable) and we run each tool_call locally, feeding the result
back to the LLM for follow-up reasoning.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.error
from typing import Any, Callable, Iterable, Iterator


# OpenAI-compatible base URLs for known providers
PROVIDER_DEFAULTS = {
    "openai":     {"base_url": "https://api.openai.com/v1",
                   "model":    "gpt-4o-mini"},
    "deepseek":   {"base_url": "https://api.deepseek.com/v1",
                   "model":    "deepseek-chat"},
    "groq":       {"base_url": "https://api.groq.com/openai/v1",
                   "model":    "llama-3.3-70b-versatile"},
    "ollama":     {"base_url": "http://localhost:11434/v1",
                   "model":    "llama3.1:70b"},
    "openai_compat": {"base_url": "", "model": ""},
    "anthropic":  {"base_url": "https://api.anthropic.com/v1",
                   "model":    "claude-sonnet-4-5"},
}

# Providers that use the OpenAI Chat Completions wire format
OPENAI_COMPAT_PROVIDERS = {"openai", "deepseek", "groq", "ollama", "openai_compat"}


# ─────────────────────────────────────────────────────────────
# HTTP helpers (stdlib only — no extra deps)
# ─────────────────────────────────────────────────────────────
def _http_post_stream(url: str, headers: dict, body: dict, timeout: int = 120) -> Iterator[str]:
    """POST JSON, yield each line of a streaming response (SSE 'data: ...')."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").rstrip("\n\r")
                if not line:
                    continue
                yield line
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise RuntimeError(f"HTTP {e.code}: {body_text or e.reason}") from e


def _http_post_json(url: str, headers: dict, body: dict, timeout: int = 60) -> dict:
    """POST JSON, return parsed JSON response."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise RuntimeError(f"HTTP {e.code}: {body_text or e.reason}") from e


# ─────────────────────────────────────────────────────────────
# Provider config resolution
# ─────────────────────────────────────────────────────────────
def resolve_config(cfg: dict) -> dict:
    """Fill in defaults from PROVIDER_DEFAULTS based on cfg['provider']."""
    out = dict(cfg)
    provider = out.get("provider") or "openai_compat"
    defaults = PROVIDER_DEFAULTS.get(provider, {})
    out["provider"] = provider
    # IMPORTANT: replace empty strings too (setdefault only fills missing keys).
    # The settings form often saves "" for blank fields — those should fall
    # back to PROVIDER_DEFAULTS, not break.
    if not out.get("base_url"):
        out["base_url"] = defaults.get("base_url", "")
    if not out.get("model"):
        out["model"] = defaults.get("model", "")
    if not out.get("base_url"):
        raise ValueError(f"base_url not set for provider={provider}")
    if not out.get("model"):
        raise ValueError(f"model not set for provider={provider}")
    return out


def test_connection(cfg: dict) -> dict:
    """One-shot tiny chat to verify provider config is usable. Non-streaming."""
    cfg = resolve_config(cfg)
    try:
        if cfg["provider"] == "anthropic":
            return _test_anthropic(cfg)
        return _test_openai_compat(cfg)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _test_openai_compat(cfg: dict) -> dict:
    headers = {"Content-Type": "application/json"}
    if cfg.get("api_key"):
        headers["Authorization"] = f"Bearer {cfg['api_key']}"
    body = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": "Reply with exactly 'pong'"}],
        "max_tokens": 5,
    }
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    j = _http_post_json(url, headers, body, timeout=30)
    text = ""
    try:
        text = j["choices"][0]["message"]["content"]
    except Exception:
        pass
    return {"ok": True, "model": cfg["model"], "provider": cfg["provider"],
            "reply": (text or "")[:120]}


def _test_anthropic(cfg: dict) -> dict:
    headers = {
        "Content-Type": "application/json",
        "x-api-key": cfg.get("api_key", ""),
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model": cfg["model"],
        "max_tokens": 10,
        "messages": [{"role": "user", "content": "Reply with exactly 'pong'"}],
    }
    url = cfg["base_url"].rstrip("/") + "/messages"
    j = _http_post_json(url, headers, body, timeout=30)
    text = ""
    try:
        text = j["content"][0]["text"]
    except Exception:
        pass
    return {"ok": True, "model": cfg["model"], "provider": cfg["provider"],
            "reply": (text or "")[:120]}


# ─────────────────────────────────────────────────────────────
# Main entry — streaming chat with tool calling
# ─────────────────────────────────────────────────────────────
def stream_chat(cfg: dict,
                messages: list[dict],
                tools: list[dict],
                tool_runner: Callable[[str, dict], dict],
                max_tool_rounds: int = 6) -> Iterator[dict]:
    """
    Streaming chat with automatic tool execution.

    Args:
        cfg: provider config dict (provider, model, api_key, base_url)
        messages: chat history in OpenAI format [{role, content}, ...]
                  (system message can be the first one)
        tools: tool schemas in OpenAI shape (from hydra_tools.get_openai_tools())
        tool_runner: callable(name, args_dict) -> result_dict, runs locally
        max_tool_rounds: safety cap on tool-call loops

    Yields chunks (see module docstring).
    """
    cfg = resolve_config(cfg)
    if cfg["provider"] == "anthropic":
        yield from _stream_anthropic(cfg, messages, tools, tool_runner, max_tool_rounds)
    else:
        yield from _stream_openai_compat(cfg, messages, tools, tool_runner, max_tool_rounds)


# ─────────────────────────────────────────────────────────────
# OpenAI-compatible streaming (DeepSeek/Groq/OpenAI/Ollama)
# ─────────────────────────────────────────────────────────────
def _stream_openai_compat(cfg, messages, tools, tool_runner, max_rounds):
    headers = {"Content-Type": "application/json",
               "Accept": "text/event-stream"}
    if cfg.get("api_key"):
        headers["Authorization"] = f"Bearer {cfg['api_key']}"

    url = cfg["base_url"].rstrip("/") + "/chat/completions"

    # We mutate this list across tool rounds.
    history = list(messages)
    rounds = 0

    while True:
        rounds += 1
        if rounds > max_rounds:
            yield {"type": "error", "error": f"exceeded max tool rounds ({max_rounds})"}
            return

        body = {
            "model": cfg["model"],
            "messages": history,
            "stream": True,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        # Accumulators per round
        text_so_far = ""
        tool_calls: dict[int, dict] = {}  # index → { id, name, args_buf }
        finish_reason = None

        try:
            for line in _http_post_stream(url, headers, body, timeout=180):
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    obj = json.loads(payload)
                except Exception:
                    continue
                choices = obj.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                delta = choice.get("delta") or {}
                if delta.get("content"):
                    text_so_far += delta["content"]
                    yield {"type": "text", "delta": delta["content"]}
                for tc in (delta.get("tool_calls") or []):
                    idx = tc.get("index", 0)
                    slot = tool_calls.setdefault(idx, {"id": "", "name": "", "args_buf": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] = fn["name"]
                    if fn.get("arguments"):
                        slot["args_buf"] += fn["arguments"]
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]
        except Exception as e:
            yield {"type": "error", "error": str(e)}
            return

        # Add assistant message to history
        assistant_msg: dict = {"role": "assistant"}
        if text_so_far:
            assistant_msg["content"] = text_so_far
        if tool_calls:
            assistant_msg["tool_calls"] = []
            for idx in sorted(tool_calls.keys()):
                t = tool_calls[idx]
                try:
                    parsed_args = json.loads(t["args_buf"] or "{}")
                except Exception:
                    parsed_args = {}
                assistant_msg["tool_calls"].append({
                    "id": t["id"] or f"call_{idx}",
                    "type": "function",
                    "function": {"name": t["name"],
                                 "arguments": json.dumps(parsed_args)},
                })
        history.append(assistant_msg)

        # If no tool calls → done
        if not tool_calls:
            yield {"type": "done", "stop_reason": finish_reason or "stop"}
            return

        # Execute each tool call and feed result back
        for idx in sorted(tool_calls.keys()):
            t = tool_calls[idx]
            try:
                parsed_args = json.loads(t["args_buf"] or "{}")
            except Exception:
                parsed_args = {}
            yield {"type": "tool_call", "id": t["id"], "name": t["name"], "args": parsed_args}
            try:
                result = tool_runner(t["name"], parsed_args)
            except Exception as e:
                result = {"error": f"{type(e).__name__}: {e}"}
            yield {"type": "tool_result", "id": t["id"], "result": result}
            history.append({
                "role": "tool",
                "tool_call_id": t["id"] or f"call_{idx}",
                "name": t["name"],
                "content": json.dumps(result, default=str),
            })
        # loop back for follow-up reasoning


# ─────────────────────────────────────────────────────────────
# Anthropic native streaming
# ─────────────────────────────────────────────────────────────
def _stream_anthropic(cfg, messages, tools, tool_runner, max_rounds):
    headers = {
        "Content-Type": "application/json",
        "x-api-key": cfg.get("api_key", ""),
        "anthropic-version": "2023-06-01",
        "Accept": "text/event-stream",
    }
    url = cfg["base_url"].rstrip("/") + "/messages"

    # Split out system message (OpenAI puts it in messages[0], Anthropic has dedicated field)
    system_text = None
    msg_list = list(messages)
    if msg_list and msg_list[0].get("role") == "system":
        system_text = msg_list[0].get("content")
        msg_list = msg_list[1:]

    # Convert OpenAI tools → Anthropic tools
    anthropic_tools = []
    for t in tools or []:
        fn = t.get("function") or {}
        anthropic_tools.append({
            "name": fn.get("name"),
            "description": fn.get("description"),
            "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
        })

    history = msg_list
    rounds = 0
    while True:
        rounds += 1
        if rounds > max_rounds:
            yield {"type": "error", "error": f"exceeded max tool rounds ({max_rounds})"}
            return

        body = {
            "model": cfg["model"],
            "max_tokens": 4096,
            "messages": history,
            "stream": True,
        }
        if system_text:
            body["system"] = system_text
        if anthropic_tools:
            body["tools"] = anthropic_tools

        cur_blocks: list[dict] = []  # accumulated content blocks
        cur_block: dict | None = None
        cur_args_buf = ""
        finish_reason = None

        try:
            for line in _http_post_stream(url, headers, body, timeout=180):
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    obj = json.loads(payload)
                except Exception:
                    continue
                ev = obj.get("type")
                if ev == "content_block_start":
                    cur_block = dict(obj.get("content_block") or {})
                    cur_args_buf = ""
                elif ev == "content_block_delta":
                    delta = obj.get("delta") or {}
                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        if cur_block is not None:
                            cur_block["text"] = (cur_block.get("text") or "") + text
                        yield {"type": "text", "delta": text}
                    elif delta.get("type") == "input_json_delta":
                        cur_args_buf += delta.get("partial_json", "")
                elif ev == "content_block_stop":
                    if cur_block is not None:
                        if cur_block.get("type") == "tool_use":
                            try:
                                cur_block["input"] = json.loads(cur_args_buf or "{}")
                            except Exception:
                                cur_block["input"] = {}
                        cur_blocks.append(cur_block)
                        cur_block = None
                        cur_args_buf = ""
                elif ev == "message_delta":
                    delta = obj.get("delta") or {}
                    if delta.get("stop_reason"):
                        finish_reason = delta["stop_reason"]
        except Exception as e:
            yield {"type": "error", "error": str(e)}
            return

        # Add assistant message
        history.append({"role": "assistant", "content": cur_blocks})

        # Find tool_use blocks
        tool_uses = [b for b in cur_blocks if b.get("type") == "tool_use"]
        if not tool_uses:
            yield {"type": "done", "stop_reason": finish_reason or "end_turn"}
            return

        # Execute each tool, append tool_result to next user message
        tool_results = []
        for tu in tool_uses:
            args = tu.get("input") or {}
            yield {"type": "tool_call", "id": tu.get("id"),
                   "name": tu.get("name"), "args": args}
            try:
                result = tool_runner(tu.get("name"), args)
            except Exception as e:
                result = {"error": f"{type(e).__name__}: {e}"}
            yield {"type": "tool_result", "id": tu.get("id"), "result": result}
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.get("id"),
                "content": json.dumps(result, default=str),
            })

        history.append({"role": "user", "content": tool_results})
        # loop back

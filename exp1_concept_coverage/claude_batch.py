"""Message Batches helper for naming and the quiz (rows N1, N3, N8).

send(requests, out_dir, tag) submits a list of (custom_id, params) as Message Batches, waits, saves every request and
raw result as JSONL, resubmits errored or expired requests once, and returns {custom_id: outcome}. Each outcome holds
the parsed JSON answer (or why there is none) and the token usage. Prices are for cost tracking only.
"""
import json
import re
import time
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

# USD per million tokens (input, output), Anthropic model table cached 2026-10-06; batches cost 50% of these (N1)
PRICES = {"claude-opus-5-5": (4.00, 20.00), "claude-sonnet-5-5": (2.00, 10.00)}
BATCH_DISCOUNT = 0.5
MAX_PER_BATCH = 50_000  # below the API's 100,000-request limit
MAX_BATCH_BYTES = 200_000_000  # below the API's 256 MB limit; a naming request is about 13 KB
MAX_TOKENS = 16_000  # thinking counts toward this; the API reference's default for non-streaming requests
POLL_SECONDS = 60
CUSTOM_ID = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")  # the Batch API's rule for custom_id


def client():
    """N1: the key comes from ~/.anthropic_key (chmod 600), never from the repo."""
    key = Path("~/.anthropic_key").expanduser().read_text().strip()
    return anthropic.Anthropic(api_key=key)


def params(model, system, messages, schema, effort="high", max_tokens=MAX_TOKENS):
    """N3: adaptive thinking (the default on these models), explicit effort, no temperature; JSON answers (N4-N6).
    F7: the F run passes a lower max_tokens per request type."""
    return MessageCreateParamsNonStreaming(
        model=model, max_tokens=max_tokens, system=system, messages=messages,
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}})


def cost(model, input_tokens, output_tokens):
    key = next(k for k in PRICES if model.startswith(k))  # tolerate a longer reported id
    price_in, price_out = PRICES[key]
    return BATCH_DISCOUNT * (input_tokens * price_in + output_tokens * price_out) / 1e6


def worst_case(p, input_tokens):
    """F7: the most one request can cost: its input counted x1.1 plus the full output cap, at batch prices."""
    return cost(p["model"], 1.1 * input_tokens, p["max_tokens"])


def _outcome(result):
    """Turn one batch result into {status, answer, usage}. status: ok, refusal, max_tokens, bad_json, errored, ..."""
    if result.result.type != "succeeded":
        return {"status": result.result.type, "answer": None, "usage": None}
    msg = result.result.message
    usage = {"model": msg.model, "input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}
    if msg.stop_reason == "refusal":  # N8: counted, not retried
        return {"status": "refusal", "answer": None, "usage": usage}
    if msg.stop_reason == "max_tokens":
        return {"status": "max_tokens", "answer": None, "usage": usage}
    text = next((b.text for b in msg.content if b.type == "text"), None)
    try:
        return {"status": "ok", "answer": json.loads(text), "usage": usage}
    except (TypeError, json.JSONDecodeError):
        return {"status": "bad_json", "answer": None, "usage": usage}


def _run_once(api, requests, out_dir, tag):
    """Submit in chunks, wait for every batch to end, save raw results; return {custom_id: outcome}."""
    outcomes = {}
    chunks, current, size = [], [], 0
    for cid, p in requests:  # cut batches by count and by size
        n = len(json.dumps(p))
        if current and (len(current) == MAX_PER_BATCH or size + n > MAX_BATCH_BYTES):
            chunks.append(current)
            current, size = [], 0
        current.append((cid, p))
        size += n
    if current:
        chunks.append(current)
    for chunk in chunks:
        batch = api.messages.batches.create(requests=[Request(custom_id=cid, params=p) for cid, p in chunk])
        with open(out_dir / "batches.jsonl", "a") as f:
            f.write(json.dumps({"tag": tag, "batch_id": batch.id, "requests": len(chunk), "created": time.time()}) + "\n")
        print(f"[{tag}] batch {batch.id}: {len(chunk)} requests submitted", flush=True)
        while (batch := api.messages.batches.retrieve(batch.id)).processing_status != "ended":
            time.sleep(POLL_SECONDS)
        with open(out_dir / f"raw_{tag}.jsonl", "a") as f:
            for result in api.messages.batches.results(batch.id):  # results come in any order: key by custom_id (N8)
                f.write(result.model_dump_json() + "\n")
                outcomes[result.custom_id] = _outcome(result)
        print(f"[{tag}] batch {batch.id} ended: {batch.request_counts}", flush=True)
    return outcomes


def send(requests, out_dir, tag, guard=None):
    """N8: save requests, run the batches, resubmit errored or expired requests once, return {custom_id: outcome}.
    F7: guard(requests), if given, is called before each submission and raises to stop it."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ids = [cid for cid, _ in requests]
    if len(ids) != len(set(ids)):
        raise ValueError("custom_ids must be unique")
    if not all(CUSTOM_ID.match(cid) for cid in ids):
        raise ValueError("custom_ids may use only letters, digits, _ and -, at most 64 characters")
    with open(out_dir / f"requests_{tag}.jsonl", "w") as f:
        for cid, p in requests:
            f.write(json.dumps({"custom_id": cid, "params": p}) + "\n")
    api = client()
    if guard:
        guard(requests)
    outcomes = _run_once(api, requests, out_dir, tag)
    retry = [(cid, p) for cid, p in requests if outcomes.get(cid, {}).get("status") in ("errored", "expired", None)]
    if retry:
        print(f"[{tag}] resubmitting {len(retry)} errored or expired requests once", flush=True)
        if guard:
            guard(retry)
        outcomes.update(_run_once(api, retry, out_dir, f"{tag}_retry"))
    return outcomes


def usage_summary(outcomes, label_of):
    """Tokens, dollars and statuses per request type; label_of(custom_id) gives the type, e.g. 'naming'."""
    summary = {}
    for cid, o in outcomes.items():
        s = summary.setdefault(label_of(cid), {"requests": 0, "statuses": {}, "input_tokens": 0, "output_tokens": 0,
                                                "usd": 0.0})
        s["requests"] += 1
        s["statuses"][o["status"]] = s["statuses"].get(o["status"], 0) + 1
        if o["usage"]:
            s["input_tokens"] += o["usage"]["input_tokens"]
            s["output_tokens"] += o["usage"]["output_tokens"]
            s["usd"] += cost(o["usage"]["model"], o["usage"]["input_tokens"], o["usage"]["output_tokens"])
    for s in summary.values():
        s["usd"] = round(s["usd"], 4)
        s["usd_per_request"] = round(s["usd"] / max(s["requests"], 1), 6)
    return summary

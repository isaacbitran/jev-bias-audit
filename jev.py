"""Minimal dependency-free TypeSafe client. Reads TYPESAFE_API_KEY from the environment or this repo's .env; never prints it."""
import json, os, time, urllib.request, urllib.error

def _key():
    k = os.environ.get("TYPESAFE_API_KEY")
    if not k:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")) as f:
            for line in f:
                if line.startswith("TYPESAFE_API_KEY="):
                    k = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    assert k, "no key"
    return k

CALLS = {"n": 0, "input_tokens": 0, "ms": []}

def ask(state, questions, model="jev-latest", retries=4):
    body = json.dumps({"state": state, "model": model, "questions": questions}).encode()
    req = urllib.request.Request("https://api.typesafe.ai/v1/systemone", data=body,
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"})
    for attempt in range(retries):
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                out = json.loads(r.read())
            ms = (time.time() - t0) * 1000
            CALLS["n"] += 1; CALLS["ms"].append(ms)
            CALLS["input_tokens"] += out.get("usage", {}).get("input_tokens", 0)
            out["_ms"] = ms
            return out
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:300]
            if e.code in (429, 529) and attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1)); continue
            raise RuntimeError(f"HTTP {e.code}: {msg}")

def cost_usd():
    return CALLS["input_tokens"] * 0.042 / 1e6

def summary():
    ms = CALLS["ms"]
    return {"calls": CALLS["n"], "input_tokens": CALLS["input_tokens"], "cost_usd": round(cost_usd(), 5),
            "ms_median": round(sorted(ms)[len(ms)//2], 0) if ms else None, "ms_max": round(max(ms), 0) if ms else None}

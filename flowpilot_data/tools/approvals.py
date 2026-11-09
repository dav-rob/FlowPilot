"""Simulated approval authority for sensitive actions.

The authority is owned by the *harness* (a human or test), never exposed in the tool registry. Tokens are
HMAC-signed with a per-instance runtime secret, bound to (case, tool, canonical args) and single use.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from typing import Callable


def args_hash(args: dict) -> str:
    return hashlib.sha256(json.dumps(args, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()[:24]


class ApprovalAuthority:
    def __init__(self, auto_policy: Callable[[dict], bool] | None = None):
        """auto_policy(request)->bool lets demos/tests simulate an instant human decision; default is manual."""
        self._secret = secrets.token_bytes(32)  # runtime only: never derived from the dataset seed
        self._requests: dict[str, dict] = {}
        self._used: set[str] = set()
        self._n = 0
        self.auto_policy = auto_policy

    # called by sessions ---------------------------------------------------
    def submit(self, case_id: str, tool: str, args: dict, justification: str) -> dict:
        self._n += 1
        rid = f"APR-{secrets.token_hex(4).upper()}"
        req = {"request_id": rid, "case_id": case_id, "tool": tool, "args": dict(args), "args_hash": args_hash(args),
               "justification": justification, "status": "pending", "approver": None}
        self._requests[rid] = req
        if self.auto_policy is not None:
            self.decide(rid, bool(self.auto_policy(req)), approver="simulated-approver")
        return req

    def verify_and_consume(self, token: str, case_id: str, tool: str, args: dict) -> tuple[bool, str]:
        try:
            payload_b64, sig = token.rsplit(".", 1)
            expected = hmac.new(self._secret, payload_b64.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected):
                return False, "APPROVAL_INVALID"
            payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode()).decode())
        except Exception:
            return False, "APPROVAL_INVALID"
        if payload.get("n") in self._used:
            return False, "APPROVAL_REUSED"
        if payload.get("c") != case_id or payload.get("t") != tool or payload.get("a") != args_hash(args):
            return False, "APPROVAL_WRONG_SCOPE"
        self._used.add(payload["n"])
        return True, "OK"

    # called by the harness / human ---------------------------------------
    def pending(self) -> list[dict]:
        return [dict(r) for r in self._requests.values() if r["status"] == "pending"]

    def decide(self, request_id: str, approve: bool, approver: str = "human-approver") -> str | None:
        req = self._requests[request_id]
        if req["status"] != "pending":
            raise ValueError("request already decided")
        req["approver"] = approver
        if not approve:
            req["status"] = "denied"
            return None
        nonce = secrets.token_hex(8)
        payload = base64.urlsafe_b64encode(json.dumps({"c": req["case_id"], "t": req["tool"], "a": req["args_hash"], "r": request_id, "n": nonce}).encode()).decode()
        sig = hmac.new(self._secret, payload.encode(), hashlib.sha256).hexdigest()
        req["status"] = "approved"
        req["token"] = f"{payload}.{sig}"
        return req["token"]

    def get_token(self, request_id: str) -> str | None:
        return self._requests[request_id].get("token")

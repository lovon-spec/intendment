# SPDX-License-Identifier: MIT
"""RFC 001 revision 5 executable reference implementation (NOT a contract).

Pinned source and implementation decisions: docs/rfc-001-implementation.md.
The world includes a simulated registration host and a controllable resolver.
All public transitions roll back atomically, including money and events.
Money is integer base units; debt is NOT cash. No network or third-party packages.
The baseline model.py and the historical credited-model experiment are untouched.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
import hashlib
import json
from typing import Callable

MAX_UINT = 2**256 - 1
BPS = 10_000
REFUSE, REQUESTER, CLAIMANT = 0, 1, 2
Key = tuple[str, str, int]  # host, item identity, host request index
Account = tuple


class Rejected(ValueError):
    """Failed precondition: the entire modeled transaction is reverted."""


def require(ok: bool, message: str) -> None:
    if not ok:
        raise Rejected(message)


def uint(value: int) -> int:
    require(type(value) is int and 0 <= value <= MAX_UINT, "invalid uint256")
    return value


def address(value: str) -> str:
    require(type(value) is str and bool(value), "empty actor/domain")
    return value


def transaction(fn: Callable) -> Callable:
    @wraps(fn)
    def run(self: World, *args, **kwargs):
        old = deepcopy(self.__dict__)
        try:
            result = fn(self, *args, **kwargs)
            self.check()
            return result
        except Exception:
            self.__dict__.clear()
            self.__dict__.update(old)
            raise
    return run


class CaseState(str, Enum):
    OPEN = "open"
    MERITS = "merits"
    NEGOTIATING = "severity-negotiation"
    SEVERITY = "severity"
    FINISHED = "finished"


class TicketState(str, Enum):
    RESERVED = "reserved"
    BOUND = "bound"
    CANCELLED = "cancelled"
    RELEASED = "released"


@dataclass(frozen=True)
class Policy:
    version: str
    award: int = 30_000
    prepayment: int = 6_000
    merits_fee: int = 500
    severity_cap: int = 500
    challenger_deposit: int = 0
    ladder: tuple[int, ...] = (500, 1000, 3500, 6000, 10_000)
    challenge_period: int = 100
    settlement_window: int = 20
    severity_window: int = 20
    appeal_window: int = 20
    appeal_fees: tuple[int, ...] = (21_600, 50_400, 108_000, 372_000)
    winner_multiplier: int = 10_000
    loser_multiplier: int = 20_000
    shared_multiplier: int = 10_000
    resolver: str = "court"

    def __post_init__(self) -> None:
        address(self.version)
        address(self.resolver)
        for name in ("award", "prepayment", "merits_fee", "severity_cap",
                     "challenger_deposit", "winner_multiplier", "loser_multiplier",
                     "shared_multiplier"):
            uint(getattr(self, name))
        require(self.award >= self.prepayment, "prepayment exceeds award")
        require(self.merits_fee > 0 and self.severity_cap > 0, "positive court fees")
        for name in ("challenge_period", "settlement_window", "severity_window", "appeal_window"):
            require(uint(getattr(self, name)) > 0, "positive window")
        require(type(self.ladder) is tuple and 2 <= len(self.ladder) <= 64, "ladder size")
        require(all(uint(x) <= BPS for x in self.ladder), "ladder range")
        require(all(a < b for a, b in zip(self.ladder, self.ladder[1:])), "ladder order")
        require(self.ladder[-1] == BPS, "top rung is full award")
        require(type(self.appeal_fees) is tuple and len(self.appeal_fees) <= 16, "appeal bound")
        require(all(uint(x) > 0 for x in self.appeal_fees), "positive appeal fee")

    @property
    def gap(self) -> int:
        return self.award - self.prepayment

    def amount(self, rung: int) -> int:
        require(type(rung) is int and 0 <= rung < len(self.ladder), "invalid rung")
        return self.gap * self.ladder[rung] // BPS


@dataclass
class Ticket:
    owner: str
    key: Key
    policy: Policy
    created_block: int
    expiry: int
    secured: int
    unsecured: int
    state: TicketState = TicketState.RESERVED


@dataclass
class Request:
    key: Key
    requester: str
    policy: Policy
    submitted_at: int
    submitted_block: int
    ticket: int | None = None
    case: int | None = None
    resolved: bool = False
    ruling: int | None = None
    registered: bool = False


@dataclass(frozen=True)
class FinalOffers:
    domain: str
    request: Key
    case: int
    policy: Policy
    evidence: str
    requester: str
    claimant: str
    admission: int
    claim: int
    admission_amount: int
    claim_amount: int
    initial_fee: int
    cost_cap: int
    opened_at: int


@dataclass
class Case:
    request: Key
    claimant: str
    claim: int
    deadline: int
    evidence: str
    state: CaseState = CaseState.OPEN
    admission: int = 0
    paid_award: int = 0
    severity_end: int = 0
    merits_dispute: int | None = None
    severity_dispute: int | None = None
    final_rung: int | None = None
    snapshot: FinalOffers | None = None
    debt: int = 0


@dataclass
class Round:
    provisional: int | None = None
    start: int = 0
    end: int = 0
    contributions: dict[tuple[str, int], int] = field(default_factory=dict)
    paid: dict[int, int] = field(default_factory=lambda: {REQUESTER: 0, CLAIMANT: 0})
    targets: dict[int, int] = field(default_factory=dict)
    next_fee: int = 0
    appealed: bool = False
    rewards: int = 0
    claimed: set[str] = field(default_factory=set)


@dataclass
class Dispute:
    case: int
    kind: str
    policy: Policy
    initial_fee: int
    rounds: list[Round] = field(default_factory=lambda: [Round()])
    final: int | None = None


@dataclass
class Mandate:
    owner: str
    root: bytes
    rung: int
    max_cases: int
    max_spend: int
    expiry: int
    created_block: int
    used: int = 0
    spent: int = 0
    closed: bool = False


def leaf_hash(domain: str, case: int, key: Key, owner: str, policy: str) -> bytes:
    """Reference SHA-256 commitment, NOT Ethereum ABI/EIP-712 encoding."""
    payload = json.dumps([domain, case, list(key), owner, policy], separators=(",", ":"))
    return hashlib.sha256(b"\x00" + payload.encode()).digest()


def pair_hash(a: bytes, b: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + min(a, b) + max(a, b)).digest()


def merkle(leaves: list[bytes]) -> tuple[bytes, list[list[bytes]]]:
    """Off-chain fixture builder. Odd levels duplicate their last node."""
    require(bool(leaves) and all(type(x) is bytes and len(x) == 32 for x in leaves), "leaves")
    paths: list[list[bytes]] = [[] for _ in leaves]
    indices = list(range(len(leaves)))
    level = list(leaves)
    while len(level) > 1:
        padded = level + [level[-1]] if len(level) % 2 else level
        for i, at in enumerate(indices):
            paths[i].append(padded[at ^ 1])
            indices[i] //= 2
        level = [pair_hash(padded[i], padded[i + 1]) for i in range(0, len(padded), 2)]
    return level[0], paths


def verifies(root: bytes, leaf: bytes, proof: list[bytes]) -> bool:
    if len(proof) > 32 or any(type(x) is not bytes or len(x) != 32 for x in proof):
        return False
    for sibling in proof:
        leaf = pair_hash(leaf, sibling)
    return leaf == root


class World:
    """Atomic protocol model plus explicitly controlled host/court fixtures.

    Public dictionaries are inspection surfaces for tests, not authenticated
    contract storage APIs. Only transitions model authorized calls. check() and
    transaction snapshots deliberately scan/copy state; they prove no gas bound.
    """

    def __init__(self, *, domain: str = "intendment-rfc001-v5", governor: str = "governor"):
        self.domain, self.governor = address(domain), address(governor)
        self.now, self.block = 1_000, 1
        self.money: dict[Account, int] = {}
        self.supply = 0
        self.policies: dict[str, Policy] = {}
        self.host_policies: dict[str, str] = {}
        self.counts: dict[tuple[str, str], int] = {}
        self.requests: dict[Key, Request] = {}
        self.tickets: dict[int, Ticket] = {}
        self.ticket_for: dict[tuple[str, Key], int] = {}
        self.credit_limits: dict[str, int] = {}
        self.unsecured: dict[str, int] = {}
        self.outstanding_debt: dict[str, int] = {}
        self.cases: dict[int, Case] = {}
        self.disputes: dict[int, Dispute] = {}
        self.mandates: dict[int, Mandate] = {}
        self.nonces: set[tuple[str, str, int]] = set()
        self.quote_overrides: dict[tuple[str, str], int] = {}
        self.unavailable: set[str] = set()
        self.failed_hosts: set[str] = set()
        self.rejecting_receivers: set[str] = set()
        self.events: list[tuple] = []
        self.retired = False

    def balance(self, *account) -> int:
        return self.money.get(tuple(account), 0)

    def _move(self, source: Account, target: Account, amount: int) -> None:
        uint(amount)
        require(self.balance(*source) >= amount, "insufficient balance")
        if source == target:
            return
        self.money[source] = self.balance(*source) - amount
        self.money[target] = uint(self.balance(*target) + amount)

    def _credit(self, source: Account, who: str, amount: int) -> None:
        self._move(source, ("credit", address(who)), amount)

    def _nonce(self, caller: str, kind: str, nonce: int) -> None:
        key = (address(caller), kind, uint(nonce))
        require(key not in self.nonces, "nonce reused")
        self.nonces.add(key)

    def _policy(self, host: str) -> Policy:
        require(host in self.host_policies, "unknown host")
        return self.policies[self.host_policies[host]]

    def _request(self, key: Key) -> Request:
        require(key in self.requests, "unknown request")
        return self.requests[key]

    def _case(self, cid: int) -> tuple[Case, Request]:
        require(type(cid) is int and cid in self.cases, "unknown case")
        c = self.cases[cid]
        return c, self._request(c.request)

    @transaction
    def mint(self, who: str, amount: int) -> None:
        """Fixture-only initial endowment; not a protocol mint function."""
        uint(amount)
        address(who)
        self.money[("wallet", who)] = uint(self.balance("wallet", who) + amount)
        self.supply = uint(self.supply + amount)

    @transaction
    def mine(self, seconds: int = 1, blocks: int = 1) -> None:
        require(uint(blocks) > 0, "must advance block")
        self.now = uint(self.now + uint(seconds))
        self.block = uint(self.block + blocks)

    @transaction
    def configure(self, caller: str, host: str, policy: Policy) -> None:
        require(caller == self.governor and not self.retired, "governor, active only")
        require(isinstance(policy, Policy), "policy")
        if policy.version in self.policies:
            require(self.policies[policy.version] == policy, "immutable version")
        self.policies[policy.version] = policy
        self.host_policies[address(host)] = policy.version

    @transaction
    def set_credit_limit(self, caller: str, who: str, limit: int) -> None:
        """Explicit experimental eligibility input; no reputation inference."""
        require(caller == self.governor and not self.retired, "governor, active only")
        self.credit_limits[address(who)] = uint(limit)

    @transaction
    def set_resolver(self, caller: str, resolver: str, *, kind: str, fee: int, available: bool = True) -> None:
        """Fixture: simulates an independently operated resolver's quote/outage."""
        require(caller == resolver, "resolver only")
        require(kind in ("merits", "severity"), "kind")
        require(uint(fee) > 0, "positive fee")
        self.quote_overrides[(resolver, kind)] = fee
        if available:
            self.unavailable.discard(resolver)
        else:
            self.unavailable.add(resolver)

    @transaction
    def deposit_bond(self, caller: str, amount: int) -> None:
        self._move(("wallet", caller), ("free", caller), amount)

    @transaction
    def withdraw_bond(self, caller: str, amount: int) -> None:
        self._credit(("free", caller), caller, amount)

    @transaction
    def claim_credit(self, caller: str, recipient: str) -> int:
        require(recipient not in self.rejecting_receivers, "receiver rejected")
        amount = self.balance("credit", caller)
        self._move(("credit", caller), ("wallet", address(recipient)), amount)
        return amount

    @transaction
    def reserve(self, caller: str, host: str, item: str, *, secured: int, nonce: int, expiry: int) -> int:
        require(not self.retired, "retired")
        p = self._policy(host)
        require(uint(secured) <= p.gap and uint(expiry) > self.now, "reservation bounds")
        key = (host, address(item), self.counts.get((host, item), 0))
        require((caller, key) not in self.ticket_for, "request slot already reserved")
        missing = p.gap - secured
        require(not missing or self.outstanding_debt.get(caller, 0) == 0, "unpaid debt")
        require(self.unsecured.get(caller, 0) + missing <= self.credit_limits.get(caller, 0), "credit limit")
        self._nonce(caller, "ticket", nonce)
        tid = len(self.tickets) + 1
        self._move(("free", caller), ("award", tid), secured)
        # This is ADDITIONAL to the host prepayment and never lent as award cash.
        self._move(("free", caller), ("cost", tid), p.severity_cap)
        self.tickets[tid] = Ticket(caller, key, p, self.block, expiry, secured, missing)
        self.ticket_for[(caller, key)] = tid
        self.unsecured[caller] = self.unsecured.get(caller, 0) + missing
        self.events.append(("Reserved", tid, key, secured, missing, p.severity_cap))
        return tid

    def _matches(self, t: Ticket, r: Request) -> bool:
        return (t.key == r.key and t.owner == r.requester and t.policy == r.policy
                and t.created_block < r.submitted_block and r.submitted_at < t.expiry)

    def _bind_ticket(self, r: Request) -> int | None:
        if r.ticket is not None:
            return r.ticket
        tid = self.ticket_for.get((r.requester, r.key))
        if tid is None:
            return None
        t = self.tickets[tid]
        if t.state != TicketState.RESERVED or not self._matches(t, r):
            return None
        # Binding may happen AFTER expiry if submission was timely.
        t.state, r.ticket = TicketState.BOUND, tid
        self.events.append(("TicketBound", tid, r.key))
        return tid

    @transaction
    def bind_ticket(self, key: Key) -> int:
        tid = self._bind_ticket(self._request(key))
        require(tid is not None, "no qualifying ticket")
        return tid

    def _release_ticket(self, tid: int, state: TicketState) -> None:
        t = self.tickets[tid]
        for bucket in ("award", "cost"):
            self._move((bucket, tid), ("free", t.owner), self.balance(bucket, tid))
        self.unsecured[t.owner] = self.unsecured.get(t.owner, 0) - t.unsecured
        t.state = state
        if self.ticket_for.get((t.owner, t.key)) == tid:
            del self.ticket_for[(t.owner, t.key)]
        self.events.append(("TicketReleased", tid, state.value))

    @transaction
    def cancel_ticket(self, caller: str, tid: int) -> None:
        require(tid in self.tickets, "unknown ticket")
        t = self.tickets[tid]
        require(t.owner == caller and t.state == TicketState.RESERVED, "owner, unused only")
        r = self.requests.get(t.key)
        require(r is None or not self._matches(t, r), "timely request still backed")
        self._release_ticket(tid, TicketState.CANCELLED)

    @transaction
    def release(self, key: Key) -> None:
        r = self._request(key)
        tid = self._bind_ticket(r)
        require(tid is not None and self.tickets[tid].state == TicketState.BOUND, "no live reservation")
        require(r.resolved, "host unresolved")
        if r.case is not None:
            require(self.cases[r.case].state == CaseState.FINISHED, "financial liability unresolved")
        self._release_ticket(tid, TicketState.RELEASED)

    @transaction
    def host_submit(self, caller: str, host: str, item: str) -> Key:
        """Stock-host fixture: does NOT require a ticket or call the wrapper.

        Missing backing is a policy failure, not a blocked challenge path.
        A production adapter must verify real host state, not trust these inputs.
        """
        p = self._policy(host)
        index = self.counts.get((host, item), 0)
        if index:
            previous = self.requests[(host, item, index - 1)]
            require(previous.resolved and not previous.registered, "item unavailable")
        key = (host, address(item), index)
        self._move(("wallet", caller), ("host", key), uint(p.prepayment + p.merits_fee))
        self.requests[key] = Request(key, caller, p, self.now, self.block)
        self.counts[(host, item)] = index + 1
        self.events.append(("Submitted", key, caller))
        return key

    @transaction
    def execute_unchallenged(self, key: Key) -> None:
        r = self._request(key)
        require(not r.resolved and r.case is None, "not unchallenged")
        require(self.now > r.submitted_at + r.policy.challenge_period, "review not ended")
        r.resolved, r.registered, r.ruling = True, True, REQUESTER
        self._credit(("host", key), r.requester, self.balance("host", key))

    @transaction
    def challenge(self, caller: str, key: Key, *, claim: int | None = None, evidence: str = "evidence") -> int:
        r = self._request(key)
        require(not r.resolved and r.case is None, "not challengeable")
        require(self.now <= r.submitted_at + r.policy.challenge_period, "challenge deadline")
        if claim is None:
            claim = len(r.policy.ladder) - 1
        r.policy.amount(claim)
        cid = len(self.cases) + 1
        self._move(("wallet", caller), ("host", key), r.policy.challenger_deposit)
        self._move(("wallet", caller), ("merits-fee", cid), r.policy.merits_fee)
        self._bind_ticket(r)
        r.case = cid
        self.cases[cid] = Case(key, caller, claim, self.now + r.policy.settlement_window, address(evidence))
        self.events.append(("Challenged", cid, r.ticket is not None))
        return cid

    def _quote(self, p: Policy, kind: str) -> int:
        require(p.resolver not in self.unavailable, "resolver unavailable")
        return self.quote_overrides.get((p.resolver, kind), p.merits_fee if kind == "merits" else p.severity_cap)

    def _new_dispute(self, cid: int, kind: str, fee: int) -> int:
        p = self.requests[self.cases[cid].request].policy
        did = len(self.disputes) + 1
        self.disputes[did] = Dispute(cid, kind, p, fee)
        self.events.append(("DisputeOpened", did, cid, kind, fee))
        return did

    @transaction
    def escalate_merits(self, caller: str, cid: int) -> int:
        c, r = self._case(cid)
        require(c.state == CaseState.OPEN, "merits already routed")
        require(caller == r.requester or self.now >= c.deadline, "requester only before deadline")
        fee = self._quote(r.policy, "merits")
        # Stage-1 reserve/shortfall handling is intentionally NOT duplicated here.
        require(fee == r.policy.merits_fee, "merits fee drift: baseline adapter required")
        self._move(("merits-fee", cid), ("jurors",), fee)
        c.merits_dispute = self._new_dispute(cid, "merits", fee)
        c.state = CaseState.MERITS
        return c.merits_dispute

    def _host_rule(self, r: Request, c: Case, ruling: int) -> None:
        require(not r.resolved and r.key[0] not in self.failed_hosts, "host callback failed")
        r.resolved, r.ruling, r.registered = True, ruling, ruling == REQUESTER
        pot = self.balance("host", r.key)
        if ruling == REFUSE:
            self._credit(("host", r.key), r.requester, pot // 2)
            self._credit(("host", r.key), c.claimant, pot // 2)
            # Preserve the host's unallocatable odd unit explicitly.
            self._move(("host", r.key), ("host-dust", r.key), self.balance("host", r.key))
        else:
            self._credit(("host", r.key), r.requester if ruling == REQUESTER else c.claimant, pot)
        self.events.append(("HostFinal", r.key, ruling))

    def _cash_admission(self, cid: int, rung: int, source: Account | None = None) -> None:
        c, r = self._case(cid)
        amount = r.policy.amount(rung)
        due = amount - c.paid_award
        require(due >= 0, "admission cannot shrink")
        if source is not None:
            self._credit(source, c.claimant, due)
        else:
            secured = min(due, self.balance("award", r.ticket)) if r.ticket is not None else 0
            if secured:
                self._credit(("award", r.ticket), c.claimant, secured)
            self._credit(("wallet", r.requester), c.claimant, due - secured)
        c.admission, c.paid_award = rung, amount

    def _concede(self, cid: int, rung: int, source: Account | None = None) -> None:
        c, r = self._case(cid)
        require(c.state == CaseState.OPEN, "not open")
        r.policy.amount(rung)
        require(rung <= c.claim, "admission above claim")
        self._cash_admission(cid, rung, source)
        self._credit(("merits-fee", cid), r.requester, self.balance("merits-fee", cid))
        self._host_rule(r, c, CLAIMANT)
        c.state, c.severity_end = CaseState.NEGOTIATING, self.now + r.policy.severity_window
        if c.admission == c.claim:
            self._finish_financial(cid, c.admission)

    @transaction
    def concede(self, caller: str, cid: int, rung: int) -> None:
        _, r = self._case(cid)
        require(caller == r.requester, "requester only")
        self._concede(cid, rung)

    @transaction
    def raise_admission(self, caller: str, cid: int, rung: int) -> None:
        c, r = self._case(cid)
        require(caller == r.requester and c.state == CaseState.NEGOTIATING, "requester, negotiating only")
        require(self.now < c.severity_end, "negotiation ended")
        require(c.admission < rung <= c.claim, "admission monotone")
        self._cash_admission(cid, rung)
        if c.admission == c.claim:
            self._finish_financial(cid, rung)

    @transaction
    def lower_claim(self, caller: str, cid: int, rung: int) -> None:
        c, r = self._case(cid)
        require(caller == c.claimant and c.state in (CaseState.OPEN, CaseState.NEGOTIATING), "claimant, unfrozen only")
        require(c.state != CaseState.NEGOTIATING or self.now < c.severity_end, "negotiation ended")
        r.policy.amount(rung)
        require(c.admission <= rung < c.claim, "claim monotone")
        c.claim = rung
        if c.state == CaseState.NEGOTIATING and c.claim == c.admission:
            self._finish_financial(cid, rung)

    @transaction
    def top_up_cost(self, caller: str, cid: int, amount: int) -> None:
        c, r = self._case(cid)
        require(caller == r.requester and c.state == CaseState.NEGOTIATING, "requester before opening")
        require(r.ticket is not None and self.now < c.severity_end, "ticket/window required")
        self._move(("wallet", caller), ("cost", r.ticket), amount)

    @transaction
    def open_severity(self, caller: str, cid: int, *, max_fee: int) -> int:
        c, r = self._case(cid)
        require(caller == c.claimant and c.state == CaseState.NEGOTIATING, "claimant, negotiating only")
        require(self.now < c.severity_end and c.claim > c.admission, "no live disagreement")
        require(r.policy.amount(c.claim) > r.policy.amount(c.admission), "no monetary disagreement")
        fee = self._quote(r.policy, "severity")
        require(fee <= uint(max_fee), "fee slippage")
        require(r.ticket is not None and self.balance("cost", r.ticket) >= fee, "cost bond shortfall")
        self._move(("wallet", caller), ("jurors",), fee)
        c.snapshot = FinalOffers(self.domain, r.key, cid, r.policy, c.evidence,
                                 r.requester, c.claimant, c.admission, c.claim,
                                 r.policy.amount(c.admission), r.policy.amount(c.claim),
                                 fee, self.balance("cost", r.ticket), self.now)
        c.severity_dispute = self._new_dispute(cid, "severity", fee)
        c.state = CaseState.SEVERITY
        return c.severity_dispute

    @transaction
    def close_severity_window(self, cid: int) -> None:
        c, _ = self._case(cid)
        require(c.state == CaseState.NEGOTIATING and self.now >= c.severity_end, "window open/not negotiating")
        self._finish_financial(cid, c.admission)

    def _finish_financial(self, cid: int, rung: int, outcome: int | None = None) -> None:
        c, r = self._case(cid)
        require(r.resolved and r.ruling == CLAIMANT and c.state != CaseState.FINISHED, "no final rejection")
        due = r.policy.amount(rung) - c.paid_award
        require(due >= 0, "award below paid admission")
        secured = min(due, self.balance("award", r.ticket)) if r.ticket is not None else 0
        if secured:
            self._credit(("award", r.ticket), c.claimant, secured)
        c.paid_award += secured
        c.debt = due - secured
        self.outstanding_debt[r.requester] = self.outstanding_debt.get(r.requester, 0) + c.debt
        # Initial fee allocation follows FINAL outcome, never a provisional vote.
        if c.snapshot is not None and outcome == CLAIMANT:
            self._credit(("cost", r.ticket), c.claimant, c.snapshot.initial_fee)
        c.final_rung, c.state = rung, CaseState.FINISHED
        self.events.append(("FinancialFinal", cid, rung, c.paid_award, c.debt))

    @transaction
    def repay(self, caller: str, cid: int, amount: int) -> None:
        c, r = self._case(cid)
        require(c.state == CaseState.FINISHED and 0 < uint(amount) <= c.debt, "repayment bounds")
        self._credit(("wallet", caller), c.claimant, amount)
        c.debt -= amount
        c.paid_award += amount
        self.outstanding_debt[r.requester] -= amount

    @transaction
    def publish_ruling(self, caller: str, did: int, ruling: int) -> None:
        require(did in self.disputes, "unknown dispute")
        d = self.disputes[did]
        require(caller == d.policy.resolver and d.final is None, "live resolver only")
        require(type(ruling) is int and ruling in (REFUSE, REQUESTER, CLAIMANT), "binary plus refusal")
        rd = d.rounds[-1]
        require(rd.provisional is None, "ruling already published")
        rd.provisional, rd.start, rd.end = ruling, self.now, self.now + d.policy.appeal_window
        i = len(d.rounds) - 1
        if i < len(d.policy.appeal_fees):
            rd.next_fee = d.policy.appeal_fees[i]
            for side in (REQUESTER, CLAIMANT):
                multiplier = (d.policy.shared_multiplier if ruling == REFUSE else
                              d.policy.winner_multiplier if side == ruling else d.policy.loser_multiplier)
                rd.targets[side] = uint(rd.next_fee + rd.next_fee * multiplier // BPS)

    @transaction
    def fund_appeal(self, caller: str, did: int, side: int, amount: int) -> int:
        require(did in self.disputes and type(side) is int and side in (REQUESTER, CLAIMANT), "dispute/side")
        d, amount = self.disputes[did], uint(amount)
        rd = d.rounds[-1]
        require(d.final is None and rd.provisional is not None and rd.next_fee > 0, "not appealable")
        require(rd.start <= self.now < rd.end, "appeal ended")
        if rd.provisional not in (REFUSE, side):
            require(2 * self.now < rd.start + rd.end, "loser half-window ended")
        remaining = rd.targets[side] - rd.paid[side]
        require(remaining > 0 and amount > 0, "side funded/zero")
        accepted = min(amount, remaining)
        self._move(("wallet", caller), ("appeal", did, len(d.rounds) - 1), accepted)
        rd.paid[side] += accepted
        key = (caller, side)
        rd.contributions[key] = rd.contributions.get(key, 0) + accepted
        if all(rd.paid[s] == rd.targets[s] for s in (REQUESTER, CLAIMANT)):
            require(d.policy.resolver not in self.unavailable, "resolver unavailable")
            self._move(("appeal", did, len(d.rounds) - 1), ("jurors",), rd.next_fee)
            rd.rewards = rd.paid[REQUESTER] + rd.paid[CLAIMANT] - rd.next_fee
            rd.appealed = True
            d.rounds.append(Round())
        return accepted

    @transaction
    def finalize(self, did: int) -> int:
        require(did in self.disputes, "unknown dispute")
        d = self.disputes[did]
        rd = d.rounds[-1]
        require(d.final is None and rd.provisional is not None and self.now >= rd.end, "not final")
        full = [s for s in (REQUESTER, CLAIMANT) if s in rd.targets and rd.paid[s] == rd.targets[s]]
        require(len(full) <= 1, "both funded must appeal")
        d.final = full[0] if full else rd.provisional
        c, r = self._case(d.case)
        if d.kind == "merits":
            require(c.state == CaseState.MERITS, "wrong phase")
            self._host_rule(r, c, d.final)
            if d.final == CLAIMANT:
                c.state, c.severity_end = CaseState.NEGOTIATING, self.now + r.policy.severity_window
                if c.claim == c.admission:
                    self._finish_financial(d.case, c.admission)
            else:
                c.state = CaseState.FINISHED
        else:
            require(c.state == CaseState.SEVERITY and c.snapshot is not None, "wrong phase")
            rung = c.snapshot.claim if d.final == CLAIMANT else c.snapshot.admission
            self._finish_financial(d.case, rung, d.final)
        self.events.append(("DisputeFinal", did, d.final))
        return d.final

    @transaction
    def claim_appeal(self, caller: str, did: int, round_index: int) -> int:
        require(did in self.disputes, "unknown dispute")
        d = self.disputes[did]
        require(d.final is not None and type(round_index) is int and 0 <= round_index < len(d.rounds), "not final/round")
        rd = d.rounds[round_index]
        require(caller not in rd.claimed, "already claimed")
        a, b = rd.contributions.get((caller, REQUESTER), 0), rd.contributions.get((caller, CLAIMANT), 0)
        if not rd.appealed:
            value = a + b
        elif d.final == REFUSE:
            value = (a + b) * rd.rewards // (rd.paid[REQUESTER] + rd.paid[CLAIMANT])
        else:
            contribution = a if d.final == REQUESTER else b
            value = contribution * rd.rewards // rd.paid[d.final]
        rd.claimed.add(caller)
        self._credit(("appeal", did, round_index), caller, value)
        return value  # Any rounding remainder remains an explicit liability.

    def mandate_leaf(self, cid: int) -> bytes:
        _, r = self._case(cid)
        return leaf_hash(self.domain, cid, r.key, r.requester, r.policy.version)

    @transaction
    def authorize(self, caller: str, root: bytes, *, rung: int, max_cases: int,
                  max_spend: int, expiry: int, nonce: int) -> int:
        require(not self.retired, "retired")
        require(type(root) is bytes and len(root) == 32, "root")
        require(uint(rung) < 64 and uint(max_cases) > 0 and uint(expiry) > self.now, "mandate bounds")
        uint(max_spend)
        self._nonce(caller, "mandate", nonce)
        mid = len(self.mandates) + 1
        self._move(("wallet", caller), ("mandate", mid), max_spend)
        self.mandates[mid] = Mandate(caller, root, rung, max_cases, max_spend, expiry, self.block)
        self.events.append(("Authorized", mid, caller, root.hex(), max_spend))
        return mid

    @transaction
    def execute_mandate(self, mid: int, cid: int, proof: list[bytes]) -> bool:
        require(mid in self.mandates, "unknown mandate")
        m = self.mandates[mid]
        c, r = self._case(cid)
        require(not m.closed and self.now < m.expiry, "mandate closed/expired")
        require(r.requester == m.owner and verifies(m.root, self.mandate_leaf(cid), proof), "mandate scope")
        if c.state in (CaseState.NEGOTIATING, CaseState.SEVERITY, CaseState.FINISHED):
            return False  # Independently conceded/resolved: no spend or count.
        require(c.state == CaseState.OPEN, "escalation won")
        r.policy.amount(m.rung)  # A malformed rung must not silently mean the maximum.
        rung = min(m.rung, c.claim)
        amount = r.policy.amount(rung)
        require(m.used < m.max_cases and m.spent + amount <= m.max_spend, "mandate exhausted")
        # Effects and host callback are one modeled transaction; any failure rolls all back.
        self._concede(cid, rung, ("mandate", mid))
        m.used += 1
        m.spent += amount
        self.events.append(("MandateExecuted", mid, cid, amount))
        return True

    @transaction
    def refund_mandate(self, mid: int) -> int:
        require(mid in self.mandates, "unknown mandate")
        m = self.mandates[mid]
        require(not m.closed, "already refunded")
        require(self.now >= m.expiry or m.used == m.max_cases or m.spent == m.max_spend, "mandate live")
        m.closed = True
        value = self.balance("mandate", mid)
        self._credit(("mandate", mid), m.owner, value)
        return value

    @transaction
    def retire(self, caller: str) -> None:
        require(caller == self.governor and not self.retired, "governor, active only")
        self.retired = True  # No seizure/migration of another party's credits or debt.

    def check(self) -> None:
        """Global audit invariants. A verifier, NOT on-chain loop semantics."""
        assert all(type(v) is int and 0 <= v <= MAX_UINT for v in self.money.values())
        assert sum(self.money.values()) == self.supply, "cash conservation"
        expected_unsecured: dict[str, int] = {}
        expected_debt: dict[str, int] = {}
        for tid, t in self.tickets.items():
            if t.state in (TicketState.RESERVED, TicketState.BOUND):
                expected_unsecured[t.owner] = expected_unsecured.get(t.owner, 0) + t.unsecured
                assert self.balance("award", tid) <= t.secured
            else:
                assert self.balance("award", tid) == self.balance("cost", tid) == 0
            if t.state == TicketState.BOUND:
                assert self.requests[t.key].ticket == tid
        for owner in set(self.unsecured) | set(expected_unsecured):
            assert self.unsecured.get(owner, 0) == expected_unsecured.get(owner, 0), "credit exposure"
        for cid, c in self.cases.items():
            r = self.requests[c.request]
            assert c.debt >= 0 and c.paid_award >= 0
            assert 0 <= c.admission <= c.claim < len(r.policy.ladder)
            expected_debt[r.requester] = expected_debt.get(r.requester, 0) + c.debt
            assert self.balance("merits-fee", cid) == (r.policy.merits_fee if c.state == CaseState.OPEN else 0)
            expected_pot = 0 if r.resolved else r.policy.prepayment + r.policy.merits_fee + r.policy.challenger_deposit
            assert self.balance("host", r.key) == expected_pot, "host pot isolated"
            assert c.debt <= r.policy.gap
            if c.state in (CaseState.NEGOTIATING, CaseState.SEVERITY):
                assert r.resolved and r.ruling == CLAIMANT and not r.registered
            if c.snapshot is not None:
                s = c.snapshot
                assert (s.admission, s.claim, s.policy, s.evidence) == (c.admission, c.claim, r.policy, c.evidence)
                assert s.admission_amount == r.policy.amount(c.admission)
                assert s.claim_amount == r.policy.amount(c.claim)
                assert 0 < s.initial_fee <= s.cost_cap
                assert c.severity_dispute is not None
            if c.final_rung is not None:
                assert c.state == CaseState.FINISHED and r.ruling == CLAIMANT and not r.registered
                assert c.paid_award + c.debt == r.policy.amount(c.final_rung), "award plus debt"
        for owner in set(expected_debt) | set(self.outstanding_debt):
            assert self.outstanding_debt.get(owner, 0) == expected_debt.get(owner, 0), "debt is not cash"
        for mid, m in self.mandates.items():
            assert 0 <= m.used <= m.max_cases and 0 <= m.spent <= m.max_spend
            assert self.balance("mandate", mid) == (0 if m.closed else m.max_spend - m.spent)
        for did, d in self.disputes.items():
            assert len(d.rounds) <= 1 + len(d.policy.appeal_fees)
            for i, rd in enumerate(d.rounds):
                for side in (REQUESTER, CLAIMANT):
                    assert rd.paid[side] == sum(v for (_, s), v in rd.contributions.items() if s == side)
                    assert rd.paid[side] <= rd.targets.get(side, 0)
                if rd.appealed:
                    assert i < len(d.rounds) - 1 and rd.rewards == sum(rd.paid.values()) - rd.next_fee

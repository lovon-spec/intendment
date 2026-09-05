# SPDX-License-Identifier: MIT
"""An executable model of the IntendmentArbitrator, spec 0.5, stage 1a with stage 1b offers behind a flag.

Integer wei accounting, a Light-GTCR-like host, a controllable resolver K, and an
invariant check after every transition. It is a model of the specification, not
of any contract: gas, reentrancy and ABI details are out of scope, except that
"properly gassed" is a boolean the caller controls, as the spec's MIN_FORWARD_GAS
floor makes it in the contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class State(Enum):
    UNBOUND = "Unbound"
    OPEN = "Open"
    FORWARDABLE = "Forwardable"
    FORWARDED = "Forwarded"
    CONCEDED = "Conceded"
    LAPSED = "Lapsed"


OPEN_STATES = {State.UNBOUND, State.OPEN, State.FORWARDABLE}
ENDED_STATES = {State.FORWARDED, State.CONCEDED, State.LAPSED}


class Kind(Enum):
    REGISTRATION = "Registration"
    REMOVAL = "Removal"


REFUSE, REQUESTER_WINS, CHALLENGER_WINS = 0, 1, 2


class Rejected(Exception):
    """A transition's precondition failed; nothing changed."""


class Clock:
    def __init__(self, now: int = 1_000_000) -> None:
        self.now = now

    def advance(self, seconds: int) -> None:
        self.now += seconds


class Resolver:
    """K: a fixed cost, switchable availability, switchable quote availability."""

    def __init__(self, cost: int) -> None:
        self.cost = cost
        self.accepting = True
        self.quotable = True
        self.disputes: dict[int, int] = {}
        self._next = 1

    def arbitration_cost(self) -> int:
        if not self.quotable:
            raise RuntimeError("K: quote reverted")
        return self.cost

    def create_dispute(self, value: int) -> int:
        if not self.accepting:
            raise RuntimeError("K: createDispute reverted")
        if value != self.cost:
            raise RuntimeError("K: wrong value")
        k_id = self._next
        self._next += 1
        self.disputes[k_id] = value
        return k_id


@dataclass
class Request:
    kind: Kind
    requester: str
    challenger: str
    pot: int
    ruling: int | None = None


class Host:
    """A Light-GTCR-like arbitrable: the party of record is whoever called it; payouts by `send`."""

    def __init__(self, wallets: "Wallets") -> None:
        self.wallets = wallets
        self.requests: dict[int, Request] = {}
        self.dispute_to_request: dict[int, int] = {}
        self.stuck = 0
        self.challenge_period = 3 * 86400
        self.arbitrator: "Wrapper | None" = None
        self._next = 1

    def submit(self, kind: Kind, requester: str, deposit: int) -> int:
        rid = self._next
        self._next += 1
        self.requests[rid] = Request(kind, requester, "", deposit)
        return rid

    def challenge(self, rid: int, caller: str, fee: int, deposit: int) -> int:
        """`caller` is the party of record, exactly as `msg.sender` is on the host."""
        req = self.requests[rid]
        req.challenger = caller
        req.pot += deposit
        assert self.arbitrator is not None
        dispute_id = self.arbitrator.create_dispute(host=self, value=fee)
        self.dispute_to_request[dispute_id] = rid
        return dispute_id

    def rule(self, dispute_id: int, ruling: int) -> None:
        req = self.requests[self.dispute_to_request[dispute_id]]
        req.ruling = ruling
        pot, req.pot = req.pot, 0
        if ruling == REFUSE:
            self._send(req.requester, pot // 2)
            self._send(req.challenger, pot // 2)
        elif ruling == REQUESTER_WINS:
            self._send(req.requester, pot)
        else:
            self._send(req.challenger, pot)

    def _send(self, to: str, amount: int) -> None:
        if not self.wallets.receive(to, amount):
            self.stuck += amount  # the host swallows a failed send, as Light does


class Wallets:
    def __init__(self) -> None:
        self.balances: dict[str, int] = {}
        self.rejecting: set[str] = set()

    def receive(self, who: str, amount: int) -> bool:
        if who in self.rejecting:
            return False
        self.balances[who] = self.balances.get(who, 0) + amount
        return True


@dataclass
class Epoch:
    quote: int
    premium: int
    max_cost: int


@dataclass
class Case:
    epoch: Epoch
    fee: int
    created_at: int
    deadline: int
    funding_end: int
    earmark: int
    dispute_id: int
    state: State = State.UNBOUND
    kind: Kind | None = None
    requester: str = ""
    challenger: str = ""
    ask: int = 0
    ask_set: bool = False
    bid: int = 0
    bid_valid_until: int = 0
    total_funding: int = 0
    contributions: dict[str, int] = field(default_factory=dict)
    funding_used: int = 0
    refundable: int = 0
    claimed_funding: int = 0
    funders_claimed: set[str] = field(default_factory=set)
    first_forward_failure: int = 0
    k_dispute_id: int | None = None
    ruling: int | None = None

    @property
    def insured(self) -> bool:
        return self.earmark == self.epoch.max_cost - self.epoch.quote

    def live_bid(self, now: int) -> bool:
        return self.bid_valid_until > now


class Wrapper:
    """The IntendmentArbitrator. Every public method is one transition of the specification."""

    TRANSITIONS = {
        "T1": "create_dispute", "T2": "bind", "T3": "forward", "T4": "set_ask", "T5": "concede",
        "T6": "bid", "T7": "accept_bid", "T8": "escalate", "T9": "escalate", "T10": "fund",
        "T11": "lapse", "T12": "rule", "T13": "appeal", "T14": "claim", "T15": "claim_funding",
        "T16": "forward_or_lapse",
        "G1": "register_epoch", "G2": "fund_reserve", "G3": "deactivate", "G4": "announce_withdrawal",
        "G5": "cancel_withdrawal", "G6": "execute_withdrawal", "G7": "migrate_surplus",
    }

    def __init__(self, host: Host, k: Resolver, clock: Clock, wallets: Wallets, governor: str, *,
                 window: int = 2 * 86400, funding_period: int = 86400, min_validity: int = 3600,
                 resolver_grace: int = 86400, reserve_timelock: int = 7 * 86400,
                 retirement_lock: int | None = None, max_margin_bps: int = 2500, max_premium_bps: int = 1000,
                 offers: bool = False, factory: str = "factory") -> None:
        self.host, self.k, self.clock, self.wallets, self.governor = host, k, clock, wallets, governor
        self.W, self.G, self.V = window, funding_period, min_validity
        self.RESOLVER_GRACE, self.RESERVE_TIMELOCK = resolver_grace, reserve_timelock
        self.RETIREMENT_LOCK = retirement_lock if retirement_lock is not None else host.challenge_period + 86400
        self.MAX_MARGIN_BPS, self.MAX_PREMIUM_BPS = max_margin_bps, max_premium_bps
        self.offers, self.factory = offers, factory
        self.epochs: dict[int, Epoch] = {}
        self.cases: dict[int, Case] = {}
        self.claimable: dict[str, int] = {}
        self.principal = 0
        self.surplus = 0
        self.balance = 0
        self.retired = False
        self.retired_at = 0
        self.pending: tuple[int, str, int] | None = None
        self.events: list[tuple] = []
        self.forward_iterations = 0  # how many per-funder steps forwarding took: must stay 0 (I13)
        self._next_case = 1
        host.arbitrator = self

    # ---- accounting views -------------------------------------------------------------------
    @property
    def reserve(self) -> int:
        return self.principal + self.surplus

    @property
    def earmarked(self) -> int:
        return sum(c.earmark for c in self.cases.values() if c.state in OPEN_STATES)

    @property
    def free(self) -> int:
        return self.reserve - self.earmarked

    def funding_liability(self, c: Case) -> int:
        return c.total_funding if c.state in OPEN_STATES else c.refundable - c.claimed_funding

    @property
    def refund_liability(self) -> int:
        return sum(self.funding_liability(c) for c in self.cases.values())

    def quotable(self) -> bool:
        try:
            self.k.arbitration_cost()
            return True
        except RuntimeError:
            return False

    def covered(self, c: Case) -> bool:
        if not self.quotable():
            return False
        return self.k.arbitration_cost() <= c.fee + c.earmark + self.free + (c.total_funding - c.funding_used)

    def grace_elapsed(self, c: Case) -> bool:
        return c.first_forward_failure != 0 and self.clock.now >= c.first_forward_failure + self.RESOLVER_GRACE

    def mode(self, c: "Case | int") -> str:
        if isinstance(c, int):
            c = self.cases[c]
        return "insured" if c.insured else "under-insured"

    # ---- the invariant check, run after every transition ------------------------------------
    def check(self) -> None:
        open_fees = sum(c.fee for c in self.cases.values() if c.state in OPEN_STATES)
        claimable = sum(self.claimable.values())
        expected = open_fees + self.refund_liability + claimable + self.reserve
        assert self.balance == expected, f"I1 conservation: balance {self.balance} != {expected}"
        assert self.free >= 0, "I1: earmarks exceed the reserve"
        assert self.principal >= 0 and self.surplus >= 0, "I19: accounts never negative"
        assert self.forward_iterations == 0, "I13: forwarding iterated over funders"

    # ---- epochs and reserve (G1..G7) --------------------------------------------------------
    def register_epoch(self, caller: str, margin_bps: int, premium_bps: int, max_cost: int) -> int:
        self._require(caller == self.governor, "governor only")
        self._require(not self.retired, "retired")
        self._require(margin_bps <= self.MAX_MARGIN_BPS and premium_bps <= self.MAX_PREMIUM_BPS, "caps")
        quote = self.k.arbitration_cost() * (10000 + margin_bps) // 10000
        self._require(max_cost >= quote, "maxCost >= quote")
        eid = len(self.epochs) + 1
        self.epochs[eid] = Epoch(quote, quote * premium_bps // 10000, max_cost)
        self.events.append(("EpochRegistered", eid, quote))
        self.check()
        return eid

    def fund_reserve(self, caller: str, amount: int) -> None:
        if caller == self.governor:
            self.principal += amount
        else:
            self.surplus += amount
        self.balance += amount
        self.events.append(("ReserveFunded", caller, amount))
        self.check()

    def deactivate(self, caller: str) -> None:
        self._require(caller == self.governor and not self.retired, "governor only, once")
        self.retired, self.retired_at = True, self.clock.now
        self.events.append(("Deactivated", self.clock.now))
        self.check()

    def announce_withdrawal(self, caller: str, amount: int, to: str) -> None:
        self._require(caller == self.governor and self.retired, "governor only, after retirement")
        self._require(amount <= self.principal, "amount <= principal")
        self.pending = (amount, to, self.clock.now)
        self.events.append(("WithdrawalAnnounced", amount, to))
        self.check()

    def cancel_withdrawal(self, caller: str) -> None:
        self._require(caller == self.governor and self.pending is not None, "nothing pending")
        self.pending = None
        self.check()

    def execute_withdrawal(self, caller: str) -> int:
        self._require(caller == self.governor and self.pending is not None, "nothing pending")
        amount, to, announced_at = self.pending
        self._require(self.clock.now >= announced_at + self.RESERVE_TIMELOCK, "timelock")
        self._require(self.clock.now >= self.retired_at + self.RETIREMENT_LOCK, "retirement lock")
        self._require(not any(c.state in OPEN_STATES for c in self.cases.values()), "cases open")
        self._require(amount <= self.principal and amount <= self.free, "amount vs principal and free at execution")
        self.pending = None
        self.principal -= amount
        self.balance -= amount
        self.wallets.receive(to, amount)
        self.events.append(("PrincipalWithdrawn", to, amount))
        self.check()
        return amount

    def migrate_surplus(self, caller: str, successor: "Wrapper") -> int:
        self._require(caller == self.governor and self.retired, "governor only, after retirement")
        self._require(self.clock.now >= self.retired_at + self.RETIREMENT_LOCK, "retirement lock")
        self._require(not any(c.state in OPEN_STATES for c in self.cases.values()), "cases open")
        self._require(successor.factory == self.factory and successor.host is self.host, "successor of the same factory for the same host")
        amount, self.surplus = self.surplus, 0
        self.balance -= amount
        successor.surplus += amount
        successor.balance += amount
        self.events.append(("SurplusMigrated", amount))
        self.check()
        successor.check()
        return amount

    # ---- case transitions (T1..T16) ---------------------------------------------------------
    def create_dispute(self, host: Host, value: int, epoch_id: int = 1) -> int:
        """T1. Never conditioned on the reserve."""
        self._require(host is self.host, "wrong sender")
        self._require(epoch_id in self.epochs, "unregistered epoch")
        epoch = self.epochs[epoch_id]
        self._require(value == epoch.quote, "wrong value")
        cid = self._next_case
        self._next_case += 1
        earmark = min(epoch.max_cost - epoch.quote, self.free)
        now = self.clock.now
        self.cases[cid] = Case(epoch, value, now, now + self.W, now + self.W + self.G, earmark, cid)
        self.balance += value
        self.events.append(("CaseOpened", cid, earmark))
        if earmark < epoch.max_cost - epoch.quote:
            self.events.append(("UnderInsured", cid, epoch.max_cost - epoch.quote - earmark))
        self.check()
        return cid

    def bind(self, cid: int) -> Case:
        """T2. Reads the party of record from the host; anyone may call."""
        c = self.cases[cid]
        if c.state is not State.UNBOUND:
            return c
        req = self.host.requests[self.host.dispute_to_request[cid]]
        c.kind, c.requester, c.challenger = req.kind, req.requester, req.challenger
        c.state = State.OPEN if c.kind is Kind.REGISTRATION else State.FORWARDABLE
        self.events.append(("CaseBound", cid, c.kind.value, c.requester, c.challenger))
        self.check()
        return c

    def _try_forward(self, c: Case, gas_ok: bool) -> bool:
        """The shared forwarding attempt of T3, T8, T9 and T16. Returns True on success; on a
        qualifying failure records it and returns False; a starved call is not qualifying."""
        self._require(gas_ok, "not enough gas for a qualifying attempt")
        try:
            cost = self.k.arbitration_cost()
            self._require(self.covered(c), "not covered")
            k_id = self.k.create_dispute(cost)
        except RuntimeError:
            if c.first_forward_failure == 0:
                c.first_forward_failure = self.clock.now
            self.events.append(("ForwardFailed", c.dispute_id))
            return False
        # money: fee, then the reserve draw (surplus first, principal second), then funding
        remaining = cost
        from_fee = min(remaining, c.fee)
        remaining -= from_fee
        if c.fee > cost:
            self.surplus += c.fee - cost
        draw = min(remaining, c.earmark + self.free)
        from_surplus = min(draw, self.surplus)
        self.surplus -= from_surplus
        self.principal -= draw - from_surplus
        remaining -= draw
        c.funding_used = remaining
        assert c.funding_used <= c.total_funding
        c.refundable = c.total_funding - c.funding_used
        c.earmark = 0
        c.state = State.FORWARDED
        c.k_dispute_id = k_id
        self.balance -= cost
        self.events.append(("Escalated", c.dispute_id, k_id, cost, c.funding_used))
        return True

    def forward(self, cid: int, gas_ok: bool = True) -> bool:
        """T3."""
        c = self.bind(cid)
        self._require(c.state is State.FORWARDABLE, "not forwardable")
        ok = self._try_forward(c, gas_ok)
        self.check()
        return ok

    def set_ask(self, cid: int, caller: str, share: int) -> None:
        """T4 (stage 1b)."""
        c = self.bind(cid)
        self._require(self.offers, "offers disabled")
        self._require(c.state is State.OPEN and caller == c.challenger, "challenger, open case")
        self._require(self.clock.now < c.deadline, "deadline passed")
        cap = c.epoch.quote - c.epoch.premium
        if c.ask_set:
            self._require(share < c.ask, "asks only fall")
        else:
            self._require(0 <= share <= cap, "0 <= share <= q - pi")
        if c.live_bid(self.clock.now) and c.bid >= share:
            self._settle(c, c.bid)
            return
        c.ask, c.ask_set = share, True
        self.events.append(("AskSet", cid, share))
        self.check()

    def concede(self, cid: int, caller: str, max_share: int | None = None) -> None:
        """T5."""
        c = self.bind(cid)
        self._require(c.state is State.OPEN and caller == c.requester, "requester, open case")
        if max_share is not None:
            self._require(c.ask <= max_share, "ask above limit")
        self._settle(c, c.ask)

    def bid(self, cid: int, caller: str, share: int, valid_until: int) -> None:
        """T6 (stage 1b)."""
        c = self.bind(cid)
        self._require(self.offers, "offers disabled")
        self._require(c.state is State.OPEN and caller == c.requester, "requester, open case")
        now = self.clock.now
        self._require(now < c.deadline, "deadline passed")
        self._require(share > c.bid and share <= c.epoch.quote - c.epoch.premium, "bids only rise, up to q - pi")
        self._require(valid_until >= now + self.V and valid_until <= c.deadline, "validity")
        if c.live_bid(now):
            self._require(valid_until >= c.bid_valid_until, "a replacement never shortens a live bid")
        if share >= c.ask:
            self._settle(c, c.ask)
            return
        c.bid, c.bid_valid_until = share, valid_until
        self.events.append(("BidPosted", cid, share, valid_until))
        self.check()

    def accept_bid(self, cid: int, caller: str, min_share: int = 0) -> None:
        """T7 (stage 1b)."""
        c = self.bind(cid)
        self._require(self.offers, "offers disabled")
        self._require(c.state is State.OPEN and caller == c.challenger, "challenger, open case")
        self._require(c.live_bid(self.clock.now) and c.bid >= min_share, "no live bid at that price")
        self._settle(c, c.bid)

    def _settle(self, c: Case, share: int) -> None:
        q, pi = c.epoch.quote, c.epoch.premium
        assert 0 <= share <= q - pi
        self.claimable[c.requester] = self.claimable.get(c.requester, 0) + (q - pi - share)
        self.claimable[c.challenger] = self.claimable.get(c.challenger, 0) + share
        self.surplus += pi
        c.earmark = 0
        c.refundable = c.total_funding
        c.state = State.CONCEDED
        c.ruling = CHALLENGER_WINS
        self.events.append(("Settled", c.dispute_id, share, pi))
        self.host.rule(c.dispute_id, CHALLENGER_WINS)
        self.check()

    def escalate(self, cid: int, caller: str, gas_ok: bool = True) -> bool:
        """T8 before the deadline for the requester without a live bid; T9 from the deadline for anyone."""
        c = self.bind(cid)
        self._require(c.state is State.OPEN, "not open")
        now = self.clock.now
        if now < c.deadline:
            self._require(caller == c.requester, "before the deadline only the requester")
            self._require(not c.live_bid(now), "a live bid blocks the requester")
        ok = self._try_forward(c, gas_ok)
        self.check()
        return ok

    def fund(self, cid: int, funder: str, amount: int) -> None:
        """T10."""
        c = self.bind(cid)
        self._require(c.state in (State.OPEN, State.FORWARDABLE), "case not open")
        self._require(self.clock.now < c.funding_end, "funding period over")
        c.total_funding += amount
        c.contributions[funder] = c.contributions.get(funder, 0) + amount
        self.balance += amount
        self.events.append(("Funded", cid, funder, amount))
        self.check()

    def _lapse(self, c: Case) -> None:
        self.claimable[c.challenger] = self.claimable.get(c.challenger, 0) + c.fee
        c.refundable = c.total_funding
        c.earmark = 0
        c.state = State.LAPSED
        c.ruling = REFUSE
        self.events.append(("Lapsed", c.dispute_id))
        self.host.rule(c.dispute_id, REFUSE)

    def lapse(self, cid: int) -> None:
        """T11: only an uncovered, quotable case after the funding period."""
        c = self.bind(cid)
        self._require(c.state in (State.OPEN, State.FORWARDABLE), "case not open")
        self._require(self.clock.now >= c.funding_end, "funding period not over")
        self._require(self.quotable(), "unquotable: use forwardOrLapse after the grace")
        self._require(not self.covered(c), "covered: escalation is the only path")
        self._lapse(c)
        self.check()

    def forward_or_lapse(self, cid: int, gas_ok: bool = True) -> State:
        """T16: forward first; lapse only on a fresh qualifying failure in the same transaction."""
        c = self.bind(cid)
        self._require(c.state in (State.OPEN, State.FORWARDABLE), "case not open")
        self._require(self.clock.now >= c.funding_end, "funding period not over")
        self._require(self.covered(c) or not self.quotable(), "uncovered: use lapse")
        self._require(self.grace_elapsed(c), "grace not elapsed")
        if self._try_forward(c, gas_ok):
            self.check()
            return State.FORWARDED
        self._lapse(c)
        self.check()
        return State.LAPSED

    def rule(self, k_dispute_id: int, ruling: int, caller: str = "K") -> None:
        """T12: K's ruling relayed to the host."""
        self._require(caller == "K", "K only")
        c = next(x for x in self.cases.values() if x.k_dispute_id == k_dispute_id)
        self._require(c.state is State.FORWARDED and c.ruling is None, "once")
        c.ruling = ruling
        self.events.append(("RulingRelayed", c.dispute_id, k_dispute_id, ruling))
        self.host.rule(c.dispute_id, ruling)
        self.check()

    def appeal(self, cid: int, caller: object) -> None:
        """T13: host only."""
        self._require(caller is self.host, "host only")
        c = self.cases[cid]
        self._require(c.state is State.FORWARDED, "not forwarded")
        self.events.append(("Appealed", cid))

    def claim(self, who: str, to: str | None = None) -> int:
        """T14: the only value transfer to a party."""
        amount = self.claimable.get(who, 0)
        self._require(amount > 0, "nothing to claim")
        if not self.wallets.receive(to or who, amount):
            self.check()
            return 0  # the receiver rejected; the credit stays
        self.claimable[who] = 0
        self.balance -= amount
        self.events.append(("Claimed", who, amount))
        self.check()
        return amount

    def claim_funding(self, cid: int, funder: str) -> int:
        """T15: lazy, per funder, floor arithmetic, once."""
        c = self.cases[cid]
        self._require(c.state in ENDED_STATES, "case not ended")
        contribution = c.contributions.get(funder, 0)
        self._require(contribution > 0 and funder not in c.funders_claimed, "nothing to claim, or claimed")
        amount = contribution * c.refundable // c.total_funding
        c.funders_claimed.add(funder)
        c.claimed_funding += amount
        self.claimable[funder] = self.claimable.get(funder, 0) + amount
        self.events.append(("FundingClaimed", cid, funder, amount))
        self.check()
        return amount

    # ---- helpers -----------------------------------------------------------------------------
    @staticmethod
    def _require(condition: bool, message: str) -> None:
        if not condition:
            raise Rejected(message)

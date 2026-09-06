# SPDX-License-Identifier: MIT
"""An executable model of RFC 001 revision 2 (experiment 3) on top of the stage-1a model.

Money unit: 1 = 0.1 xDAI, the unit of ``tests/test_stage1a.py`` (D = 300, q1 = 5, u = 60).

What is modelled, and where:

* a cheap first instance (RFC 3): ``Court`` is a resolver with a programmed route, one
  (court, jurors, cost) per round, an appeal period, and multi-option rulings; the wrapper
  relays appeals unchanged (T13) and every round's cost is burned to jurors;
* the host's appeal rule (RFC 3.4): ``CreditedHost.fund_appeal`` needs the previous loser's
  side to raise cost x 3 and the winner's x 2 (x 2 each after a refusal), anyone may fund
  either side, an appeal is created only when both sides are funded, and a lone funded side
  wins by the host's own override in ``rule``; rewards follow Light GTCR's waterfall;
* credited deposits (RFC 5): the host's cash deposit is the prepayment u plus the first
  instance fee; the wrapper knows only the promise D - u (never u or D, S16) and keeps the
  ledger: escrow on a concession, bonds, debts, and a per-submitter standing
  ``accrued - unpaid defaults`` that falls when a debt is recorded and recovers on payment;
* severity tiers (RFC 4.2): K rules among REFUSE, NO_VIOLATION, FORMAL, SUBSTANTIVE,
  MALICIOUS; every rejecting tier maps to the host's CHALLENGER_WINS, refusal to REFUSE;
  a tier scales only wrapper-held money: the held fee's share, the promise, a bond;
* tiered concession with cost shifting (RFC 4.3): the requester concedes at a tier by paying
  that tier's price in cash into escrow in the same transition; the challenger accepts or
  escalates; if the court's tier is at or below the conceded tier the challenger bears the
  court cost (its fee, which the host's pot reimburses unconditionally, is netted off the
  wrapper's award), otherwise the requester pays the higher tier and the pot's fee;
* batch concession (RFC 4.4): one transition over the caller's own open cases only;
* silence escalates (S1): the first instance is prepaid, so an absent requester reaches
  court through the inherited T9;
* the bonding rule (RFC 5.2) as an evidence display computed from wrapper events at the
  submission time, and an immutable per-host ``Policy`` that an arbitrator switch cannot change.

The stage-1a model is untouched: ``CreditedWrapper`` subclasses ``Wrapper`` and inherits
T1, T2, T3, T9, T10, T11, T14, T15, T16 and G1..G7 verbatim; ``check`` is extended, never
weakened, and also asserts system-wide conservation: every wallet, the host's cash, every
wrapper's balance and the fees burned to jurors sum to the money minted.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import (CHALLENGER_WINS, OPEN_STATES, REFUSE, REQUESTER_WINS, Case, Clock, Host, Kind,
                    Rejected, Request, Resolver, State, Wallets, Wrapper)

# K's ruling options, named in the wrapper's meta-evidence (RFC 4.2).
NO_VIOLATION, FORMAL, SUBSTANTIVE, MALICIOUS = 1, 2, 3, 4
REJECTING = (FORMAL, SUBSTANTIVE, MALICIOUS)
TIER_NAMES = ("formal", "substantive", "malicious")
DEFAULT_TIER_BPS = (1000, 5000, 10000)  # illustrative: 10, 50, 100 percent of the promise (RFC 4.5)
DAY = 86400


def to_host(option: int) -> int:
    """The wrapper-to-host mapping: any rejecting tier is a challenger win, refusal is refusal."""
    if option == REFUSE:
        return REFUSE
    if option == NO_VIOLATION:
        return REQUESTER_WINS
    if option in REJECTING:
        return CHALLENGER_WINS
    raise Rejected(f"unknown ruling option {option}")


def tier_of(option: int) -> int | None:
    return option - FORMAL if option in REJECTING else None


# ---- money ---------------------------------------------------------------------------------
class CreditedWallets(Wallets):
    """Wallets that are debited, plus the system-wide conservation check.

    Every unit of money enters through ``mint``; ``conserved`` holds when wallets, every
    registered holder (host cash, wrapper balances, the court's burned fees) sum to it.
    """

    def __init__(self) -> None:
        super().__init__()
        self.minted = 0
        self.holders: list = []

    def mint(self, who: str, amount: int) -> None:
        self.minted += amount
        self.balances[who] = self.balances.get(who, 0) + amount

    def pay(self, who: str, amount: int) -> None:
        if amount < 0 or self.balances.get(who, 0) < amount:
            raise Rejected(f"{who} lacks {amount} in cash")
        self.balances[who] -= amount

    def held_by_holders(self) -> int:
        return sum(h.held() for h in self.holders)

    def total(self) -> int:
        return sum(self.balances.values()) + self.held_by_holders()

    def conserved(self) -> bool:
        return self.total() == self.minted


# ---- the resolver with a route -------------------------------------------------------------
@dataclass(frozen=True)
class Round:
    court: str
    jurors: int
    cost: int


# RFC 3.3: a child of court 19 at 0.5 xDAI, jump threshold 1, then 19, 19, 19, General.
SCOUT_ROUTE = (Round("child", 1, 5), Round("19", 3, 216), Round("19", 7, 504), Round("19", 15, 1080),
               Round("0", 31, 3720))


@dataclass
class Dispute:
    round: int = 0
    option: int | None = None
    appeal_until: int = 0
    period: str = "evidence"  # evidence -> appeal -> executed
    history: list = field(default_factory=list)  # (round, court, cost, option)
    arbitrable: object = None  # the wrapper that created it, as Kleros's dispute.arbitrated


class Court(Resolver):
    """K with a programmed route (RFC 3.2): the arbitrable chooses nothing but the entry court."""

    def __init__(self, clock: Clock, route: tuple[Round, ...] = SCOUT_ROUTE, appeal_period: int = 2 * DAY) -> None:
        super().__init__(route[0].cost)
        self.clock, self.route, self.appeal_period = clock, route, appeal_period
        self.burned = 0  # fees paid to jurors: the only leak in the system
        self.arbitrable: CreditedWrapper | None = None
        self.disputes: dict[int, Dispute] = {}

    def held(self) -> int:
        return self.burned

    def create_dispute(self, value: int) -> int:
        if not self.accepting:
            raise RuntimeError("K: createDispute reverted")
        if value != self.cost:
            raise RuntimeError("K: wrong value")
        k_id = self._next
        self._next += 1
        self.disputes[k_id] = Dispute(arbitrable=self.arbitrable)
        self.burned += value
        return k_id

    def round_of(self, k_id: int) -> Round:
        return self.route[self.disputes[k_id].round]

    def appeal_cost(self, k_id: int) -> int | None:
        """None once the route is exhausted: General at the threshold cannot be appealed."""
        nxt = self.disputes[k_id].round + 1
        return self.route[nxt].cost if nxt < len(self.route) else None

    def appeal_open(self, k_id: int) -> bool:
        d = self.disputes[k_id]
        return d.period == "appeal" and self.clock.now < d.appeal_until

    def current_option(self, k_id: int) -> int | None:
        return self.disputes[k_id].option

    def rule(self, k_id: int, option: int) -> None:
        """The round's jurors decide; the appeal period opens."""
        d = self.disputes[k_id]
        if d.period != "evidence":
            raise Rejected("K: round already ruled")
        to_host(option)  # a valid option
        d.option, d.period, d.appeal_until = option, "appeal", self.clock.now + self.appeal_period
        d.history.append((d.round, self.route[d.round].court, self.route[d.round].cost, option))

    def appeal(self, k_id: int, value: int) -> None:
        d = self.disputes[k_id]
        cost = self.appeal_cost(k_id)
        if not self.appeal_open(k_id):
            raise Rejected("K: not in the appeal period")
        if cost is None:
            raise Rejected("K: cannot be appealed further")
        if value != cost:
            raise Rejected("K: wrong appeal value")
        self.burned += value
        d.round += 1
        d.option, d.period = None, "evidence"

    def execute(self, k_id: int) -> None:
        """After an appeal period that saw no appeal, the ruling reaches the arbitrable (T12)."""
        d = self.disputes[k_id]
        if d.period != "appeal" or self.clock.now < d.appeal_until:
            raise Rejected("K: appeal period not over")
        d.period = "executed"
        assert d.arbitrable is not None and d.option is not None
        d.arbitrable.rule(k_id, d.option)  # the instance that created it, retired or not


# ---- the host ------------------------------------------------------------------------------
@dataclass(frozen=True)
class Policy:
    """The listing policy, immutable per registry (RFC 5.2): a switch of arbitrator cannot change it."""
    bonding_rule: bool
    promise: int
    tier_bps: tuple[int, ...] = DEFAULT_TIER_BPS
    standing_threshold: int = 3


@dataclass
class CreditedRequest(Request):
    submitted_at: int = 0
    executed: bool = False


@dataclass
class AppealRound:
    cost: int
    required: dict[int, int]
    paid: dict[int, int] = field(default_factory=lambda: {REQUESTER_WINS: 0, CHALLENGER_WINS: 0})
    has_paid: dict[int, bool] = field(default_factory=lambda: {REQUESTER_WINS: False, CHALLENGER_WINS: False})
    contributions: dict[tuple[str, int], int] = field(default_factory=dict)
    fee_rewards: int = 0
    appealed: bool = False
    withdrawn: set[tuple[str, int]] = field(default_factory=set)


class CreditedHost(Host):
    """A Light-GTCR-like host with a prepayment as its cash deposit, a challenger base deposit, and
    Light's appeal crowdfunding: multipliers, one-side-funds-wins, and the rewards waterfall."""

    def __init__(self, wallets: CreditedWallets, clock: Clock, policy: Policy, *, prepayment: int, fee: int,
                 challenger_deposit: int = 0, loser_bps: int = 20000, winner_bps: int = 10000,
                 shared_bps: int = 10000) -> None:
        super().__init__(wallets)
        self.wallets: CreditedWallets = wallets
        self.clock, self._policy = clock, policy
        self.u, self.fee, self.dc = prepayment, fee, challenger_deposit
        self.loser_bps, self.winner_bps, self.shared_bps = loser_bps, winner_bps, shared_bps
        self.cash = 0  # everything physically in the host: pots, round contributions, stuck sends, dust
        self.rounds: dict[int, dict[int, AppealRound]] = {}
        self.governor = "gov"
        wallets.holders.append(self)

    def held(self) -> int:
        return self.cash

    @property
    def policy(self) -> Policy:
        """Read-only: the policy is fixed at deployment (Policy is frozen too)."""
        return self._policy

    def switch_arbitrator(self, caller: str, arbitrator: "CreditedWrapper") -> None:
        """The host governor re-points the arbitrator; the policy is untouched by construction."""
        if caller != self.governor:
            raise Rejected("governor only")
        self.arbitrator = arbitrator

    def submit(self, kind: Kind, requester: str, deposit: int | None = None) -> int:
        deposit = self.u + self.fee if deposit is None else deposit
        self.wallets.pay(requester, deposit)
        self.cash += deposit
        rid = self._next
        self._next += 1
        self.requests[rid] = CreditedRequest(kind, requester, "", deposit, submitted_at=self.clock.now)
        return rid

    def open_requests(self, requester: str, at: int | None = None) -> int:
        """Pending requests of one submitter at a time: host data the bonding rule multiplies by."""
        at = self.clock.now if at is None else at
        return sum(1 for r in self.requests.values() if r.requester == requester and r.submitted_at <= at
                   and not r.executed and r.ruling is None)

    def execute_request(self, rid: int) -> None:
        """An unchallenged request executes after the challenge period: the deposit returns."""
        req = self.requests[rid]
        if req.challenger or req.executed or self.clock.now < req.submitted_at + self.challenge_period:
            raise Rejected("challenged, executed, or still in the challenge period")
        req.executed = True
        pot, req.pot = req.pot, 0
        self._send(req.requester, pot)

    def challenge(self, rid: int, caller: str, fee: int | None = None, deposit: int | None = None) -> int:
        fee = self.fee if fee is None else fee
        deposit = self.dc if deposit is None else deposit
        req = self.requests[rid]
        if req.challenger or req.executed:
            raise Rejected("already challenged or executed")
        self.wallets.pay(caller, fee + deposit)
        self.cash += deposit  # the fee goes to the arbitrator
        dispute_id = super().challenge(rid, caller, fee, deposit)
        self.rounds[rid] = {}
        return dispute_id

    # ---- appeals: Light GTCR's fundAppeal, applied to whatever the arbitrator quotes ------------
    def fund_appeal(self, rid: int, side: int, funder: str, amount: int) -> int:
        req = self.requests[rid]
        dispute_id = next(d for d, r in self.dispute_to_request.items() if r == rid)
        arb = self.arbitrator
        assert isinstance(arb, CreditedWrapper)
        if side not in (REQUESTER_WINS, CHALLENGER_WINS):
            raise Rejected("side")
        if not arb.appeal_open(dispute_id):
            raise Rejected("not in the appeal period")
        cost = arb.appeal_cost(dispute_id)
        if cost is None:
            raise Rejected("cannot be appealed further")
        k_round = arb.k_round(dispute_id)
        if k_round not in self.rounds[rid]:
            current = arb.current_ruling(dispute_id)
            mult = {s: (self.shared_bps if current == REFUSE else (self.winner_bps if s == current else self.loser_bps))
                    for s in (REQUESTER_WINS, CHALLENGER_WINS)}
            self.rounds[rid][k_round] = AppealRound(cost, {s: cost + cost * mult[s] // 10000 for s in mult})
        rnd = self.rounds[rid][k_round]
        if rnd.has_paid[side]:
            raise Rejected("side already funded")
        contribution = min(amount, rnd.required[side] - rnd.paid[side])
        self.wallets.pay(funder, contribution)
        self.cash += contribution
        rnd.paid[side] += contribution
        rnd.contributions[(funder, side)] = rnd.contributions.get((funder, side), 0) + contribution
        if rnd.paid[side] == rnd.required[side]:
            rnd.has_paid[side] = True
        if rnd.has_paid[REQUESTER_WINS] and rnd.has_paid[CHALLENGER_WINS]:
            rnd.fee_rewards = rnd.paid[REQUESTER_WINS] + rnd.paid[CHALLENGER_WINS] - cost
            rnd.appealed = True
            self.cash -= cost
            arb.appeal(dispute_id, self, cost)  # T13: the wrapper relays, the route decides the court
        arb.check()
        return contribution

    def rule(self, dispute_id: int, ruling: int) -> None:
        """A lone fully funded side wins, whatever the arbitrator said: Light's override in `rule`."""
        rid = self.dispute_to_request[dispute_id]
        rounds = self.rounds.get(rid, {})
        if rounds:
            last = rounds[max(rounds)]
            if not last.appealed:
                if last.has_paid[REQUESTER_WINS] and not last.has_paid[CHALLENGER_WINS]:
                    ruling = REQUESTER_WINS
                elif last.has_paid[CHALLENGER_WINS] and not last.has_paid[REQUESTER_WINS]:
                    ruling = CHALLENGER_WINS
        super().rule(dispute_id, ruling)

    def withdraw_rewards(self, rid: int, k_round: int, funder: str) -> int:
        """Light's withdrawFeesAndRewards for one funder and round, after the final ruling."""
        req = self.requests[rid]
        if req.ruling is None:
            raise Rejected("not ruled")
        rnd = self.rounds[rid][k_round]
        total = 0
        for side in (REQUESTER_WINS, CHALLENGER_WINS):
            key = (funder, side)
            c = rnd.contributions.get(key, 0)
            if c == 0 or key in rnd.withdrawn:
                continue
            rnd.withdrawn.add(key)
            if not rnd.appealed:
                total += c  # reimbursed: not enough was raised to appeal
            elif req.ruling == REFUSE:
                total += c * rnd.fee_rewards // (rnd.paid[REQUESTER_WINS] + rnd.paid[CHALLENGER_WINS])
            elif side == req.ruling:
                total += c * rnd.fee_rewards // rnd.paid[side]
        if total:
            self._send(funder, total)
        return total

    def _send(self, to: str, amount: int) -> None:
        if self.wallets.receive(to, amount):
            self.cash -= amount
        else:
            self.stuck += amount  # the host keeps a failed send, as Light does; still host cash


# ---- the wrapper ---------------------------------------------------------------------------
@dataclass
class CaseCredit:
    conceded_tier: int | None = None
    conceded_at: int = 0
    escrow: int = 0
    option: int | None = None
    ruled_tier: int | None = None
    award: int = 0
    shifted: bool = False


@dataclass
class Debt:
    debtor: str
    creditor: str
    amount: int
    paid: int = 0

    @property
    def remaining(self) -> int:
        return self.amount - self.paid


class CreditedWrapper(Wrapper):
    """The IntendmentArbitrator of RFC 001 revision 2: stage 1a plus tiers, the ledger, and appeals.

    New transitions: X1 concede at a tier (replaces T5), X2 accept, X3 concede all, X4 pay a debt,
    X5 post a bond, X6/X7 announce and withdraw a bond, X8 accrue standing (age and volume,
    governance-attested, never outcomes or payments: S4/S5). T8 is refined by S2 for a live
    concession; T12 maps options and settles the ledger; T13 relays the appeal value to K.
    """

    CREDITED_TRANSITIONS = {"X1": "concede", "X2": "accept", "X3": "concede_all", "X4": "pay_debt",
                            "X5": "post_bond", "X6": "announce_bond_withdrawal", "X7": "withdraw_bond",
                            "X8": "accrue_standing"}

    def __init__(self, host: CreditedHost, k: Court, clock: Clock, wallets: CreditedWallets, governor: str, *,
                 promise: int, tier_bps: tuple[int, ...] = DEFAULT_TIER_BPS, standing_threshold: int = 3,
                 flip_tier: int | None = None, bond_notice: int | None = None, **kw) -> None:
        super().__init__(host, k, clock, wallets, governor, **kw)
        self.host: CreditedHost = host
        self.k: Court = k
        self.wallets: CreditedWallets = wallets
        if len(tier_bps) != len(TIER_NAMES) or any(not 0 <= b <= 10000 for b in tier_bps):
            raise Rejected("three tiers, each a fraction of the promise")
        self.promise, self.tier_bps, self.standing_threshold = promise, tuple(tier_bps), standing_threshold
        self.flip_tier = flip_tier  # tier priced when the host's funding rule flips a ruling K never gave
        self.BOND_NOTICE = bond_notice if bond_notice is not None else host.challenge_period + DAY
        self.credit: dict[int, CaseCredit] = {}
        self.debts: dict[int, Debt] = {}
        self.bond: dict[str, int] = {}
        self.bond_pending: dict[str, tuple[int, int]] = {}  # who -> (amount, announced_at)
        self.accrued: dict[str, int] = {}
        self.unpaid: dict[str, int] = {}
        self.ledger_events: list[tuple] = []  # the evidence display's source: timestamped effective values
        k.arbitrable = self
        wallets.holders.append(self)
        if k not in wallets.holders:
            wallets.holders.append(k)

    # ---- views ---------------------------------------------------------------------------------
    def held(self) -> int:
        return self.balance

    def price(self, tier: int | None) -> int:
        return 0 if tier is None else self.promise * self.tier_bps[tier] // 10000

    def fee_share(self, fee: int, tier: int) -> int:
        return fee * self.tier_bps[tier] // 10000

    def standing(self, who: str) -> int:
        return self.accrued.get(who, 0) - self.unpaid.get(who, 0)

    def effective_bond(self, who: str) -> int:
        return self.bond.get(who, 0) - (self.bond_pending[who][0] if who in self.bond_pending else 0)

    @property
    def escrow(self) -> int:
        return sum(cc.escrow for cc in self.credit.values())

    @property
    def bonds(self) -> int:
        return sum(self.bond.values())

    def _case_of_k(self, k_id: int) -> Case:
        return next(x for x in self.cases.values() if x.k_dispute_id == k_id)

    def k_round(self, cid: int) -> int:
        return self.k.disputes[self.cases[cid].k_dispute_id].round

    def appeal_cost(self, cid: int) -> int | None:
        return self.k.appeal_cost(self.cases[cid].k_dispute_id)

    def appeal_open(self, cid: int) -> bool:
        c = self.cases[cid]
        return c.k_dispute_id is not None and self.k.appeal_open(c.k_dispute_id)

    def current_ruling(self, cid: int) -> int:
        option = self.k.current_option(self.cases[cid].k_dispute_id)
        return REFUSE if option is None else to_host(option)

    def bonding_status(self, submitter: str, open_requests: int, at: int) -> dict:
        """RFC 5.2's display line, replayed from the wrapper's own events at the submission time."""
        bond = standing = 0
        for ev in self.ledger_events:
            if ev[2] > at or ev[1] != submitter:
                continue
            if ev[0] == "BondEffective":
                bond = ev[3]
            elif ev[0] == "StandingEffective":
                standing = ev[3]
        bonded = bond >= self.promise * open_requests
        has_standing = standing >= self.standing_threshold
        return {"bond": bond, "standing": standing, "bonded": bonded, "has_standing": has_standing,
                "ok": bonded or has_standing}

    # ---- the invariant check ------------------------------------------------------------------
    def check(self) -> None:
        open_fees = sum(c.fee for c in self.cases.values() if c.state in OPEN_STATES)
        claimable = sum(self.claimable.values())
        expected = open_fees + self.refund_liability + claimable + self.reserve + self.escrow + self.bonds
        assert self.balance == expected, f"I1 conservation: balance {self.balance} != {expected}"
        assert self.free >= 0, "I1: earmarks exceed the reserve"
        assert self.principal >= 0 and self.surplus >= 0, "I19: accounts never negative"
        assert self.forward_iterations == 0, "I13: forwarding iterated over funders"
        assert all(v >= 0 for v in self.bond.values()) and all(v >= 0 for v in self.unpaid.values())
        assert all(0 <= d.paid <= d.amount for d in self.debts.values())
        assert all(cc.escrow == 0 for cid, cc in self.credit.items()
                   if self.cases[cid].state in (State.CONCEDED, State.LAPSED) or self.cases[cid].ruling is not None), \
            "escrow is released when a case ends"
        assert sum(1 for d in self.debts.values() if d.remaining > 0) == sum(self.unpaid.values()), "standing follows debts"
        assert self.wallets.conserved(), f"system conservation: {self.wallets.total()} != {self.wallets.minted}"

    # ---- ledger events -------------------------------------------------------------------------
    def _note_bond(self, who: str) -> None:
        self.ledger_events.append(("BondEffective", who, self.clock.now, self.effective_bond(who)))

    def _note_standing(self, who: str) -> None:
        self.ledger_events.append(("StandingEffective", who, self.clock.now, self.standing(who)))

    # ---- case transitions ----------------------------------------------------------------------
    def create_dispute(self, host: Host, value: int, epoch_id: int = 1) -> int:
        cid = super().create_dispute(host, value, epoch_id)
        self.credit[cid] = CaseCredit()
        return cid

    def _try_forward(self, c: Case, gas_ok: bool) -> bool:
        """The inherited attempt, with this instance as K's `msg.sender`: the dispute is ours to rule."""
        self.k.arbitrable = self
        return super()._try_forward(c, gas_ok)

    def concede(self, cid: int, caller: str, tier: int | None = None, max_share: int | None = None) -> None:  # type: ignore[override]
        """X1: concede at a tier, cash to escrow in the same transition. A concession only rises.
        Before the deadline it is an offer that binds its owner's escalation (S2); the challenger
        accepts (X2) or rejects it by escalating (T8); after the deadline it is an executable quote."""
        c = self.bind(cid)
        self._require(c.state is State.OPEN and caller == c.requester, "requester, open case")
        self._require(tier is not None and 0 <= tier < len(self.tier_bps), "a tier")
        cc = self.credit[cid]
        self._require(cc.conceded_tier is None or tier > cc.conceded_tier, "a concession only rises")
        price = self.price(tier)
        top_up = price - cc.escrow
        self.wallets.pay(caller, top_up)  # cash to concede: a defaulter's only exit is court
        self.balance += top_up
        cc.escrow, cc.conceded_tier, cc.conceded_at = price, tier, self.clock.now
        self.events.append(("Conceded", cid, tier, price))
        self.check()

    def accept(self, cid: int, caller: str) -> None:
        """X2: the challenger takes the concession; the case ends as a challenger win at the host."""
        c = self.bind(cid)
        cc = self.credit[cid]
        self._require(c.state is State.OPEN and caller == c.challenger, "challenger, open case")
        self._require(cc.conceded_tier is not None, "no concession to accept")
        self._settle_tier(c, cc, cc.conceded_tier)

    def concede_all(self, caller: str, tier: int, cids: list[int] | None = None) -> list[int]:
        """X3: one transition over the caller's own open cases; no other party's case is touched (S15)."""
        own = [cid for cid, c in self.cases.items() if c.state is State.OPEN and c.requester == caller] \
            if cids is None else list(cids)
        for cid in own:
            c = self.bind(cid)
            self._require(c.requester == caller and c.state is State.OPEN, "only the caller's own open cases")
        todo = [cid for cid in own if self.credit[cid].conceded_tier is None or self.credit[cid].conceded_tier < tier]
        need = sum(self.price(tier) - self.credit[cid].escrow for cid in todo)
        self._require(self.wallets.balances.get(caller, 0) >= need, "cash for every case or none")
        for cid in todo:
            self.concede(cid, caller, tier)
        self.events.append(("ConcededAll", caller, tier, tuple(todo)))
        self.check()
        return todo

    def escalate(self, cid: int, caller: str, gas_ok: bool = True) -> bool:
        """T8/T9 under S2: a live concession binds the requester and may be rejected by the challenger."""
        c = self.bind(cid)
        self._require(c.state is State.OPEN, "not open")
        cc = self.credit[cid]
        if self.clock.now < c.deadline:
            if cc.conceded_tier is None:
                self._require(caller == c.requester, "before the deadline only the requester")
            else:
                self._require(caller == c.challenger, "a live concession binds its owner; the challenger may reject it")
        ok = self._try_forward(c, gas_ok)
        self.check()
        return ok

    def _settle_tier(self, c: Case, cc: CaseCredit, tier: int) -> None:
        share = self.fee_share(c.fee, tier)  # the tier scales the held fee, the promise, a bond: nothing of the host's
        self.claimable[c.requester] = self.claimable.get(c.requester, 0) + (c.fee - share)
        self.claimable[c.challenger] = self.claimable.get(c.challenger, 0) + share + cc.escrow
        cc.award, cc.escrow, cc.ruled_tier = cc.escrow, 0, tier
        c.earmark = 0
        c.refundable = c.total_funding
        c.state = State.CONCEDED
        c.ruling = CHALLENGER_WINS
        self.events.append(("SettledAtTier", c.dispute_id, tier, share, cc.award))
        self.host.rule(c.dispute_id, CHALLENGER_WINS)
        self.check()

    def _lapse(self, c: Case) -> None:
        """T11/T16's refusal: the escrow of a conceding requester returns to it (refusal maps to refusal)."""
        cc = self.credit[c.dispute_id]
        self.claimable[c.requester] = self.claimable.get(c.requester, 0) + cc.escrow
        cc.escrow = 0
        super()._lapse(c)

    def rule(self, k_dispute_id: int, ruling: int, caller: str = "K") -> None:
        """T12: K's option is mapped to the host's binary ruling; the ledger follows the host's outcome."""
        self._require(caller == "K", "K only")
        c = self._case_of_k(k_dispute_id)
        self._require(c.state is State.FORWARDED and c.ruling is None, "once")
        cc = self.credit[c.dispute_id]
        binary = to_host(ruling)
        c.ruling, cc.option = binary, ruling
        self.events.append(("RulingRelayed", c.dispute_id, k_dispute_id, ruling, binary))
        self.host.rule(c.dispute_id, binary)
        outcome = self.host.requests[self.host.dispute_to_request[c.dispute_id]].ruling
        if outcome == CHALLENGER_WINS:
            tier = tier_of(ruling) if ruling in REJECTING else self.flip_tier
            award = self.price(tier)
            if cc.conceded_tier is not None and tier is not None and tier <= cc.conceded_tier:
                cc.shifted = True  # the pot reimbursed the challenger's fee; the wrapper nets it off
                award = max(award - c.fee, 0)
            cc.ruled_tier = tier
            self._award(c, cc, award)
        else:
            self.claimable[c.requester] = self.claimable.get(c.requester, 0) + cc.escrow  # refusal or no violation
            cc.escrow = 0
        self.check()

    def _award(self, c: Case, cc: CaseCredit, award: int) -> None:
        """Escrow first, then the bond, then a recorded promise; the standing falls with the promise."""
        a, b = c.requester, c.challenger
        from_escrow = min(cc.escrow, award)
        self.claimable[b] = self.claimable.get(b, 0) + from_escrow
        self.claimable[a] = self.claimable.get(a, 0) + cc.escrow - from_escrow
        cc.escrow = 0
        rest = award - from_escrow
        from_bond = min(self.bond.get(a, 0), rest)
        if from_bond:
            self.bond[a] -= from_bond
            self.claimable[b] = self.claimable.get(b, 0) + from_bond
            self._note_bond(a)
            rest -= from_bond
        if rest > 0:
            self.debts[c.dispute_id] = Debt(a, b, rest)
            self.unpaid[a] = self.unpaid.get(a, 0) + 1
            self._note_standing(a)
            self.events.append(("DebtRecorded", c.dispute_id, a, b, rest))
        cc.award = award

    def appeal(self, cid: int, caller: object, value: int = 0) -> None:  # type: ignore[override]
        """T13: host only; the value passes through to K unchanged, the route picks the court."""
        self._require(caller is self.host, "host only")
        c = self.cases[cid]
        self._require(c.state is State.FORWARDED and c.k_dispute_id is not None, "not forwarded")
        self.k.appeal(c.k_dispute_id, value)
        self.events.append(("Appealed", cid, self.k.round_of(c.k_dispute_id).court, value))

    # ---- the ledger ---------------------------------------------------------------------------
    def pay_debt(self, cid: int, payer: str, amount: int | None = None) -> int:
        """X4: anyone may pay a debt; standing recovers only when it is paid in full. Survives retirement."""
        d = self.debts[cid]
        amount = d.remaining if amount is None else amount
        self._require(0 < amount <= d.remaining, "amount within the debt")
        self.wallets.pay(payer, amount)
        self.balance += amount
        self.claimable[d.creditor] = self.claimable.get(d.creditor, 0) + amount
        d.paid += amount
        if d.remaining == 0:
            self.unpaid[d.debtor] -= 1
            self._note_standing(d.debtor)
        self.events.append(("DebtPaid", cid, payer, amount))
        self.check()
        return amount

    def post_bond(self, who: str, amount: int) -> None:
        """X5: a voluntary bond backing all of one submitter's requests, paying challengers first."""
        self._require(not self.retired and amount > 0, "live instance, positive amount")
        self.wallets.pay(who, amount)
        self.balance += amount
        self.bond[who] = self.bond.get(who, 0) + amount
        self._note_bond(who)
        self.events.append(("BondPosted", who, amount))
        self.check()

    def announce_bond_withdrawal(self, who: str, amount: int) -> None:
        """X6: the display treats an announced amount as gone at once; the cash leaves after the notice."""
        self._require(0 < amount <= self.bond.get(who, 0), "amount within the bond")
        self.bond_pending[who] = (amount, self.clock.now)
        self._note_bond(who)
        self.check()

    def withdraw_bond(self, who: str) -> int:
        """X7: after the notice, with no open case and no unpaid debt of this submitter; a credit."""
        self._require(who in self.bond_pending, "nothing announced")
        amount, announced_at = self.bond_pending[who]
        self._require(self.clock.now >= announced_at + self.BOND_NOTICE, "notice not over")
        self._require(not any(c.requester == who and c.state in OPEN_STATES for c in self.cases.values()), "cases open")
        self._require(self.unpaid.get(who, 0) == 0, "unpaid debts")
        amount = min(amount, self.bond.get(who, 0))
        del self.bond_pending[who]
        self.bond[who] -= amount
        self.claimable[who] = self.claimable.get(who, 0) + amount
        self._note_bond(who)
        self.events.append(("BondWithdrawn", who, amount))
        self.check()
        return amount

    def accrue_standing(self, caller: str, who: str, amount: int) -> None:
        """X8: age and volume, attested by governance; never outcomes or payments (S4, S5)."""
        self._require(caller == self.governor and amount > 0, "governor only, positive")
        self.accrued[who] = self.accrued.get(who, 0) + amount
        self._note_standing(who)
        self.check()


def evidence_display(host: CreditedHost, wrapper: CreditedWrapper, submitter: str, at: int) -> dict:
    """What jurors see for the bonding rule: the policy says whether the rule exists; the wrapper's
    events say whether the submitter was bonded or had standing at the submission time; the host
    says how many requests were open then. The verdict is the formal tier or nothing."""
    status = wrapper.bonding_status(submitter, host.open_requests(submitter, at), at)
    in_policy = host.policy.bonding_rule
    return {**status, "rule_in_policy": in_policy, "violation": FORMAL if in_policy and not status["ok"] else None}


# ---- payoffs (design v0.9 section 2, re-derived with the award split) ------------------------
def payoff_table(D: float, q1: float, u: float, dc: float = 0.0, tier_fractions=(0.1, 0.5, 1.0)) -> dict:
    """Court losses and gains per party and tier, the concession band, and the challenger's minimum
    confidence, in xDAI, with the award split into the prepayment u and the promise D - u."""
    promise = D - u
    rows = {}
    for name, f in zip(TIER_NAMES, tier_fractions):
        p = promise * f
        rows[name] = {k: round(v, 6) for k, v in {
            "price": p,
            "s_A": u + q1 + p,           # A's court loss at this tier
            "g_A": dc,                   # A's court gain: the challenger's base deposit
            "s_B": q1 + dc,              # B's court loss: the prepaid fee plus its deposit
            "g_B_paying": u + p,         # B's court gain against a submitter who pays
            "g_B_defaulter": u,          # against a defaulter: the prepayment through the host
            "band_low": u + p,           # B's court win: below it B escalates
            "band_high": u + q1 + p,     # A's court loss: above it A escalates
            "band_width": q1,            # the fee court would burn, as in the vanilla q - pi
            "min_conf_paying": (q1 + dc) / (q1 + dc + u + p),
            "min_conf_defaulter": (q1 + dc) / (q1 + dc + u),
        }.items()}
    return {"u": u, "promise": round(promise, 6), "tiers": rows}


def vanilla_payoffs(D: float = 30.0, q: float = 21.6, dc: float = 0.0, pi: float = 0.0) -> dict:
    return {"s_A": D + q, "g_A": dc, "s_B": q + dc, "g_B": D, "band_width": q - pi,
            "min_conf": (q + dc) / (q + dc + D)}

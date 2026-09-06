# SPDX-License-Identifier: MIT
"""Traces of RFC 001 revision 2, section 8, against the credited model (experiment 3).

One test per row of the trace table, plus the spine and rule checks the RFC asks for. The
model asserts, after every transition, the wrapper's own conservation and the system-wide
one: wallets, host cash, wrapper balances and fees burned to jurors sum to the money minted.
Every test also asserts it at the end, so a passing trace proves it held throughout.

Units: 1 = 0.1 xDAI. Scout numbers: D = 300, q1 = 5, u = 60 (also 84 and 120).
"""
import dataclasses
import random

import pytest

from intendment.credited import (DEFAULT_TIER_BPS, FORMAL, MALICIOUS, NO_VIOLATION, SCOUT_ROUTE, SUBSTANTIVE, Court,
                                 CreditedHost, CreditedWallets, CreditedWrapper, Policy, evidence_display,
                                 payoff_table, to_host, vanilla_payoffs)
from intendment.model import CHALLENGER_WINS, REFUSE, REQUESTER_WINS, Clock, Kind, Rejected, State, Wrapper

DAY = 86400
D, Q1, U = 300, 5, 60
TIERS = {"formal": 0, "substantive": 1, "malicious": 2}


class World:
    def __init__(self, *, u=U, q1=Q1, dc=0, tier_bps=DEFAULT_TIER_BPS, threshold=3, flip_tier=None, bonding_rule=True,
                 promise=None, appeal_period=2 * DAY):
        self.clock, self.wallets = Clock(), CreditedWallets()
        self.k = Court(self.clock, appeal_period=appeal_period)
        self.u, self.q1, self.dc = u, q1, dc
        self.promise = D - u if promise is None else promise
        policy = Policy(bonding_rule, self.promise, tuple(tier_bps), threshold)
        self.host = CreditedHost(self.wallets, self.clock, policy, prepayment=u, fee=q1, challenger_deposit=dc)
        self.w = CreditedWrapper(self.host, self.k, self.clock, self.wallets, "gov", promise=self.promise,
                                 tier_bps=tier_bps, standing_threshold=threshold, flip_tier=flip_tier)
        self.w.register_epoch("gov", 0, 0, q1)
        self.minted: dict[str, int] = {}

    def mint(self, who, amount):
        self.wallets.mint(who, amount)
        self.minted[who] = self.minted.get(who, 0) + amount

    def open(self, requester="A", challenger="B", kind=Kind.REGISTRATION):
        rid = self.host.submit(kind, requester)
        cid = self.host.challenge(rid, challenger)
        self.w.bind(cid)
        return cid

    def rid(self, cid):
        return self.host.dispute_to_request[cid]

    def kid(self, cid):
        return self.w.cases[cid].k_dispute_id

    def to_court(self, cid, option, by=None):
        """Escalate (by the requester, or by anyone at the deadline), let K rule, and execute."""
        c = self.w.cases[cid]
        if by is None:
            self.clock.now = max(self.clock.now, c.deadline)
            by = "anyone"
        assert self.w.escalate(cid, by) is True
        self.k.rule(self.kid(cid), option)
        self.execute(cid)

    def execute(self, cid):
        self.clock.now = max(self.clock.now, self.k.disputes[self.kid(cid)].appeal_until)
        self.k.execute(self.kid(cid))

    def net(self, who):
        """Cash plus wrapper credits, less what was minted to the wallet."""
        return self.wallets.balances.get(who, 0) + self.w.claimable.get(who, 0) - self.minted.get(who, 0)

    def price(self, tier):
        return self.w.price(tier)

    def conserved(self):
        return self.wallets.conserved()


def test_the_credited_wrapper_keeps_every_stage_1a_transition():
    for method in Wrapper.TRANSITIONS.values():
        assert callable(getattr(CreditedWrapper, method))
    for method in CreditedWrapper.CREDITED_TRANSITIONS.values():
        assert callable(getattr(CreditedWrapper, method))


# ---- Route ---------------------------------------------------------------------------------
def test_route_reaches_court_19_on_the_first_appeal_and_general_at_the_threshold():
    wd = World()
    wd.mint("A", 100_000)
    wd.mint("B", 100_000)
    cid = wd.open()
    rid = wd.rid(cid)
    wd.w.escalate(cid, "A")
    assert wd.k.round_of(wd.kid(cid)) == SCOUT_ROUTE[0] and wd.k.burned == Q1
    for i, option in enumerate((NO_VIOLATION, MALICIOUS, NO_VIOLATION, MALICIOUS)):
        wd.k.rule(wd.kid(cid), option)
        cost = wd.w.appeal_cost(cid)
        assert cost == SCOUT_ROUTE[i + 1].cost
        before = wd.w.balance
        wd.host.fund_appeal(rid, REQUESTER_WINS, "A", 3 * cost)
        wd.host.fund_appeal(rid, CHALLENGER_WINS, "B", 3 * cost)
        assert wd.k.round_of(wd.kid(cid)) == SCOUT_ROUTE[i + 1]  # the court tree, not the wrapper, chose it
        assert wd.w.balance == before  # the relay passed the value through unchanged
        assert wd.w.events[-1] == ("Appealed", cid, SCOUT_ROUTE[i + 1].court, cost)
    assert wd.k.burned == sum(r.cost for r in SCOUT_ROUTE)
    wd.k.rule(wd.kid(cid), MALICIOUS)
    assert wd.w.appeal_cost(cid) is None  # General at the threshold: no further appeal
    with pytest.raises(Rejected):
        wd.host.fund_appeal(rid, REQUESTER_WINS, "A", 10_000)
    wd.execute(cid)
    assert [(h[1], h[2]) for h in wd.k.disputes[wd.kid(cid)].history] == [(r.court, r.cost) for r in SCOUT_ROUTE]
    assert wd.host.requests[rid].ruling == CHALLENGER_WINS
    assert wd.conserved()


# ---- Appeal funding ------------------------------------------------------------------------
def test_only_one_funded_side_wins_and_the_loser_stake_is_lost_on_a_second_loss():
    wd = World()
    for who in ("A", "B", "F1", "F2"):
        wd.mint(who, 10_000)
    # only one side funds: that side wins, and its stake comes back
    cid = wd.open()
    rid = wd.rid(cid)
    wd.w.escalate(cid, "A")
    wd.k.rule(wd.kid(cid), NO_VIOLATION)
    cost = wd.w.appeal_cost(cid)
    wd.host.fund_appeal(rid, CHALLENGER_WINS, "F1", 10_000)  # a third party funds the loser's side
    rnd = wd.host.rounds[rid][0]
    assert rnd.required == {REQUESTER_WINS: 2 * cost, CHALLENGER_WINS: 3 * cost}
    assert rnd.paid[CHALLENGER_WINS] == 3 * cost and not rnd.appealed
    wd.execute(cid)
    assert wd.host.requests[rid].ruling == CHALLENGER_WINS  # K said no violation; the host's funding rule flipped it
    assert wd.host.withdraw_rewards(rid, 0, "F1") == 3 * cost and wd.net("F1") == 0
    # both sides fund, the loser loses again: its stake is gone, the winner's funders share it
    cid2 = wd.open()
    rid2 = wd.rid(cid2)
    wd.w.escalate(cid2, "A")
    wd.k.rule(wd.kid(cid2), NO_VIOLATION)
    wd.host.fund_appeal(rid2, CHALLENGER_WINS, "F1", 3 * cost)
    wd.host.fund_appeal(rid2, REQUESTER_WINS, "F2", 2 * cost)  # a third party may fund either side
    assert wd.host.rounds[rid2][0].appealed and wd.k.round_of(wd.kid(cid2)) == SCOUT_ROUTE[1]
    wd.k.rule(wd.kid(cid2), NO_VIOLATION)
    wd.execute(cid2)
    assert wd.host.withdraw_rewards(rid2, 0, "F1") == 0
    assert wd.host.withdraw_rewards(rid2, 0, "F2") == 3 * cost + 2 * cost - cost
    assert wd.net("F1") == -3 * cost and wd.net("F2") == 2 * cost
    assert wd.conserved()


# ---- Fooled first instance -----------------------------------------------------------------
def test_a_fooled_first_instance_is_corrected_by_a_watchdog_within_the_window():
    wd = World(appeal_period=2 * DAY)
    wd.mint("A", 5_000)
    wd.mint("B", 100)
    wd.mint("watchdog", 5_000)
    wd.mint("poor-watchdog", 2 * Q1)  # two first-instance fees, no loser stake
    cid = wd.open()
    rid = wd.rid(cid)
    wd.clock.now = wd.w.cases[cid].deadline  # the junk item reaches court by S1
    wd.w.escalate(cid, "anyone")
    wd.k.rule(wd.kid(cid), NO_VIOLATION)  # the agent juror was fooled by the tree
    stake = 3 * wd.w.appeal_cost(cid)
    with pytest.raises(Rejected):
        wd.host.fund_appeal(rid, CHALLENGER_WINS, "poor-watchdog", stake)  # the wallet is not sized for it
    wd.host.fund_appeal(rid, CHALLENGER_WINS, "watchdog", stake)
    wd.host.fund_appeal(rid, REQUESTER_WINS, "A", 2 * wd.w.appeal_cost(cid))
    assert wd.k.round_of(wd.kid(cid)).court == "19"
    wd.k.rule(wd.kid(cid), MALICIOUS)  # humans correct it
    wd.execute(cid)
    assert wd.host.requests[rid].ruling == CHALLENGER_WINS
    assert wd.w.credit[cid].ruled_tier == TIERS["malicious"] and wd.w.debts[cid].amount == wd.price(2)
    assert wd.host.withdraw_rewards(rid, 0, "watchdog") == stake + 216  # the stake returns, plus the loser's
    assert wd.net("watchdog") == 216
    # the window: after it, the same appeal is refused
    cid2 = wd.open()
    wd.clock.now = wd.w.cases[cid2].deadline
    wd.w.escalate(cid2, "anyone")
    wd.k.rule(wd.kid(cid2), NO_VIOLATION)
    wd.clock.advance(2 * DAY)
    with pytest.raises(Rejected):
        wd.host.fund_appeal(wd.rid(cid2), CHALLENGER_WINS, "watchdog", stake)
    assert wd.conserved()


def test_a_funding_flip_has_no_tier_so_the_promise_needs_a_rule_the_rfc_does_not_give():
    """Conflict: when the host's rule flips a no-violation ruling because only the challenger's side
    funded, no juror named a tier. With flip_tier None the wrapper awards only the prepayment."""
    for flip_tier, expected in ((None, 0), (TIERS["malicious"], D - U)):
        wd = World(flip_tier=flip_tier)
        wd.mint("A", 1_000)
        wd.mint("B", 100)
        wd.mint("watchdog", 1_000)
        cid = wd.open()
        rid = wd.rid(cid)
        wd.w.escalate(cid, "A")
        wd.k.rule(wd.kid(cid), NO_VIOLATION)
        wd.host.fund_appeal(rid, CHALLENGER_WINS, "watchdog", 3 * wd.w.appeal_cost(cid))
        wd.execute(cid)
        assert wd.host.requests[rid].ruling == CHALLENGER_WINS and wd.w.credit[cid].award == expected
        assert wd.host.withdraw_rewards(rid, 0, "watchdog") == 3 * 216
        assert wd.conserved()


# ---- Griefing with cheap challenges --------------------------------------------------------
def test_griefing_a_thousand_valid_items_costs_the_challenger_base_deposit():
    n, victim_delay_cost = 1000, 10  # 1 xDAI per delayed item, an illustrative R2 price
    for dc in (0, 5):
        wd = World(dc=dc)
        for i in range(n):
            wd.mint(f"V{i}", U + Q1)
        wd.mint("griefer", n * (Q1 + dc))
        cids = []
        for i in range(n):
            cid = wd.open(requester=f"V{i}", challenger="griefer")
            wd.w.escalate(cid, f"V{i}")
            wd.k.rule(wd.kid(cid), NO_VIOLATION)
            cids.append(cid)
        for cid in cids:
            wd.execute(cid)
        griefer_cost = -wd.net("griefer")
        assert griefer_cost == n * (Q1 + dc)
        assert all(wd.net(f"V{i}") == dc for i in range(n))  # the victims recover their lock plus the base deposit
        assert (griefer_cost >= n * victim_delay_cost) == (dc + Q1 >= victim_delay_cost)  # R2 holds only through dc
        assert wd.conserved()


# ---- Tiers ----------------------------------------------------------------------------------
def test_every_tier_maps_to_the_host_and_conserves_at_every_rounding_boundary():
    boundaries = [(0, 0, 0), (1, 1, 1), DEFAULT_TIER_BPS, (3333, 6667, 9999), (10000, 10000, 10000)]
    for tier_bps in boundaries:
        for promise in (240, 216, 180, 1):
            for option in (FORMAL, SUBSTANTIVE, MALICIOUS, REFUSE, NO_VIOLATION):
                wd = World(tier_bps=tier_bps, promise=promise)
                wd.mint("A", 1_000)
                wd.mint("B", 1_000)
                cid = wd.open()
                b_before = wd.wallets.balances["B"]
                wd.to_court(cid, option, by="A")
                assert wd.host.requests[wd.rid(cid)].ruling == to_host(option)
                if option in (FORMAL, SUBSTANTIVE, MALICIOUS):
                    tier = option - FORMAL
                    price = promise * tier_bps[tier] // 10000
                    assert wd.wallets.balances["B"] - b_before == U + Q1  # the host's whole cash deposit, any tier
                    if price:
                        wd.w.pay_debt(cid, "A")
                    assert wd.net("B") == U + price and wd.net("A") == -(U + Q1 + price)
                elif option == REFUSE:
                    assert wd.net("A") == -(U + Q1) + (U + Q1) // 2 and wd.net("B") == -Q1 + (U + Q1) // 2
                else:
                    assert wd.net("A") == 0 and wd.net("B") == -Q1
                assert wd.w.escrow == 0 and wd.conserved()
            # a concession at every tier: the fee share and the promise scale, the host's pot does not
            for tier in range(3):
                wd = World(tier_bps=tier_bps, promise=promise)
                wd.mint("A", 1_000)
                wd.mint("B", 1_000)
                cid = wd.open()
                wd.w.concede(cid, "A", tier)
                wd.w.accept(cid, "B")
                price, share = promise * tier_bps[tier] // 10000, Q1 * tier_bps[tier] // 10000
                assert wd.net("A") == -(U + price + share) and wd.net("B") == U + price + share
                assert wd.k.burned == 0 and wd.conserved()


# ---- Cost shifting -------------------------------------------------------------------------
def test_cost_shifting_in_both_directions():
    f, s = TIERS["formal"], TIERS["substantive"]
    # at or below the conceded tier: the challenger bears the court cost
    for conceded, ruled in ((f, FORMAL), (s, FORMAL), (s, SUBSTANTIVE)):
        wd = World()
        wd.mint("A", 1_000)
        wd.mint("B", 1_000)
        cid = wd.open()
        wd.w.concede(cid, "A", conceded)
        wd.w.escalate(cid, "B")  # rejects the offer
        wd.k.rule(wd.kid(cid), ruled)
        wd.execute(cid)
        price = wd.price(ruled - FORMAL)
        assert wd.w.credit[cid].shifted and cid not in wd.w.debts
        assert wd.net("B") == U + price - Q1 and wd.net("A") == -(U + price)
        assert wd.k.burned == Q1 and wd.conserved()
    # above the conceded tier: the requester pays the higher tier plus the fee the pot reimbursed
    wd = World()
    wd.mint("A", 1_000)
    wd.mint("B", 1_000)
    cid = wd.open()
    wd.w.concede(cid, "A", f)
    wd.w.escalate(cid, "B")
    wd.k.rule(wd.kid(cid), SUBSTANTIVE)
    wd.execute(cid)
    assert not wd.w.credit[cid].shifted and wd.w.debts[cid].amount == wd.price(s) - wd.price(f)
    wd.w.pay_debt(cid, "A")
    assert wd.net("A") == -(U + Q1 + wd.price(s)) and wd.net("B") == U + wd.price(s)
    # the bound: the shift can only net off wrapper-held money; at a zero tier price nothing shifts
    wd = World(tier_bps=(0, 5000, 10000))
    wd.mint("A", 1_000)
    wd.mint("B", 1_000)
    cid = wd.open()
    wd.w.concede(cid, "A", f)
    wd.w.escalate(cid, "B")
    wd.k.rule(wd.kid(cid), FORMAL)
    wd.execute(cid)
    assert wd.w.credit[cid].award == 0 and wd.net("B") == U  # its fee came back through the pot regardless
    # refusal after a concession: the escrow returns
    wd = World()
    wd.mint("A", 1_000)
    wd.mint("B", 1_000)
    cid = wd.open()
    wd.w.concede(cid, "A", s)
    wd.w.escalate(cid, "B")
    wd.k.rule(wd.kid(cid), REFUSE)
    wd.execute(cid)
    assert wd.w.claimable["A"] == wd.price(s) and wd.net("A") == -(U + Q1) + (U + Q1) // 2
    assert wd.conserved()


# ---- Batch concession ----------------------------------------------------------------------
def test_batch_concession_touches_only_the_callers_cases():
    wd = World()
    for who in ("E", "B", "C", "F", "G"):
        wd.mint(who, 1_000)
    wd.mint("A", 3 * (U + Q1) + 3 * wd.price(1) + 3 * (wd.price(2) - wd.price(1)) - 1)  # one unit short of malicious
    a_cases = [wd.open("A", ch) for ch in ("B", "C", "B")]
    e_cases = [wd.open("E", ch) for ch in ("F", "G")]
    wd.w.concede(a_cases[0], "A", TIERS["formal"])
    with pytest.raises(Rejected):
        wd.w.concede_all("A", TIERS["substantive"], cids=a_cases + e_cases[:1])  # another party's case
    assert all(wd.w.credit[cid].conceded_tier is None for cid in e_cases)
    done = wd.w.concede_all("A", TIERS["substantive"])
    assert done == a_cases and wd.w.events[-1][0] == "ConcededAll"
    assert all(wd.w.credit[cid].conceded_tier == TIERS["substantive"] for cid in a_cases)
    assert all(wd.w.credit[cid].conceded_tier is None and wd.w.credit[cid].escrow == 0 for cid in e_cases)
    assert wd.net("E") == -2 * (U + Q1) and wd.net("A") == -3 * (U + Q1) - 3 * wd.price(1)
    assert wd.w.concede_all("A", TIERS["substantive"]) == []  # nothing left to raise
    # all or nothing: without the cash for every case, none concedes
    assert wd.wallets.balances["A"] == 3 * (wd.price(2) - wd.price(1)) - 1
    with pytest.raises(Rejected):
        wd.w.concede_all("A", TIERS["malicious"])
    assert all(wd.w.credit[cid].conceded_tier == TIERS["substantive"] for cid in a_cases)
    assert wd.conserved()


# ---- Bonding rule --------------------------------------------------------------------------
def test_bonding_rule_is_decidable_from_wrapper_events_at_the_submission_time():
    wd = World(threshold=3)
    wd.mint("S", 10_000)
    wd.mint("T", 2 * (U + Q1))
    t0 = wd.clock.now
    r1 = wd.host.submit(Kind.REGISTRATION, "S")
    assert evidence_display(wd.host, wd.w, "S", t0)["violation"] == FORMAL  # unbonded, no standing
    wd.clock.advance(DAY)
    wd.w.post_bond("S", 2 * wd.promise)
    r2 = wd.host.submit(Kind.REGISTRATION, "S")  # two open requests, bond covers two
    t2 = wd.clock.now
    assert evidence_display(wd.host, wd.w, "S", t2)["violation"] is None
    wd.clock.advance(DAY)
    r3 = wd.host.submit(Kind.REGISTRATION, "S")  # three open, bond covers two
    t3 = wd.clock.now
    assert evidence_display(wd.host, wd.w, "S", t3)["violation"] == FORMAL
    wd.clock.advance(1)
    wd.w.post_bond("S", wd.promise)  # a later bond does not repair the submission block
    assert evidence_display(wd.host, wd.w, "S", t3)["violation"] == FORMAL
    assert evidence_display(wd.host, wd.w, "S", t0)["violation"] == FORMAL
    # standing above the threshold is the other way through, and one recorded default takes it away
    wd.w.accrue_standing("gov", "T", 3)
    wd.host.submit(Kind.REGISTRATION, "T")
    assert evidence_display(wd.host, wd.w, "T", wd.clock.now)["violation"] is None
    wd.mint("B", 100)
    cid = wd.open("T", "B")  # T's cash is now exactly gone: the promise becomes a debt
    assert wd.wallets.balances["T"] == 0
    wd.to_court(cid, MALICIOUS, by="T")
    assert wd.w.standing("T") == 2
    wd.clock.advance(1)
    wd.mint("T", U + Q1)
    wd.host.submit(Kind.REGISTRATION, "T")
    assert evidence_display(wd.host, wd.w, "T", wd.clock.now)["violation"] == FORMAL
    assert r1 and r2 and r3 and wd.conserved()


# ---- Two wallets ---------------------------------------------------------------------------
def test_two_wallets_via_concession_move_only_the_pairs_money():
    wd = World()
    wd.mint("me1", 1_000)
    wd.mint("me2", 1_000)
    wd.mint("bystander", 1_000)
    cid = wd.open("me1", "me2")
    wd.w.concede(cid, "me1", TIERS["malicious"])
    wd.w.accept(cid, "me2")
    assert wd.w.claimable.get("me1", 0) == 0  # at the malicious tier the whole held fee is the challenger's
    wd.w.claim("me2")
    assert wd.net("me1") + wd.net("me2") == 0 and wd.net("me1") == -(U + wd.price(2) + Q1)
    assert wd.net("bystander") == 0 and wd.w.surplus == 0 and wd.w.reserve == 0 and wd.k.burned == 0
    assert wd.conserved()


def test_two_wallets_via_court_burn_the_fee_and_nobody_else_pays():
    wd = World()
    wd.mint("me1", 10_000)
    wd.mint("me2", 10_000)
    wd.mint("bystander", 1_000)
    cid = wd.open("me1", "me2")
    rid = wd.rid(cid)
    wd.w.escalate(cid, "me1")
    wd.k.rule(wd.kid(cid), NO_VIOLATION)
    cost = wd.w.appeal_cost(cid)
    wd.host.fund_appeal(rid, CHALLENGER_WINS, "me2", 3 * cost)
    wd.host.fund_appeal(rid, REQUESTER_WINS, "me1", 2 * cost)
    wd.k.rule(wd.kid(cid), MALICIOUS)
    wd.execute(cid)
    wd.w.pay_debt(cid, "me1")
    wd.host.withdraw_rewards(rid, 0, "me1")
    wd.host.withdraw_rewards(rid, 0, "me2")
    wd.w.claim("me2")
    assert wd.net("me1") + wd.net("me2") == -(Q1 + cost) == -wd.k.burned
    assert wd.net("bystander") == 0 and wd.w.surplus == 0 and wd.w.reserve == 0
    assert wd.conserved()


# ---- Defaulter -----------------------------------------------------------------------------
def test_defaulter_pays_the_prepayment_at_once_and_loses_standing_until_payment():
    wd = World()
    wd.mint("A", U + Q1)  # exactly the lock, no cash for a promise
    wd.mint("B", 1_000)
    cid = wd.open()
    b_cash = wd.wallets.balances["B"]
    wd.to_court(cid, MALICIOUS)
    assert wd.wallets.balances["B"] - b_cash == U + Q1  # the host's cash, at once, through the host
    assert wd.w.debts[cid].remaining == wd.price(2) and wd.w.claimable.get("B", 0) == 0
    assert wd.w.standing("A") == -1 and wd.net("B") == U
    wd.clock.advance(365 * DAY)
    with pytest.raises(Rejected):
        wd.w.claim("B")
    assert wd.w.standing("A") == -1  # no later mechanism restores it without payment
    wd.mint("A", U + Q1)  # the lock for one more request and nothing else
    cid2 = wd.open()
    with pytest.raises(Rejected):
        wd.w.concede(cid2, "A", TIERS["formal"])  # cash to concede: the defaulter's only exit is court
    wd.mint("A", 1_000)
    wd.w.pay_debt(cid, "A")
    assert wd.w.standing("A") == 0 and wd.w.claim("B") == wd.price(2)
    assert wd.conserved()


# ---- Farmed standing -----------------------------------------------------------------------
def test_farmed_standing_gains_throughput_only():
    wd = World()
    wd.w.accrue_standing("gov", "farm", 100)  # age and volume, no capital
    n = 10
    wd.mint("farm", n * (U + Q1))  # the whole lock for ten concurrent submissions
    hunters = [f"H{i}" for i in range(n)]
    for h in hunters:
        wd.mint(h, Q1)
    cids = []
    for h in hunters:
        assert evidence_display(wd.host, wd.w, "farm", wd.clock.now)["violation"] is None  # unbonded, by standing
        cids.append(wd.open("farm", h))
    assert wd.w.bond.get("farm", 0) == 0 and wd.host.open_requests("farm") == n  # throughput: ten for 65 each
    for cid in cids:
        wd.to_court(cid, MALICIOUS)
    assert all(wd.net(h) == U for h in hunters)  # the credit line beyond a bond is worth the prepayment only
    assert wd.w.standing("farm") == 100 - n and sum(d.remaining for d in wd.w.debts.values()) == n * wd.price(2)
    t = payoff_table(D / 10, Q1 / 10, U / 10)["tiers"]["malicious"]
    assert t["min_conf_defaulter"] == round((Q1 / 10) / (Q1 / 10 + U / 10), 6)  # the threshold the prepayment clears
    assert wd.conserved()


# ---- Compromised publisher -----------------------------------------------------------------
def test_compromised_publisher_stays_catchable():
    wd = World()
    wd.w.accrue_standing("gov", "pub", 100)
    n = 50
    wd.mint("pub", n * (U + Q1))
    hunters = [f"H{i}" for i in range(n)]
    for h in hunters:
        wd.mint(h, Q1)
    cids = [wd.open("pub", h) for h in hunters]
    for cid in cids:
        wd.clock.now = wd.w.cases[cid].deadline
        wd.w.escalate(cid, "anyone")
        wd.k.rule(wd.kid(cid), MALICIOUS)
    stake = 3 * wd.w.appeal_cost(cids[0])
    assert wd.wallets.balances["pub"] < stake  # the attacker cannot buy even one loser-side appeal
    for cid in cids:
        wd.execute(cid)
    assert all(wd.net(h) == U for h in hunters)  # each hunter risked 0.5 and holds 6 in cash plus a 24 promise
    assert wd.w.standing("pub") == 100 - n
    assert sum(d.remaining for d in wd.w.debts.values()) == n * wd.price(2)
    assert n * Q1 < n * U  # the threshold: fee at risk against the cash award, every case
    assert wd.conserved()


# ---- Policy immutability -------------------------------------------------------------------
def test_policy_immutability_blocks_the_bonding_rule_by_arbitrator_switch():
    wd = World(bonding_rule=False)  # a registry deployed without the rule in its policy
    wd.mint("S", 1_000)
    wd.host.submit(Kind.REGISTRATION, "S")
    shown = evidence_display(wd.host, wd.w, "S", wd.clock.now)
    assert shown["ok"] is False and shown["rule_in_policy"] is False and shown["violation"] is None
    successor = CreditedWrapper(wd.host, wd.k, wd.clock, wd.wallets, "gov", promise=wd.promise)
    successor.register_epoch("gov", 0, 0, Q1)
    wd.host.switch_arbitrator("gov", successor)
    assert wd.host.arbitrator is successor and wd.host.policy.bonding_rule is False
    assert evidence_display(wd.host, successor, "S", wd.clock.now)["violation"] is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        wd.host.policy.bonding_rule = True  # type: ignore[misc]
    with pytest.raises(AttributeError):
        wd.host.policy = Policy(True, wd.promise)  # type: ignore[misc]
    assert wd.conserved()


# ---- Retirement ----------------------------------------------------------------------------
def test_retirement_leaves_promises_bonds_and_debts_enforceable():
    wd = World()
    for who in ("A", "B", "C", "E"):
        wd.mint(who, 1_000)
    wd.w.post_bond("A", 100)
    cid = wd.open("A", "B")
    wd.to_court(cid, MALICIOUS, by="A")  # bond pays first, the rest is a promise
    assert wd.w.bond["A"] == 0 and wd.w.debts[cid].remaining == wd.price(2) - 100 and wd.w.standing("A") == -1
    cid2 = wd.open("C", "E")
    wd.w.concede(cid2, "C", TIERS["substantive"])
    cid3 = wd.open("A", "B")
    wd.w.deactivate("gov")
    successor = CreditedWrapper(wd.host, wd.k, wd.clock, wd.wallets, "gov", promise=wd.promise)
    successor.register_epoch("gov", 0, 0, Q1)
    wd.host.switch_arbitrator("gov", successor)
    with pytest.raises(Rejected):
        wd.w.post_bond("A", 10)  # no new bonds on a retired instance
    wd.w.accept(cid2, "E")  # the open concession still settles
    wd.to_court(cid3, SUBSTANTIVE, by="A")  # a case opened under the old instance is ruled to it, not the successor
    assert wd.w.debts[cid3].remaining == wd.price(1) and successor.cases == {}
    wd.w.pay_debt(cid, "A")
    wd.w.pay_debt(cid3, "A")
    assert wd.w.standing("A") == 0
    assert wd.w.claim("B") == 100 + (wd.price(2) - 100) + wd.price(1)
    assert wd.w.claim("E") == wd.price(1) + Q1 * DEFAULT_TIER_BPS[1] // 10000
    assert wd.w.claim("C") == Q1 - Q1 * DEFAULT_TIER_BPS[1] // 10000
    assert wd.w.claimable.get("A", 0) == 0  # A's bond was consumed by the award; nothing is owed to A
    assert wd.w.balance == 0 and wd.w.retired and wd.conserved()


def test_bond_withdrawal_waits_for_the_notice_and_for_every_own_case_and_debt():
    wd = World()
    wd.mint("A", 1_000)
    wd.mint("B", 1_000)
    wd.w.post_bond("A", wd.promise)
    cid = wd.open()
    wd.w.announce_bond_withdrawal("A", wd.promise)
    assert wd.w.bonding_status("A", 1, wd.clock.now)["bonded"] is False  # announced is gone for the display
    with pytest.raises(Rejected):
        wd.w.withdraw_bond("A")  # notice
    wd.clock.advance(wd.w.BOND_NOTICE)
    with pytest.raises(Rejected):
        wd.w.withdraw_bond("A")  # an open case
    wd.to_court(cid, FORMAL, by="A")  # the bond pays the formal price first
    assert wd.w.bond["A"] == wd.promise - wd.price(0) and cid not in wd.w.debts
    assert wd.w.withdraw_bond("A") == wd.promise - wd.price(0)
    assert wd.w.claim("A") == wd.promise - wd.price(0) + 0 and wd.conserved()


# ---- S1: silence escalates -----------------------------------------------------------------
def test_silence_escalates_at_the_prepaid_first_instance():
    wd = World()
    wd.mint("A", 1_000)
    wd.mint("B", 1_000)
    cid = wd.open()
    with pytest.raises(Rejected):
        wd.w.escalate(cid, "B")  # the challenge is B's opening offer: B waits the window
    with pytest.raises(Rejected):
        wd.w.lapse(cid)  # covered: lapse is unreachable
    wd.clock.now = wd.w.cases[cid].deadline
    assert wd.w.escalate(cid, "anyone") is True  # nobody paid anything more: the first instance was prepaid
    wd.k.rule(wd.kid(cid), SUBSTANTIVE)
    wd.execute(cid)
    wd.w.pay_debt(cid, "A")
    assert wd.net("A") == -(U + Q1 + wd.price(1)) and wd.net("B") == U + wd.price(1)
    assert wd.conserved()


def test_cash_to_concede_is_mandatory_and_a_concession_only_rises():
    wd = World()
    wd.mint("A", U + Q1)
    wd.mint("B", 1_000)
    cid = wd.open()
    with pytest.raises(Rejected):
        wd.w.concede(cid, "A", TIERS["formal"])  # no cash: the only exit is court
    assert wd.w.credit[cid].conceded_tier is None and wd.w.escrow == 0
    wd.mint("A", 1_000)
    wd.w.concede(cid, "A", TIERS["formal"])
    with pytest.raises(Rejected):
        wd.w.concede(cid, "A", TIERS["formal"])
    a = wd.wallets.balances["A"]
    wd.w.concede(cid, "A", TIERS["substantive"])
    assert a - wd.wallets.balances["A"] == wd.price(1) - wd.price(0) and wd.w.escrow == wd.price(1)
    assert wd.conserved()


def test_a_live_concession_binds_its_owner_and_is_a_quote_after_the_deadline():
    wd = World()
    wd.mint("A", 1_000)
    wd.mint("B", 1_000)
    cid = wd.open()
    wd.w.concede(cid, "A", TIERS["formal"])
    with pytest.raises(Rejected):
        wd.w.escalate(cid, "A")  # bound by its own offer (S2)
    with pytest.raises(Rejected):
        wd.w.escalate(cid, "anyone")
    wd.clock.now = wd.w.cases[cid].deadline
    cid2 = wd.open()
    wd.w.concede(cid2, "A", TIERS["formal"])
    wd.clock.now = wd.w.cases[cid2].deadline
    wd.w.accept(cid2, "B")  # after the deadline, still executable by the challenger
    assert wd.w.escalate(cid, "anyone") is True  # and it binds nobody's escalation any more
    assert wd.w.cases[cid].state is State.FORWARDED and wd.w.cases[cid2].state is State.CONCEDED
    assert wd.conserved()


# ---- The payoff table ----------------------------------------------------------------------
def test_payoff_table_reproduces_the_rfc_numbers():
    v = vanilla_payoffs()
    assert (v["s_A"], v["s_B"], v["g_B"], v["band_width"]) == (51.6, 21.6, 30, 21.6)
    t = payoff_table(30, 0.5, 6)["tiers"]
    assert t["malicious"]["g_B_paying"] == 30 and t["malicious"]["s_A"] == 30.5
    assert t["formal"]["price"] == 2.4 and t["formal"]["g_B_paying"] == 8.4
    assert round(t["malicious"]["min_conf_paying"], 3) == 0.016 and round(t["malicious"]["min_conf_defaulter"], 3) == 0.077
    assert round(21.6 / (21.6 + 6), 2) == 0.78  # the RFC's 78 percent against a defaulter at today's fee
    assert all(row["band_width"] == 0.5 for row in t.values())


# ---- Random sequences ----------------------------------------------------------------------
def test_random_sequences_keep_every_invariant():
    rng = random.Random(11)
    parties = ["A", "B", "C", "E"]
    for _ in range(30):
        wd = World(dc=rng.choice([0, 5]), tier_bps=rng.choice([DEFAULT_TIER_BPS, (0, 5000, 10000), (1, 2, 3)]),
                   flip_tier=rng.choice([None, 2]))
        for who in parties + ["F1", "F2"]:
            wd.mint(who, rng.choice([100, 1_000, 10_000]))
        cids = []
        for _step in range(40):
            op = rng.random()
            try:
                if op < 0.2 or not cids:
                    a, b = rng.sample(parties, 2)
                    cids.append(wd.open(a, b))
                elif op < 0.3:
                    cid = rng.choice(cids)
                    wd.w.concede(cid, wd.w.cases[cid].requester, rng.randrange(3))
                elif op < 0.36:
                    cid = rng.choice(cids)
                    wd.w.accept(cid, wd.w.cases[cid].challenger)
                elif op < 0.42:
                    wd.w.concede_all(rng.choice(parties), rng.randrange(3))
                elif op < 0.55:
                    wd.w.escalate(rng.choice(cids), rng.choice(parties + ["anyone"]))
                elif op < 0.65:
                    cid = rng.choice(cids)
                    wd.k.rule(wd.kid(cid), rng.choice([REFUSE, NO_VIOLATION, FORMAL, SUBSTANTIVE, MALICIOUS]))
                elif op < 0.72:
                    cid = rng.choice(cids)
                    wd.host.fund_appeal(wd.rid(cid), rng.choice([REQUESTER_WINS, CHALLENGER_WINS]),
                                        rng.choice(parties + ["F1", "F2"]), rng.choice([100, 700, 5_000]))
                elif op < 0.8:
                    cid = rng.choice(cids)
                    wd.k.execute(wd.kid(cid))
                elif op < 0.85:
                    cid = rng.choice(list(wd.w.debts) or cids)
                    wd.w.pay_debt(cid, rng.choice(parties), rng.choice([1, 50, None]))
                elif op < 0.9:
                    wd.w.post_bond(rng.choice(parties), rng.choice([10, 240]))
                elif op < 0.95:
                    for who in parties:
                        if wd.w.claimable.get(who, 0) > 0:
                            wd.w.claim(who)
                else:
                    cid = rng.choice(cids)
                    wd.host.withdraw_rewards(wd.rid(cid), rng.choice([0, 1]), rng.choice(parties + ["F1", "F2"]))
            except (Rejected, KeyError, StopIteration):
                pass
            if rng.random() < 0.4:
                wd.clock.advance(rng.choice([3600, DAY, 3 * DAY]))
            wd.w.check()
        assert wd.conserved()

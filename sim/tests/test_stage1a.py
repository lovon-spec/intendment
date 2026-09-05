# SPDX-License-Identifier: MIT
"""Stage-1a acceptance tests for the IntendmentArbitrator model, spec 0.5.

Every test is a trace from the specification's section 14 or an acceptance area
of the v0.8 review. The model checks conservation and the account invariants
after every transition, so a passing trace also proves those held throughout.
"""
import os
import random

import pytest
import yaml

from intendment.model import (CHALLENGER_WINS, REFUSE, REQUESTER_WINS, Clock, Host, Kind, Rejected, Resolver, State,
                              Wallets, Wrapper)

DAY = 86400
D, K_COST = 300, 216  # deposit and the resolver's cost, Scout-like in small units


class World:
    def __init__(self, *, premium_bps=0, margin_bps=0, principal=None, offers=False, max_cost=None):
        self.clock = Clock()
        self.wallets = Wallets()
        self.host = Host(self.wallets)
        self.k = Resolver(K_COST)
        self.w = Wrapper(self.host, self.k, self.clock, self.wallets, "gov", offers=offers)
        self.w.register_epoch("gov", margin_bps, premium_bps, max_cost or 2 * K_COST)
        self.epoch = self.w.epochs[1]
        self.q, self.pi = self.epoch.quote, self.epoch.premium
        self.w.fund_reserve("gov", (self.epoch.max_cost - self.q) * 3 if principal is None else principal)

    def open(self, kind=Kind.REGISTRATION, requester="A", challenger="B", challenger_deposit=0):
        rid = self.host.submit(kind, requester, D + self.q)
        cid = self.host.challenge(rid, challenger, self.q, challenger_deposit)
        self.w.bind(cid)
        return cid

    def past_deadline(self, cid):
        self.clock.now = self.w.cases[cid].deadline

    def past_funding(self, cid):
        self.clock.now = self.w.cases[cid].funding_end

    def request(self, cid):
        return self.host.requests[self.host.dispute_to_request[cid]]


def test_every_yaml_transition_has_a_model_method():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "..", "..", "spec", "intendment-arbitrator-state-machine.yaml"), encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    ids = {t["id"] for t in doc["transitions"]} | {g["id"] for g in doc["reserve_operations"]}
    assert ids == set(Wrapper.TRANSITIONS)
    for method in Wrapper.TRANSITIONS.values():
        assert callable(getattr(Wrapper, method))


def test_default_concession_returns_the_fee_and_pays_the_pot():
    wd = World()
    cid = wd.open()
    wd.w.concede(cid, "A")
    c = wd.w.cases[cid]
    assert c.state is State.CONCEDED
    assert wd.w.claimable["A"] == wd.q and wd.w.claimable.get("B", 0) == 0
    assert wd.request(cid).ruling == CHALLENGER_WINS
    assert wd.wallets.balances["B"] == D + wd.q  # the host's pot, D + F_A, went to the challenger
    assert wd.w.claim("A") == wd.q and wd.wallets.balances["A"] == wd.q


def test_premium_is_kept_by_the_pool_and_paid_by_the_requester():
    wd = World(premium_bps=1000)
    before = wd.w.surplus
    cid = wd.open()
    wd.w.concede(cid, "A")
    assert wd.w.claimable["A"] == wd.q - wd.pi
    assert wd.w.surplus == before + wd.pi
    assert wd.pi == wd.q // 10


def test_silent_challenger_is_conceded_to_without_any_challenger_action():
    wd = World()
    cid = wd.open()
    wd.clock.advance(DAY)
    wd.w.concede(cid, "A", max_share=0)
    assert wd.w.cases[cid].state is State.CONCEDED


def test_escalation_paths_are_disjoint_in_time():
    wd = World()
    cid = wd.open()
    with pytest.raises(Rejected):
        wd.w.escalate(cid, "B")  # the challenger cannot escalate before the deadline
    with pytest.raises(Rejected):
        wd.w.escalate(cid, "anyone")
    assert wd.w.escalate(cid, "A") is True  # the requester may, at once
    cid2 = wd.open()
    wd.past_deadline(cid2)
    assert wd.w.escalate(cid2, "anyone") is True


def test_temporary_resolver_failure_then_recovery_forwards_instead_of_lapsing():
    wd = World()
    cid = wd.open()
    wd.k.accepting = False
    assert wd.w.escalate(cid, "A") is False
    c = wd.w.cases[cid]
    assert c.first_forward_failure == wd.clock.now and c.state is State.OPEN
    wd.k.accepting = True  # K recovers, nobody forwards
    wd.past_funding(cid)
    wd.clock.advance(wd.w.RESOLVER_GRACE)
    with pytest.raises(Rejected):
        wd.w.lapse(cid)  # covered: the plain lapse is not available
    assert wd.w.forward_or_lapse(cid) is State.FORWARDED  # the stale failure did not authorize a refusal
    assert c.k_dispute_id is not None


def test_persistent_resolver_failure_lapses_only_after_a_fresh_rejection():
    wd = World()
    wd.w.RESOLVER_GRACE = 10 * DAY  # longer than the window plus the funding period
    cid = wd.open()
    wd.k.accepting = False
    wd.w.escalate(cid, "A")
    failed_at = wd.clock.now
    wd.past_funding(cid)
    with pytest.raises(Rejected):
        wd.w.forward_or_lapse(cid)  # the funding period is over but the grace has not elapsed
    wd.clock.now = failed_at + wd.w.RESOLVER_GRACE
    assert wd.w.forward_or_lapse(cid) is State.LAPSED
    assert wd.w.claimable["B"] == wd.q and wd.request(cid).ruling == REFUSE
    assert wd.wallets.balances["A"] == (D + wd.q) // 2 and wd.wallets.balances["B"] == (D + wd.q) // 2


def test_quote_revert_counts_as_a_failure_and_has_a_terminal_path():
    wd = World()
    cid = wd.open()
    wd.k.quotable = False
    assert wd.w.escalate(cid, "A") is False
    wd.past_funding(cid)
    with pytest.raises(Rejected):
        wd.w.lapse(cid)  # unquotable is not "uncovered"
    wd.clock.advance(wd.w.RESOLVER_GRACE)
    wd.k.quotable = True
    assert wd.w.forward_or_lapse(cid) is State.FORWARDED
    cid2 = wd.open()
    wd.k.quotable = False
    wd.w.escalate(cid2, "A")
    wd.past_funding(cid2)
    wd.clock.advance(wd.w.RESOLVER_GRACE)
    assert wd.w.forward_or_lapse(cid2) is State.LAPSED


def test_a_gas_starved_attempt_is_not_a_qualifying_failure():
    wd = World()
    cid = wd.open()
    with pytest.raises(Rejected):
        wd.w.escalate(cid, "A", gas_ok=False)
    assert wd.w.cases[cid].first_forward_failure == 0
    wd.k.accepting = False
    wd.w.escalate(cid, "A")
    wd.past_funding(cid)
    wd.clock.advance(wd.w.RESOLVER_GRACE)
    with pytest.raises(Rejected):
        wd.w.forward_or_lapse(cid, gas_ok=False)
    assert wd.w.cases[cid].state is State.OPEN


def test_exclusivity_at_funding_end():
    wd = World(principal=0)  # no reserve: every case is under-insured
    cid = wd.open()
    wd.k.cost = 2 * K_COST  # above what the case can pay
    wd.past_funding(cid)
    with pytest.raises(Rejected):
        wd.w.escalate(cid, "anyone")
    wd.w.lapse(cid)
    assert wd.w.cases[cid].state is State.LAPSED
    wd2 = World()
    cid2 = wd2.open()
    wd2.past_funding(cid2)
    with pytest.raises(Rejected):
        wd2.w.lapse(cid2)
    assert wd2.w.escalate(cid2, "anyone") is True


def test_a_reserve_gift_after_the_funding_period_rescues_an_uncovered_case():
    wd = World(principal=0)
    cid = wd.open()
    wd.k.cost = K_COST + 50
    wd.past_funding(cid)
    with pytest.raises(Rejected):
        wd.w.escalate(cid, "anyone")
    wd.w.fund_reserve("donor", 50)  # G2 stays open after fundingEnd, on purpose
    with pytest.raises(Rejected):
        wd.w.lapse(cid)
    assert wd.w.escalate(cid, "anyone") is True
    assert wd.w.surplus == 0  # the gift was consumed by the draw


def test_loss_waterfall_consumes_surplus_before_principal():
    wd = World(principal=1000)
    wd.w.fund_reserve("donor", 30)  # surplus 30
    cid = wd.open()
    wd.k.cost = K_COST + 100  # within maxCost: covered by the earmark
    assert wd.w.escalate(cid, "A") is True
    assert wd.w.surplus == 0 and wd.w.principal == 1000 - 70


def test_partial_funding_use_refunds_pro_rata_with_floor_and_keeps_the_dust():
    wd = World(principal=0)
    cid = wd.open()
    wd.k.cost = K_COST + 5
    wd.w.fund(cid, "f1", 10)
    wd.w.fund(cid, "f2", 10)
    assert wd.w.escalate(cid, "A") is True
    c = wd.w.cases[cid]
    assert c.funding_used == 5 and c.refundable == 15
    assert wd.w.claim_funding(cid, "f1") == 7 and wd.w.claim_funding(cid, "f2") == 7
    with pytest.raises(Rejected):
        wd.w.claim_funding(cid, "f1")  # once
    assert wd.w.refund_liability == 1  # the rounding remainder stays a liability
    assert wd.w.claim("f1") == 7 and wd.w.claim("f2") == 7


def test_ten_thousand_dust_funders_do_not_change_the_cost_of_forwarding():
    wd = World(principal=0)
    cid = wd.open()
    wd.k.cost = K_COST + 3000
    for i in range(10_000):
        wd.w.fund(cid, f"f{i}", 1)
    assert wd.w.escalate(cid, "A") is True
    assert wd.w.forward_iterations == 0
    c = wd.w.cases[cid]
    assert c.funding_used == 3000 and c.refundable == 7000
    assert wd.w.claim_funding(cid, "f0") == 0  # floor(1 * 7000 / 10000)
    assert wd.w.refund_liability == 7000


def test_appeal_is_host_only():
    wd = World()
    cid = wd.open()
    wd.w.escalate(cid, "A")
    with pytest.raises(Rejected):
        wd.w.appeal(cid, "eoa")
    wd.w.appeal(cid, wd.host)


def test_rulings_are_relayed_once_and_the_host_pays():
    wd = World()
    cid = wd.open()
    wd.w.escalate(cid, "A")
    k_id = wd.w.cases[cid].k_dispute_id
    wd.w.rule(k_id, REQUESTER_WINS)
    assert wd.wallets.balances["A"] == D + wd.q
    with pytest.raises(Rejected):
        wd.w.rule(k_id, REQUESTER_WINS)


def test_a_replacement_bid_may_not_shorten_a_live_bid():
    wd = World(offers=True)
    cid = wd.open()
    c = wd.w.cases[cid]
    wd.w.set_ask(cid, "B", 100)
    wd.w.bid(cid, "A", 5, c.deadline - DAY)
    with pytest.raises(Rejected):
        wd.w.bid(cid, "A", 6, wd.clock.now + 2 * wd.w.V)  # earlier than the live bid
    with pytest.raises(Rejected):
        wd.w.escalate(cid, "A")  # bound by its own live bid
    wd.w.bid(cid, "A", 6, c.deadline - DAY)
    wd.w.accept_bid(cid, "B", 6)
    assert c.state is State.CONCEDED and wd.w.claimable["B"] == 6 and wd.w.claimable["A"] == wd.q - 6


def test_crossing_executes_deterministically():
    wd = World(offers=True)
    cid = wd.open()
    c = wd.w.cases[cid]
    wd.w.set_ask(cid, "B", 50)
    wd.w.bid(cid, "A", 20, c.deadline)
    wd.w.set_ask(cid, "B", 20)  # at or below the live bid: executes at the bid
    assert c.state is State.CONCEDED and wd.w.claimable["B"] == 20


def test_retirement_procedure_and_withdrawal_precision():
    wd = World(principal=1000)
    gov = "gov"
    with pytest.raises(Rejected):
        wd.w.announce_withdrawal(gov, 100, gov)  # not retired
    cid = wd.open()
    wd.w.deactivate(gov)
    with pytest.raises(Rejected):
        wd.w.register_epoch(gov, 0, 0, 500)  # retired: no new epochs
    wd.w.announce_withdrawal(gov, 1000, gov)
    wd.clock.advance(wd.w.RESERVE_TIMELOCK + wd.w.RETIREMENT_LOCK)
    with pytest.raises(Rejected):
        wd.w.execute_withdrawal(gov)  # a case is still open
    wd.k.cost = K_COST + 100
    wd.w.escalate(cid, "A")  # a loss of 100 hits principal after the announcement
    with pytest.raises(Rejected):
        wd.w.execute_withdrawal(gov)  # 1000 > the 900 of principal left
    wd.w.cancel_withdrawal(gov)
    wd.w.announce_withdrawal(gov, 900, gov)
    wd.clock.advance(wd.w.RESERVE_TIMELOCK)
    assert wd.w.execute_withdrawal(gov) == 900
    assert wd.w.pending is None and wd.w.principal == 0


def test_surplus_moves_only_to_a_successor_of_the_same_factory():
    wd = World()
    wd.w.fund_reserve("donor", 40)
    stranger = Wrapper(Host(wd.wallets), wd.k, wd.clock, wd.wallets, "gov", factory="other")
    successor = Wrapper(wd.host, wd.k, wd.clock, wd.wallets, "gov")
    wd.w.deactivate("gov")
    wd.clock.advance(wd.w.RETIREMENT_LOCK)
    with pytest.raises(Rejected):
        wd.w.migrate_surplus("gov", stranger)
    assert wd.w.migrate_surplus("gov", successor) == 40
    assert successor.surplus == 40 and wd.w.surplus == 0


def test_self_challenges_occupy_capacity_and_the_premium_prices_it():
    wd = World(principal=2 * K_COST, premium_bps=500)  # room for two insured cases
    a = wd.open(requester="me", challenger="me")
    b = wd.open(requester="me", challenger="me")
    c = wd.open(requester="honest", challenger="hunter")
    assert wd.w.mode(a) == "insured" and wd.w.mode(b) == "insured" and wd.w.mode(c) == "under-insured"
    assert any(e[0] == "UnderInsured" and e[1] == c for e in wd.w.events)
    wd.w.concede(a, "me")
    wd.w.concede(b, "me")
    assert wd.w.claimable["me"] == 2 * (wd.q - wd.pi)  # the self-challenger paid the premium twice
    assert wd.w.surplus == 2 * wd.pi
    d = wd.open(requester="honest2", challenger="hunter")
    assert wd.w.mode(d) == "insured"  # capacity released by the settlements


def test_an_underinsured_removal_that_nobody_forwards_ends_in_a_refusal():
    wd = World(principal=0)
    cid = wd.open(kind=Kind.REMOVAL, requester="remover", challenger="owner")
    assert wd.w.cases[cid].state is State.FORWARDABLE
    wd.k.cost = 2 * K_COST
    with pytest.raises(Rejected):
        wd.w.forward(cid)
    wd.past_funding(cid)
    wd.w.lapse(cid)
    assert wd.request(cid).ruling == REFUSE  # on Light the item stays registered: disclosed


def test_a_removal_is_forwarded_by_anyone_in_a_second_transaction():
    wd = World()
    cid = wd.open(kind=Kind.REMOVAL, requester="remover", challenger="owner")
    assert wd.w.forward(cid) is True
    assert wd.w.cases[cid].state is State.FORWARDED


def test_the_party_of_record_is_whoever_called_the_host():
    wd = World()
    cid = wd.open(challenger="router-contract")
    assert wd.w.cases[cid].challenger == "router-contract"  # not the user behind it
    wd.w.concede(cid, "A")
    assert wd.wallets.balances["router-contract"] == D + wd.q


def test_a_rejecting_receiver_never_blocks_a_transition():
    wd = World()
    wd.wallets.rejecting.add("B")
    cid = wd.open()
    wd.w.concede(cid, "A")  # the host's send to B fails and the host keeps it; the wrapper is unaffected
    assert wd.host.stuck == D + wd.q
    wd.w.claimable["B"] = 5
    wd.w.balance += 5
    assert wd.w.claim("B") == 0 and wd.w.claimable["B"] == 5  # the credit stays until B can receive
    wd.wallets.rejecting.discard("B")
    assert wd.w.claim("B", to="B-cold") == 5


def test_never_refuses_a_challenge_for_reserve_state():
    wd = World(principal=0)
    cid = wd.open()
    assert wd.w.cases[cid].earmark == 0 and wd.w.mode(cid) == "under-insured"


def test_random_sequences_keep_every_invariant():
    rng = random.Random(7)
    for _ in range(40):
        wd = World(principal=rng.choice([0, 300, 5000]), premium_bps=rng.choice([0, 500]), offers=True)
        cids = []
        for step in range(30):
            op = rng.random()
            try:
                if op < 0.25 or not cids:
                    cids.append(wd.open(kind=rng.choice([Kind.REGISTRATION, Kind.REMOVAL])))
                elif op < 0.35:
                    wd.w.concede(rng.choice(cids), "A")
                elif op < 0.5:
                    wd.w.escalate(rng.choice(cids), rng.choice(["A", "B", "anyone"]))
                elif op < 0.6:
                    wd.w.forward(rng.choice(cids))
                elif op < 0.7:
                    wd.w.fund(rng.choice(cids), rng.choice(["f1", "f2"]), rng.randint(1, 50))
                elif op < 0.78:
                    wd.w.lapse(rng.choice(cids))
                elif op < 0.84:
                    wd.w.forward_or_lapse(rng.choice(cids))
                elif op < 0.9:
                    wd.w.set_ask(rng.choice(cids), "B", rng.randint(0, wd.q))
                elif op < 0.95:
                    for who in ("A", "B", "f1", "f2"):
                        if wd.w.claimable.get(who, 0) > 0:
                            wd.w.claim(who)
                else:
                    wd.k.cost = rng.choice([K_COST, K_COST + 100, K_COST * 3])
                    wd.k.accepting = rng.random() > 0.2
            except Rejected:
                pass
            if rng.random() < 0.3:
                wd.clock.advance(rng.choice([3600, DAY, 3 * DAY]))
            wd.w.check()

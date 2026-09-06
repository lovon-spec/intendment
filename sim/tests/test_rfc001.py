# SPDX-License-Identifier: MIT
"""Offline tests for the RFC 001 revision-5 model; no RPC/keys/dependencies.

Run: python -m unittest discover -s sim/tests -p 'test_rfc001.py' -v
Pytest also collects these tests alongside the unchanged baseline suite.
"""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import random
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from intendment.rfc001 import (  # noqa: E402
    CaseState, TicketState, Policy, World, Rejected, FinalOffers,
    REFUSE, REQUESTER, CLAIMANT, MAX_UINT, merkle, verifies, leaf_hash,
)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.p = Policy("rfc5-test")
        self.w.configure("governor", "host", self.p)
        for name in ("alice", "bob", "carol", "dave", "eve"):
            self.w.mint(name, 10_000_000)

    def rejected(self, fn, *args, **kwargs):
        before = deepcopy(self.w.__dict__)
        with self.assertRaises(Rejected):
            fn(*args, **kwargs)
        self.assertEqual(self.w.__dict__, before, "revert must roll back money, state AND events")

    def ticket(self, item="item", secured=None, owner="alice", expiry=None):
        if secured is None:
            secured = self.p.gap
        if secured < self.p.gap:
            self.w.set_credit_limit("governor", owner, 10_000_000)
        self.w.deposit_bond(owner, secured + self.p.severity_cap)
        return self.w.reserve(owner, "host", item, secured=secured,
                              nonce=len(self.w.tickets), expiry=expiry or self.w.now + 200)

    def request(self, item="item", secured=None, owner="alice"):
        tid = self.ticket(item, secured, owner)
        self.w.mine()
        key = self.w.host_submit(owner, "host", item)
        return tid, key

    def case(self, item="item", secured=None, claim=None):
        tid, key = self.request(item, secured)
        cid = self.w.challenge("bob", key, claim=claim)
        return tid, key, cid

    def severity(self, admission=1, secured=None):
        tid, key, cid = self.case(secured=secured)
        self.w.concede("alice", cid, admission)
        did = self.w.open_severity("bob", cid, max_fee=self.p.severity_cap)
        return tid, key, cid, did

    def finish(self, did, ruling):
        self.w.publish_ruling("court", did, ruling)
        self.w.mine(self.p.appeal_window)
        return self.w.finalize(did)

    def appeal_both(self, did, provisional):
        self.w.publish_ruling("court", did, provisional)
        rd = self.w.disputes[did].rounds[-1]
        self.w.fund_appeal("carol", did, REQUESTER, rd.targets[REQUESTER])
        self.w.fund_appeal("dave", did, CLAIMANT, rd.targets[CLAIMANT])

    def mandate(self, cases, rung=1, max_cases=None, max_spend=None, expiry=None, owner="alice"):
        root, proofs = merkle([self.w.mandate_leaf(cid) for cid in cases])
        amount = self.p.amount(rung) * len(cases) if max_spend is None else max_spend
        mid = self.w.authorize(owner, root, rung=rung, max_cases=max_cases or len(cases),
                               max_spend=amount, expiry=expiry or self.w.now + 20, nonce=len(self.w.mandates))
        return mid, proofs


class ReservationTests(Fixture):
    def test_locks_award_and_cost_separately(self):
        self.w.deposit_bond("alice", 100_000)
        tid = self.w.reserve("alice", "host", "x", secured=24_000, nonce=0, expiry=1200)
        self.assertEqual(self.w.balance("free", "alice"), 75_500)
        self.assertEqual(self.w.balance("award", tid), 24_000)
        self.assertEqual(self.w.balance("cost", tid), 500)
        self.rejected(self.w.withdraw_bond, "alice", 75_501)

    def test_unused_ticket_cancellation(self):
        tid = self.ticket()
        self.w.cancel_ticket("alice", tid)
        self.assertEqual(self.w.tickets[tid].state, TicketState.CANCELLED)
        self.assertEqual(self.w.balance("free", "alice"), 24_500)
        self.rejected(self.w.cancel_ticket, "alice", tid)

    def test_only_owner_cancels(self):
        tid = self.ticket()
        self.rejected(self.w.cancel_ticket, "bob", tid)

    def test_nonce_cannot_be_reused_after_cancellation(self):
        tid = self.ticket()
        self.w.cancel_ticket("alice", tid)
        self.rejected(self.w.reserve, "alice", "host", "new", secured=24_000, nonce=0, expiry=1200)

    def test_duplicate_slot_cannot_reserve_twice(self):
        self.ticket()
        self.w.deposit_bond("alice", 24_500)
        self.rejected(self.w.reserve, "alice", "host", "item", secured=24_000, nonce=1, expiry=1200)

    def test_expiry_does_not_remove_timely_unbound_backing(self):
        tid = self.ticket(expiry=self.w.now + 10)
        self.w.mine(9)
        key = self.w.host_submit("alice", "host", "item")
        self.w.mine(2)
        self.assertIsNone(self.w.requests[key].ticket)
        self.rejected(self.w.cancel_ticket, "alice", tid)
        self.assertEqual(self.w.bind_ticket(key), tid)
        self.assertEqual(self.w.tickets[tid].state, TicketState.BOUND)

    def test_submission_at_expiry_is_not_covered(self):
        tid = self.ticket(expiry=self.w.now + 10)
        self.w.mine(10)
        key = self.w.host_submit("alice", "host", "item")
        self.rejected(self.w.bind_ticket, key)
        self.w.cancel_ticket("alice", tid)

    def test_same_block_ticket_is_not_covered(self):
        tid = self.ticket()
        key = self.w.host_submit("alice", "host", "item")
        self.rejected(self.w.bind_ticket, key)
        self.w.cancel_ticket("alice", tid)

    def test_stranger_front_run_does_not_consume_collateral(self):
        tid = self.ticket()
        self.w.mine()
        key = self.w.host_submit("bob", "host", "item")
        self.rejected(self.w.bind_ticket, key)
        self.w.cancel_ticket("alice", tid)
        self.assertIsNone(self.w.requests[key].ticket)

    def test_cancel_then_submit_never_revives_ticket(self):
        tid = self.ticket()
        self.w.cancel_ticket("alice", tid)
        self.w.mine()
        key = self.w.host_submit("alice", "host", "item")
        self.rejected(self.w.bind_ticket, key)

    def test_unchallenged_release_requires_actual_execution(self):
        tid, key = self.request()
        self.w.mine(101)
        self.rejected(self.w.release, key)
        self.w.execute_unchallenged(key)
        self.w.release(key)
        self.assertEqual(self.w.balance("free", "alice"), 24_500)
        self.rejected(self.w.release, key)

    def test_credit_capacity_cannot_be_double_used(self):
        self.w.set_credit_limit("governor", "alice", 24_000)
        self.w.deposit_bond("alice", 1000)
        self.w.reserve("alice", "host", "a", secured=0, nonce=0, expiry=1200)
        self.rejected(self.w.reserve, "alice", "host", "b", secured=0, nonce=1, expiry=1200)

    def test_partial_award_backing(self):
        tid, key, cid, did = self.severity(secured=10_000)
        self.finish(did, CLAIMANT)
        self.assertEqual(self.w.cases[cid].paid_award, 10_000)
        self.assertEqual(self.w.cases[cid].debt, 14_000)
        self.assertEqual(self.w.balance("cost", tid), 0)
        self.w.release(key)

    def test_losing_merits_releases_nothing_before_severity_terminal(self):
        tid, key, cid = self.case()
        did = self.w.escalate_merits("alice", cid)
        self.finish(did, CLAIMANT)
        self.assertTrue(self.w.requests[key].resolved)
        self.rejected(self.w.release, key)
        self.w.mine(20)
        self.w.close_severity_window(cid)
        self.w.release(key)
        self.assertEqual(self.w.balance("free", "alice"), 24_500 - self.p.amount(0))

    def test_old_policy_request_keeps_old_terms(self):
        tid, key = self.request()
        self.w.configure("governor", "host", replace(self.p, version="new", award=40_000))
        cid = self.w.challenge("bob", key)
        self.assertEqual(self.w.requests[key].policy, self.p)
        self.assertEqual(self.w.tickets[tid].policy, self.p)
        self.w.concede("alice", cid, 4)
        self.assertEqual(self.w.cases[cid].paid_award, 24_000)

    def test_policy_change_before_submission_invalidates_old_ticket(self):
        tid = self.ticket()
        self.w.configure("governor", "host", replace(self.p, version="new", award=40_000))
        self.w.mine()
        key = self.w.host_submit("alice", "host", "item")
        self.rejected(self.w.bind_ticket, key)
        self.w.cancel_ticket("alice", tid)

    def test_same_item_new_index_does_not_release_old_severity_backing(self):
        tid, old, cid = self.case()
        self.w.concede("alice", cid, 1)
        newer = self.ticket("item")
        self.w.mine()
        key = self.w.host_submit("alice", "host", "item")
        self.assertEqual(key[2], 1)
        self.w.bind_ticket(key)
        self.assertEqual(self.w.requests[key].ticket, newer)
        self.rejected(self.w.release, old)
        self.w.mine(20)
        self.w.close_severity_window(cid)
        self.w.release(old)
        self.assertEqual(self.w.tickets[newer].state, TicketState.BOUND)
        self.assertEqual(self.w.balance("award", newer), 24_000)
        self.assertEqual(self.w.balance("award", tid), 0)

    def test_retirement_preserves_old_tickets_and_claims(self):
        tid = self.ticket()
        self.w.retire("governor")
        self.rejected(self.w.reserve, "alice", "host", "b", secured=0, nonce=1, expiry=1200)
        self.w.mine()
        key = self.w.host_submit("alice", "host", "item")
        cid = self.w.challenge("bob", key)
        self.w.concede("alice", cid, 4)
        self.w.release(key)
        self.w.withdraw_bond("alice", 500)
        self.w.claim_credit("alice", "carol")
        self.w.check()


class LifecycleTests(Fixture):
    def test_no_court_when_positions_agree(self):
        _, key, cid = self.case(claim=1)
        self.w.concede("alice", cid, 1)
        self.assertFalse(self.w.disputes)
        self.assertEqual(self.w.cases[cid].state, CaseState.FINISHED)
        self.assertFalse(self.w.requests[key].registered)

    def test_severity_only_after_concession(self):
        _, key, cid, did = self.severity()
        self.assertEqual(len(self.w.disputes), 1)
        self.assertEqual(self.w.disputes[did].kind, "severity")
        self.assertFalse(self.w.requests[key].registered)

    def test_merits_accept_never_opens_severity(self):
        _, key, cid = self.case()
        did = self.w.escalate_merits("alice", cid)
        self.finish(did, REQUESTER)
        self.assertTrue(self.w.requests[key].registered)
        self.rejected(self.w.open_severity, "bob", cid, max_fee=500)
        self.w.release(key)

    def test_merits_refusal_does_not_create_severity(self):
        _, key, cid = self.case()
        did = self.w.escalate_merits("alice", cid)
        self.finish(did, REFUSE)
        self.assertFalse(self.w.requests[key].registered)
        self.rejected(self.w.open_severity, "bob", cid, max_fee=500)
        self.w.release(key)

    def test_contested_merits_then_contested_severity(self):
        _, key, cid = self.case()
        merits = self.w.escalate_merits("alice", cid)
        self.finish(merits, CLAIMANT)
        self.w.raise_admission("alice", cid, 1)
        severity = self.w.open_severity("bob", cid, max_fee=500)
        self.finish(severity, CLAIMANT)
        self.assertEqual(len(self.w.disputes), 2)
        self.assertEqual(self.w.cases[cid].paid_award, 24_000)
        self.assertFalse(self.w.requests[key].registered)
        self.w.release(key)

    def test_claimant_waits_before_merits_escalation(self):
        _, _, cid = self.case()
        self.rejected(self.w.escalate_merits, "bob", cid)
        self.w.mine(20)
        self.w.escalate_merits("eve", cid)

    def test_admission_can_meet_claim_and_settle(self):
        _, _, cid = self.case()
        self.w.concede("alice", cid, 1)
        self.w.raise_admission("alice", cid, 4)
        self.assertEqual(self.w.cases[cid].state, CaseState.FINISHED)
        self.assertFalse(self.w.disputes)

    def test_merits_loss_with_lowest_claim_needs_no_severity_case(self):
        _, _, cid = self.case(claim=0)
        did = self.w.escalate_merits("alice", cid)
        self.finish(did, CLAIMANT)
        self.assertEqual(self.w.cases[cid].state, CaseState.FINISHED)
        self.assertEqual(len(self.w.disputes), 1)

    def test_early_requester_escalation(self):
        _, _, cid = self.case()
        self.w.escalate_merits("alice", cid)
        self.assertEqual(self.w.cases[cid].state, CaseState.MERITS)

    def test_no_financial_model_censors_unbacked_challenge(self):
        key = self.w.host_submit("alice", "host", "item")
        cid = self.w.challenge("bob", key)
        self.assertIsNone(self.w.requests[key].ticket)
        did = self.w.escalate_merits("alice", cid)
        self.finish(did, CLAIMANT)
        self.rejected(self.w.open_severity, "bob", cid, max_fee=500)
        self.w.mine(20)
        self.w.close_severity_window(cid)
        self.assertEqual(self.w.cases[cid].debt, self.p.amount(0))

    def test_offer_monotonicity(self):
        _, _, cid = self.case()
        self.w.concede("alice", cid, 1)
        self.rejected(self.w.raise_admission, "alice", cid, 0)
        self.rejected(self.w.lower_claim, "bob", cid, 0)
        self.rejected(self.w.lower_claim, "bob", cid, 4)
        self.w.raise_admission("alice", cid, 2)
        self.w.lower_claim("bob", cid, 2)
        self.assertEqual(self.w.cases[cid].state, CaseState.FINISHED)

    def test_equal_positions_settle_before_funding(self):
        _, _, cid = self.case()
        self.w.concede("alice", cid, 1)
        self.w.lower_claim("bob", cid, 1)
        self.rejected(self.w.open_severity, "bob", cid, max_fee=500)
        self.assertEqual(len(self.w.disputes), 0)

    def test_silent_requester_gets_ruling_not_initial_funding_default(self):
        _, _, cid = self.case()
        merits = self.w.escalate_merits("alice", cid)
        self.finish(merits, CLAIMANT)
        severity = self.w.open_severity("bob", cid, max_fee=500)
        self.finish(severity, REQUESTER)
        self.assertEqual(self.w.cases[cid].final_rung, 0)

    def test_deadline_default_applies_admission(self):
        _, _, cid = self.case()
        self.w.concede("alice", cid, 2)
        self.rejected(self.w.close_severity_window, cid)
        self.w.mine(20)
        self.rejected(self.w.open_severity, "bob", cid, max_fee=500)
        self.w.close_severity_window(cid)
        self.assertEqual(self.w.cases[cid].final_rung, 2)

    def test_concession_host_failure_is_fully_atomic(self):
        _, key, cid = self.case()
        self.w.failed_hosts.add("host")
        self.rejected(self.w.concede, "alice", cid, 1)
        self.assertFalse(self.w.requests[key].resolved)

    def test_unfunded_concession_rolls_back(self):
        _, _, cid = self.case(secured=0)
        self.w.deposit_bond("alice", self.w.balance("wallet", "alice"))
        self.rejected(self.w.concede, "alice", cid, 1)

    def test_only_parties_may_negotiate(self):
        _, _, cid = self.case()
        self.rejected(self.w.concede, "eve", cid, 1)
        self.w.concede("alice", cid, 1)
        self.rejected(self.w.raise_admission, "eve", cid, 2)
        self.rejected(self.w.lower_claim, "eve", cid, 2)
        self.rejected(self.w.open_severity, "eve", cid, max_fee=500)


class SeverityTests(Fixture):
    def test_snapshot_is_immutable_and_domain_bound(self):
        _, key, cid, _ = self.severity()
        s = self.w.cases[cid].snapshot
        self.assertIsInstance(s, FinalOffers)
        self.assertEqual((s.domain, s.request, s.policy, s.initial_fee), (self.w.domain, key, self.p, 500))
        with self.assertRaises(FrozenInstanceError):
            s.claim = 1
        self.rejected(self.w.raise_admission, "alice", cid, 2)
        self.rejected(self.w.lower_claim, "bob", cid, 2)
        self.rejected(self.w.open_severity, "bob", cid, max_fee=500)

    def test_position_update_winning_race_is_snapshotted(self):
        _, _, cid = self.case()
        self.w.concede("alice", cid, 1)
        self.w.lower_claim("bob", cid, 3)
        self.w.open_severity("bob", cid, max_fee=500)
        self.assertEqual(self.w.cases[cid].snapshot.claim, 3)

    def test_claimant_wins_cost_bond_once(self):
        tid, key, cid, did = self.severity()
        self.finish(did, CLAIMANT)
        self.assertEqual(self.w.balance("cost", tid), 0)
        self.assertEqual(self.w.cases[cid].paid_award, 24_000)
        self.rejected(self.w.finalize, did)
        self.w.release(key)

    def test_requester_wins_returns_cost_bond(self):
        tid, key, cid, did = self.severity()
        self.finish(did, REQUESTER)
        self.assertEqual(self.w.balance("cost", tid), 500)
        self.assertEqual(self.w.cases[cid].final_rung, 1)
        self.w.release(key)
        self.assertEqual(self.w.balance("free", "alice"), 24_500 - 2400)

    def test_refusal_yields_admission_and_returns_bond(self):
        tid, key, cid, did = self.severity()
        self.finish(did, REFUSE)
        self.assertEqual(self.w.cases[cid].final_rung, 1)
        self.assertEqual(self.w.balance("cost", tid), 500)
        self.assertFalse(self.w.requests[key].registered)

    def test_fee_decrease_reimburses_actual_fee_only(self):
        tid, key, cid = self.case()
        self.w.concede("alice", cid, 1)
        self.w.set_resolver("court", "court", kind="severity", fee=200)
        did = self.w.open_severity("bob", cid, max_fee=500)
        self.finish(did, CLAIMANT)
        self.assertEqual(self.w.balance("cost", tid), 300)
        self.w.release(key)
        self.assertEqual(self.w.balance("free", "alice"), 300)

    def test_fee_increase_cannot_create_unbacked_reimbursement(self):
        tid, _, cid = self.case()
        self.w.concede("alice", cid, 1)
        self.w.set_resolver("court", "court", kind="severity", fee=700)
        self.rejected(self.w.open_severity, "bob", cid, max_fee=700)
        self.w.top_up_cost("alice", cid, 200)
        did = self.w.open_severity("bob", cid, max_fee=700)
        self.finish(did, CLAIMANT)
        self.assertEqual(self.w.balance("cost", tid), 0)

    def test_fee_slippage_limit_is_enforced(self):
        _, _, cid = self.case()
        self.w.concede("alice", cid, 1)
        self.rejected(self.w.open_severity, "bob", cid, max_fee=499)

    def test_resolver_failure_rolls_back_fee_and_snapshot(self):
        _, _, cid = self.case()
        self.w.concede("alice", cid, 1)
        self.w.set_resolver("court", "court", kind="severity", fee=500, available=False)
        self.rejected(self.w.open_severity, "bob", cid, max_fee=500)
        self.assertIsNone(self.w.cases[cid].snapshot)
        self.w.set_resolver("court", "court", kind="severity", fee=500)
        self.w.open_severity("bob", cid, max_fee=500)

    def test_policy_update_does_not_change_live_case(self):
        _, _, cid, did = self.severity()
        frozen = self.w.cases[cid].snapshot
        self.w.configure("governor", "host", replace(self.p, version="new", ladder=(0, 5000, 10000)))
        self.finish(did, CLAIMANT)
        self.assertEqual(self.w.cases[cid].snapshot, frozen)

    def test_no_cost_payment_at_provisional_ruling(self):
        tid, _, _, did = self.severity()
        self.w.publish_ruling("court", did, CLAIMANT)
        self.assertEqual(self.w.balance("cost", tid), 500)
        self.rejected(self.w.finalize, did)

    def test_zero_priced_lowest_rung(self):
        self.p = replace(self.p, version="zero", ladder=(0, 2500, 5000, 7500, 10000))
        self.w.configure("governor", "host", self.p)
        _, key, cid = self.case(secured=0, claim=0)
        self.w.concede("alice", cid, 0)
        self.assertEqual(self.w.cases[cid].paid_award, 0)
        self.w.release(key)

    def test_equal_rounded_amounts_cannot_burn_a_severity_fee(self):
        self.p = replace(self.p, version="tiny", award=2, prepayment=1, ladder=(0, 1000, 10000))
        self.w.configure("governor", "host", self.p)
        _, _, cid = self.case(claim=1)
        self.w.concede("alice", cid, 0)
        self.rejected(self.w.open_severity, "bob", cid, max_fee=500)
        self.w.mine(20)
        self.w.close_severity_window(cid)
        self.assertEqual(self.w.cases[cid].paid_award, 0)

    def test_unsecured_award_is_debt_not_cash(self):
        tid, key, cid, did = self.severity(secured=0)
        self.finish(did, CLAIMANT)
        self.assertEqual(self.w.cases[cid].debt, 21_600)
        self.assertEqual(self.w.cases[cid].paid_award, 2400)
        self.assertEqual(self.w.outstanding_debt["alice"], 21_600)
        self.assertEqual(self.w.balance("cost", tid), 0)
        self.w.release(key)
        self.w.deposit_bond("alice", 500)
        self.rejected(self.w.reserve, "alice", "host", "next", secured=0, nonce=1, expiry=1300)
        self.w.repay("carol", cid, 1600)
        self.w.repay("alice", cid, 20_000)
        self.assertEqual(self.w.outstanding_debt["alice"], 0)
        self.rejected(self.w.repay, "alice", cid, 1)
        self.w.reserve("alice", "host", "next", secured=0, nonce=1, expiry=1300)


class AppealTests(Fixture):
    def test_claimant_first_ruling_reversed_cost_bond_returns(self):
        tid, key, cid, did = self.severity()
        frozen = self.w.cases[cid].snapshot
        self.appeal_both(did, CLAIMANT)
        self.assertEqual(self.w.balance("cost", tid), 500)
        self.finish(did, REQUESTER)
        self.assertEqual(self.w.cases[cid].snapshot, frozen)
        self.assertEqual(self.w.cases[cid].final_rung, 1)
        self.assertEqual(self.w.balance("cost", tid), 500)
        self.assertEqual(self.w.balance("jurors"), 500 + 21_600)
        self.w.release(key)

    def test_requester_first_ruling_reversed_only_initial_cost_reimbursed(self):
        tid, key, cid, did = self.severity()
        self.appeal_both(did, REQUESTER)
        before = self.w.balance("credit", "bob")
        self.finish(did, CLAIMANT)
        self.assertEqual(self.w.balance("credit", "bob") - before, 21_600 + 500)
        self.assertEqual(self.w.balance("cost", tid), 0)
        self.assertEqual(self.w.cases[cid].debt, 0)
        self.w.release(key)

    def test_one_side_funding_flips_final_severity(self):
        tid, _, cid, did = self.severity()
        self.w.publish_ruling("court", did, REQUESTER)
        self.w.fund_appeal("dave", did, CLAIMANT, 64_800)
        self.w.mine(20)
        self.assertEqual(self.w.finalize(did), CLAIMANT)
        self.assertEqual(self.w.cases[cid].final_rung, 4)
        self.assertEqual(self.w.balance("cost", tid), 0)
        self.assertEqual(self.w.claim_appeal("dave", did, 0), 64_800)
        self.assertEqual(len(self.w.disputes[did].rounds), 1)

    def test_one_side_merits_funding_effective_host_outcome(self):
        _, key, cid = self.case()
        did = self.w.escalate_merits("alice", cid)
        self.w.publish_ruling("court", did, REQUESTER)
        self.w.fund_appeal("carol", did, CLAIMANT, 64_800)
        self.w.mine(20)
        self.w.finalize(did)
        self.assertEqual(self.w.requests[key].ruling, CLAIMANT)
        self.assertEqual(self.w.cases[cid].state, CaseState.NEGOTIATING)
        self.assertEqual(self.w.cases[cid].admission, 0)

    def test_partial_funding_does_not_flip_ruling(self):
        _, _, cid, did = self.severity()
        self.w.publish_ruling("court", did, REQUESTER)
        self.w.fund_appeal("carol", did, CLAIMANT, 100)
        self.w.mine(20)
        self.assertEqual(self.w.finalize(did), REQUESTER)
        self.assertEqual(self.w.claim_appeal("carol", did, 0), 100)

    def test_losing_side_only_has_first_half_window(self):
        _, _, _, did = self.severity()
        self.w.publish_ruling("court", did, CLAIMANT)
        self.w.mine(10)
        self.rejected(self.w.fund_appeal, "carol", did, REQUESTER, 64_800)
        self.w.fund_appeal("dave", did, CLAIMANT, 43_200)

    def test_excess_funding_is_not_debited(self):
        _, _, _, did = self.severity()
        self.w.publish_ruling("court", did, CLAIMANT)
        before = self.w.balance("wallet", "dave")
        self.assertEqual(self.w.fund_appeal("dave", did, CLAIMANT, 100_000), 43_200)
        self.assertEqual(before - self.w.balance("wallet", "dave"), 43_200)

    def test_refusal_round_uses_shared_multiplier(self):
        _, _, _, did = self.severity()
        self.w.publish_ruling("court", did, REFUSE)
        rd = self.w.disputes[did].rounds[0]
        self.assertEqual(rd.targets, {REQUESTER: 43_200, CLAIMANT: 43_200})
        self.w.mine(10)
        self.w.fund_appeal("carol", did, REQUESTER, 43_200)

    def test_lazy_rewards_and_double_claim(self):
        _, _, _, did = self.severity()
        self.appeal_both(did, CLAIMANT)
        self.finish(did, REQUESTER)
        self.assertEqual(self.w.claim_appeal("carol", did, 0), 86_400)
        self.assertEqual(self.w.claim_appeal("dave", did, 0), 0)
        self.rejected(self.w.claim_appeal, "carol", did, 0)

    def test_final_refusal_refunds_pro_rata_with_dust_retained(self):
        _, _, _, did = self.severity()
        self.w.publish_ruling("court", did, REQUESTER)
        self.w.fund_appeal("carol", did, REQUESTER, 1)
        self.w.fund_appeal("eve", did, REQUESTER, 43_199)
        self.w.fund_appeal("dave", did, CLAIMANT, 64_800)
        self.finish(did, REFUSE)
        paid = sum(self.w.claim_appeal(who, did, 0) for who in ("carol", "eve", "dave"))
        self.assertLessEqual(paid, 86_400)
        self.assertEqual(self.w.balance("appeal", did, 0), 86_400 - paid)
        self.assertGreater(self.w.balance("appeal", did, 0), 0)

    def test_round_bound_is_enforced_not_only_economic(self):
        self.p = replace(self.p, version="bounded", appeal_fees=(100,))
        self.w.configure("governor", "host", self.p)
        _, _, _, did = self.severity()
        self.appeal_both(did, CLAIMANT)
        self.w.publish_ruling("court", did, REQUESTER)
        self.rejected(self.w.fund_appeal, "carol", did, REQUESTER, 10_000)
        self.w.mine(20)
        self.w.finalize(did)

    def test_unauthorized_and_duplicate_rulings(self):
        _, _, _, did = self.severity()
        self.rejected(self.w.publish_ruling, "eve", did, CLAIMANT)
        self.rejected(self.w.publish_ruling, "court", did, 3)
        self.w.publish_ruling("court", did, CLAIMANT)
        self.rejected(self.w.publish_ruling, "court", did, REQUESTER)

    def test_second_funding_failure_is_atomic(self):
        _, _, _, did = self.severity()
        self.w.publish_ruling("court", did, CLAIMANT)
        self.w.fund_appeal("carol", did, REQUESTER, 64_800)
        self.w.set_resolver("court", "court", kind="severity", fee=500, available=False)
        self.rejected(self.w.fund_appeal, "dave", did, CLAIMANT, 43_200)
        self.w.set_resolver("court", "court", kind="severity", fee=500)
        self.w.fund_appeal("dave", did, CLAIMANT, 43_200)
        self.assertEqual(len(self.w.disputes[did].rounds), 2)

    def test_final_host_callback_failure_can_be_retried(self):
        _, _, cid = self.case()
        did = self.w.escalate_merits("alice", cid)
        self.w.publish_ruling("court", did, REQUESTER)
        self.w.mine(20)
        self.w.failed_hosts.add("host")
        self.rejected(self.w.finalize, did)
        self.w.failed_hosts.clear()
        self.w.finalize(did)


class MandateTests(Fixture):
    def test_one_decision_many_permissionless_executions(self):
        cases = [self.case(item=str(i))[2] for i in range(8)]
        mid, proofs = self.mandate(cases)
        for cid, proof in zip(cases, proofs):
            self.assertTrue(self.w.execute_mandate(mid, cid, proof))
        self.assertEqual(self.w.mandates[mid].used, 8)
        self.assertEqual(self.w.mandates[mid].spent, 8 * 2400)
        self.assertEqual(self.w.refund_mandate(mid), 0)

    def test_duplicate_execution_is_no_op(self):
        _, _, cid = self.case()
        mid, (proof,) = self.mandate([cid])
        self.w.execute_mandate(mid, cid, proof)
        before = deepcopy(self.w.__dict__)
        self.assertFalse(self.w.execute_mandate(mid, cid, proof))
        self.assertEqual(before, self.w.__dict__)

    def test_independent_concession_consumes_no_budget(self):
        _, _, cid = self.case()
        mid, (proof,) = self.mandate([cid])
        self.w.concede("alice", cid, 1)
        self.assertFalse(self.w.execute_mandate(mid, cid, proof))
        self.assertEqual(self.w.mandates[mid].spent, 0)

    def test_escalation_wins_race_no_budget_consumed(self):
        _, _, cid = self.case()
        mid, (proof,) = self.mandate([cid])
        self.w.escalate_merits("alice", cid)
        self.rejected(self.w.execute_mandate, mid, cid, proof)
        self.assertEqual(self.w.mandates[mid].used, 0)

    def test_mandate_wins_race_escalation_cannot_reopen_merits(self):
        _, _, cid = self.case()
        mid, (proof,) = self.mandate([cid])
        self.w.execute_mandate(mid, cid, proof)
        self.rejected(self.w.escalate_merits, "alice", cid)

    def test_host_callback_failure_does_not_consume_budget(self):
        _, _, cid = self.case()
        mid, (proof,) = self.mandate([cid])
        self.w.failed_hosts.add("host")
        self.rejected(self.w.execute_mandate, mid, cid, proof)
        self.w.failed_hosts.clear()
        self.w.execute_mandate(mid, cid, proof)

    def test_scope_does_not_include_later_related_case(self):
        _, _, cid = self.case("first")
        mid, (proof,) = self.mandate([cid])
        _, _, later = self.case("second")
        self.rejected(self.w.execute_mandate, mid, later, proof)

    def test_wrong_requester_cannot_spend_mandate(self):
        _, key = self.request("other", owner="carol")
        cid = self.w.challenge("bob", key)
        mid, (proof,) = self.mandate([cid])
        self.rejected(self.w.execute_mandate, mid, cid, proof)

    def test_case_cap_exhaustion_keeps_single_case_exit(self):
        cases = [self.case(item=str(i))[2] for i in range(2)]
        mid, proofs = self.mandate(cases, max_cases=1)
        self.w.execute_mandate(mid, cases[0], proofs[0])
        self.rejected(self.w.execute_mandate, mid, cases[1], proofs[1])
        self.w.concede("alice", cases[1], 1)
        self.assertEqual(self.w.refund_mandate(mid), 2400)

    def test_spend_cap_exhaustion_keeps_single_case_exit(self):
        cases = [self.case(item=str(i))[2] for i in range(2)]
        mid, proofs = self.mandate(cases, max_spend=2400)
        self.w.execute_mandate(mid, cases[0], proofs[0])
        self.rejected(self.w.execute_mandate, mid, cases[1], proofs[1])
        self.w.escalate_merits("alice", cases[1])

    def test_expiry_and_unused_refund_once(self):
        _, _, cid = self.case()
        mid, (proof,) = self.mandate([cid])
        self.rejected(self.w.refund_mandate, mid)
        self.w.mine(20)
        self.rejected(self.w.execute_mandate, mid, cid, proof)
        self.assertEqual(self.w.refund_mandate(mid), 2400)
        self.rejected(self.w.refund_mandate, mid)

    def test_mandate_remains_executable_after_retirement(self):
        _, _, cid = self.case()
        mid, (proof,) = self.mandate([cid])
        self.w.retire("governor")
        self.w.execute_mandate(mid, cid, proof)

    def test_lowered_claim_reduces_payment(self):
        _, _, cid = self.case()
        mid, (proof,) = self.mandate([cid], rung=4)
        self.w.lower_claim("bob", cid, 1)
        self.w.execute_mandate(mid, cid, proof)
        self.assertEqual(self.w.mandates[mid].spent, 2400)
        self.assertEqual(self.w.refund_mandate(mid), 21_600)

    def test_invalid_rung_never_silently_awards_maximum(self):
        _, _, cid = self.case()
        root, (proof,) = merkle([self.w.mandate_leaf(cid)])
        mid = self.w.authorize("alice", root, rung=20, max_cases=1, max_spend=24000,
                              expiry=1200, nonce=0)
        self.rejected(self.w.execute_mandate, mid, cid, proof)

    def test_nonce_reuse_rejected(self):
        _, _, cid = self.case()
        mid, _ = self.mandate([cid])
        m = self.w.mandates[mid]
        self.rejected(self.w.authorize, "alice", m.root, rung=1, max_cases=1,
                      max_spend=2400, expiry=1200, nonce=0)

    def test_proof_hash_domains_and_bounds(self):
        leaves = [leaf_hash("one", i, ("host", "item", i), "alice", "v1") for i in range(7)]
        root, proofs = merkle(leaves)
        self.assertTrue(all(verifies(root, x, p) for x, p in zip(leaves, proofs)))
        wrong = leaf_hash("two", 0, ("host", "item", 0), "alice", "v1")
        self.assertFalse(verifies(root, wrong, proofs[0]))
        self.assertFalse(verifies(root, leaves[0], [b"x" * 32] * 33))
        self.assertFalse(verifies(root, leaves[0], [b"x"]))


class InvariantTests(Fixture):
    def test_validation_and_uint_boundaries(self):
        for value in (-1, True, 1.5, MAX_UINT + 1):
            with self.subTest(value=value):
                self.rejected(self.w.deposit_bond, "alice", value)
        self.rejected(self.w.mint, "alice", MAX_UINT)
        for ladder in ((0,), (1000, 1000), (1000, 900), (0, 11000)):
            with self.subTest(ladder=ladder), self.assertRaises(Rejected):
                Policy("invalid", ladder=ladder)

    def test_same_version_cannot_change_terms(self):
        self.rejected(self.w.configure, "governor", "host", replace(self.p, award=35_000))
        self.rejected(self.w.configure, "eve", "host", self.p)

    def test_self_concession_cannot_mint_money(self):
        self.w.deposit_bond("alice", 24_500)
        self.w.reserve("alice", "host", "x", secured=24_000, nonce=0, expiry=1200)
        self.w.mine()
        key = self.w.host_submit("alice", "host", "x")
        cid = self.w.challenge("alice", key)
        self.w.concede("alice", cid, 4)
        self.w.release(key)
        self.w.withdraw_bond("alice", 500)
        self.w.claim_credit("alice", "alice")
        self.assertEqual(self.w.balance("wallet", "alice"), 10_000_000)
        self.assertEqual(self.w.balance("jurors"), 0)

    def test_two_wallet_merits_cycle_burns_only_fee(self):
        _, key, cid = self.case()
        did = self.w.escalate_merits("alice", cid)
        self.finish(did, CLAIMANT)
        self.w.lower_claim("bob", cid, 0)
        self.w.release(key)
        for who in ("alice", "bob"):
            self.w.withdraw_bond(who, self.w.balance("free", who))
            self.w.claim_credit(who, who)
        self.assertEqual(self.w.balance("wallet", "alice") + self.w.balance("wallet", "bob"), 20_000_000 - 500)

    def test_reverting_credit_recipient_never_blocks_settlement(self):
        _, key, cid = self.case(claim=1)
        self.w.rejecting_receivers.add("bob")
        self.w.concede("alice", cid, 1)
        self.w.release(key)
        self.rejected(self.w.claim_credit, "bob", "bob")
        value = self.w.balance("credit", "bob")
        self.assertEqual(self.w.claim_credit("bob", "carol"), value)

    def test_rounding_conserves_cash_for_every_ladder_rung(self):
        self.p = replace(self.p, version="rounding", award=101, prepayment=3, severity_cap=1, merits_fee=1)
        self.w.configure("governor", "host", self.p)
        for rung in range(len(self.p.ladder)):
            with self.subTest(rung=rung):
                _, key, cid = self.case(item=str(rung), claim=rung)
                self.w.concede("alice", cid, rung)
                self.w.release(key)
                self.assertEqual(self.w.cases[cid].paid_award, 98 * self.p.ladder[rung] // 10_000)
                self.w.check()

    def test_merits_fee_drift_is_explicit_not_silent_subsidy(self):
        _, _, cid = self.case()
        self.w.set_resolver("court", "court", kind="merits", fee=700)
        self.rejected(self.w.escalate_merits, "alice", cid)

    def test_seeded_lifecycles_preserve_all_invariants(self):
        rng = random.Random(501)
        for i in range(40):
            secured = rng.choice((0, 10_000, 24_000))
            # Independent identities prevent intentional defaults blocking later unsecured tickets.
            owner = f"publisher-{i}"
            self.w.mint(owner, 1_000_000)
            _, key = self.request(item=str(i), secured=secured, owner=owner)
            claim = rng.randrange(5)
            cid = self.w.challenge("bob", key, claim=claim)
            admission = rng.randrange(claim + 1)
            self.w.concede(owner, cid, admission)
            if admission != claim:
                if rng.choice((True, False)):
                    did = self.w.open_severity("bob", cid, max_fee=500)
                    self.finish(did, rng.choice((REFUSE, REQUESTER, CLAIMANT)))
                else:
                    self.w.mine(20)
                    self.w.close_severity_window(cid)
            self.w.release(key)
            if self.w.cases[cid].debt and rng.choice((True, False)):
                self.w.repay(owner, cid, self.w.cases[cid].debt)
            self.w.check()


if __name__ == "__main__":
    unittest.main()

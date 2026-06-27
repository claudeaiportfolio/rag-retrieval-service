"""Pure-logic tests for the fusion + freshness math (no DB)."""

from datetime import UTC, datetime, timedelta

import pytest

from common.retrieval import _freshness_boost, rrf_fuse


def test_rrf_fuse_rewards_agreement_across_retrievers():
    vec = [1, 2, 3]
    bm25 = [1, 4, 5]
    scores = rrf_fuse([vec, bm25], rrf_k=60)
    # doc 1 is rank-0 in both lists, so it must win.
    assert max(scores, key=scores.__getitem__) == 1
    assert scores[1] == pytest.approx(1 / 60 + 1 / 60)
    # doc 2 appears only in the vector list at rank 1.
    assert scores[2] == pytest.approx(1 / 61)


def test_rrf_fuse_single_list_preserves_order():
    scores = rrf_fuse([[7, 8, 9]], rrf_k=60)
    assert scores[7] > scores[8] > scores[9]


def test_freshness_boost_decays_caps_and_disables():
    now = datetime(2026, 6, 27, tzinfo=UTC)
    fresh = _freshness_boost(now, half_life_days=7, now=now)
    old = _freshness_boost(now - timedelta(days=14), half_life_days=7, now=now)
    assert fresh > old > 0
    # capped below one RRF rank-step so it only breaks near-ties.
    assert fresh < 1 / 60
    # disabled paths return exactly zero.
    assert _freshness_boost(now, half_life_days=0, now=now) == 0.0
    assert _freshness_boost(None, half_life_days=7, now=now) == 0.0

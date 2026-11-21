# Feature: pawleen-photo-booth, Property 2: Only returned images are counted
"""**Validates: Requirements 3.8, 3.9, 4.12, 4.14, 6.13, 10.17, 12.5**"""
from hypothesis import HealthCheck, given, settings as hsettings, strategies as st

from app.errors import PawleenError
from app.events import ErrorEvent, ResultEvent, parse_sse
from app.models import GatekeeperDecision
from tests.conftest import HANG, fake_png, failing_check, passing_check
from tests.conftest import FakeCostumeMaker, FakeGatekeeper, FakeQualityChecker
from tests.test_routes_summon import make_client, remaining, summon

PBT = hsettings(max_examples=100, deadline=None, suppress_health_check=list(HealthCheck))

gatekeeper_outcomes = st.sampled_from(
    [
        GatekeeperDecision(accepted=True),
        GatekeeperDecision(False, "no_animal"),
        GatekeeperDecision(False, "bad_costume"),
        RuntimeError("boom"),
        PawleenError("credits_depleted"),
        HANG,
    ]
)
maker_outcomes = st.sampled_from(
    [
        fake_png(b"a"),
        fake_png(b"b"),
        RuntimeError("boom"),
        PawleenError("credits_depleted"),
        PawleenError("refused"),
        HANG,
    ]
)
checker_outcomes = st.sampled_from(
    [
        passing_check(),
        failing_check("bad", passed=2),
        failing_check("worse", passed=0),
        RuntimeError("boom"),
        HANG,
    ]
)


def script(outcomes):
    return st.lists(outcomes, min_size=1, max_size=3)


@PBT
@given(
    gatekeeper=script(gatekeeper_outcomes),
    maker=script(maker_outcomes),
    checker=script(checker_outcomes),
    pipeline_timeout=st.sampled_from([0.04, 0.5]),
)
def test_usage_increases_by_one_iff_image_returned(
    gatekeeper, maker, checker, pipeline_timeout
):
    client, app = make_client(
        gatekeeper=FakeGatekeeper(*gatekeeper),
        maker=FakeCostumeMaker(*maker),
        checker=FakeQualityChecker(*checker),
        gatekeeper_timeout=0.02,
        maker_timeout=0.02,
        checker_timeout=0.02,
        pipeline_timeout=pipeline_timeout,
    )
    before = remaining(client)
    r = summon(client)
    assert r.status_code == 200
    events = parse_sse(r.text)
    results = [e for e in events if isinstance(e, ResultEvent)]
    errors = [e for e in events if isinstance(e, ErrorEvent)]

    # Exactly one terminal event.
    assert len(results) + len(errors) == 1

    delta = before - remaining(client)
    assert delta == (1 if results else 0)
    assert app.state.usage._global == (1 if results else 0)
    if results:
        assert results[0].remaining == before - 1
        assert results[0].image_b64

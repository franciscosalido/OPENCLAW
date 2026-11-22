"""Oráculos do leitor de eventos sintéticos."""
from pathlib import Path

import pytest

from backend.derivatives.ticket.replay import ReplayError, load_replay

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures/derivatives/synthetic/ticket/replay.json"


def test_gap_is_observable_and_times_are_aware() -> None:
    """A sequência 1, 2, 4 conserva todos os eventos."""
    replay = load_replay(FIXTURE)
    assert [e.gap_before for e in replay.events] == [False, False, True]
    assert replay.session_close.utcoffset() is not None


@pytest.mark.parametrize(("old", "new"), [
    ('"0.95"', '0.95'), ('"0.95"', '"0.955"'), ('"0.95"', '"0"'), ('"0.95"', '"-1"'),
    ('"1.02"', 'null'),
    ('"bid_size":50', '"bid_size":-1'), ('"0.95"', 'null'),
    ('14:00:01Z', '13:59:59Z'), ('14:00:01Z', '14:00:01'), ('"seq":4', '"seq":2'),
    ('"seq":4', '"seq":1'), ('"seq":4', '"seq":4,"extra":1'),
    ('"timeout"', '"bad"'), ('"seq":4', '"seq":3,"seq":4'),
    ('"seq":4', '"gap_before":false,"seq":4'), ('"size":100', '"size":-1'),
])
def test_invalid_fixture(tmp_path: Path, old: str, new: str) -> None:
    """Cada violação individual recusa o replay."""
    path = tmp_path / "bad.json"
    path.write_text(FIXTURE.read_text().replace(old, new))
    with pytest.raises(ReplayError):
        load_replay(path)

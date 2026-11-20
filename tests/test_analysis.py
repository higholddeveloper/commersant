import pytest

from core import storage
from core.analysis import analyze
from core.engine import Game
from core.models import GameStatus

SIGMA = 0.03


def line(*segments):
    """Кусочно-линейная история: (кол-во шагов, конечное значение) ..."""
    out = [segments[0][1]]
    for steps, end in segments[1:]:
        start = out[-1]
        out += [start + (end - start) * i / steps for i in range(1, steps + 1)]
    return out


def test_decline():
    assert analyze(line((0, 100), (21, 60)), SIGMA).key == "decline"


def test_rebound_after_decline():
    assert analyze(line((0, 100), (12, 60), (8, 75)), SIGMA).key == "rebound"


def test_steady_growth():
    assert analyze(line((0, 100), (21, 130)), SIGMA).key == "growth"


def test_peak_after_sharp_jump():
    t = analyze(line((0, 100), (15, 100), (5, 135)), SIGMA)
    assert t.key == "peak" and t.tone == 1


def test_flat():
    hist = [100 + (0.5 if i % 2 else -0.5) for i in range(21)]
    assert analyze(hist, SIGMA).key == "flat"


def test_not_enough_data():
    assert analyze([100, 101, 102], SIGMA).key == "new"


def test_has_text_for_every_result():
    for hist in (line((0, 100), (21, 60)), line((0, 100), (21, 130)), [100] * 21):
        t = analyze(hist, SIGMA)
        assert t.title and t.hint


# ---- средняя цена покупки ----
def test_avg_cost_tracks_buys_and_sells():
    g = Game(seed=1)
    g.buy("OIL", 10)
    first = g.avg_cost("OIL")
    assert first == pytest.approx(70 * 1.01)
    g.state.prices["OIL"] = 90.0
    g.buy("OIL", 10)
    assert g.avg_cost("OIL") == pytest.approx((70 * 1.01 + 90 * 1.01) / 2)
    avg = g.avg_cost("OIL")
    g.sell("OIL", 10)
    assert g.avg_cost("OIL") == pytest.approx(avg)   # продажа не меняет среднюю цену остатка
    g.sell("OIL", 10)
    assert g.avg_cost("OIL") == 0 and g.state.cost_basis["OIL"] == 0


# ---- важные события / настройки ----
def test_report_important_on_event():
    g = Game(seed=1)
    seen = {True: 0, False: 0}
    while g.state.status is GameStatus.PLAYING:
        r = g.next_turn()
        seen[r.important] += 1
        if not r.all_events and r.status is GameStatus.PLAYING and r.penalty == 0:
            assert r.important is False
    assert seen[True] > 0 and seen[False] > 0


def test_settings_roundtrip_and_defaults(tmp_path):
    path = tmp_path / "settings.json"
    assert storage.load_settings(path) == storage.DEFAULT_SETTINGS
    storage.save_settings({"realtime": True, "speed": 5.0, "period": 60, "last_name": "Аня"}, path)
    assert storage.load_settings(path) == {"realtime": True, "speed": 5.0, "period": 60, "last_name": "Аня"}
    path.write_text("{broken", encoding="utf-8")
    assert storage.load_settings(path) == storage.DEFAULT_SETTINGS


def test_old_save_without_cost_basis_loads(tmp_path):
    g = Game(seed=3)
    d = storage.state_to_dict(g.state)
    del d["state"]["cost_basis"]
    assert storage.state_from_dict(d).cost_basis == {}

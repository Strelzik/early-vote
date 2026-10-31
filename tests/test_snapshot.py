from datetime import datetime

from earlyvote import snapshot


def test_save_writes_only_new_content(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot, "SNAPSHOTS", tmp_path)
    t1, t2 = datetime(2026, 10, 20, 9, 0), datetime(2026, 10, 20, 19, 30)

    first = snapshot.save("uf", "US.csv", b"a,b\n1,2\n", t1)
    assert snapshot.save("uf", "US.csv", b"a,b\n1,2\n", t2) is None
    second = snapshot.save("uf", "US.csv", b"a,b\n1,3\n", t2)

    files = sorted(p.name for p in (tmp_path / "uf" / "US.csv").iterdir())
    assert files == [first.name, second.name]
    assert first.name.startswith("20261020T0900_") and second.name.startswith("20261020T1930_")


def test_save_ignores_empty_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot, "SNAPSHOTS", tmp_path)
    t = datetime(2026, 10, 30, 14, 10)

    assert snapshot.save("uf", "HI_county.csv", b"", t) is None
    assert snapshot.save("uf", "HI_county.csv", b"\r\n", t) is None
    assert not (tmp_path / "uf").exists()

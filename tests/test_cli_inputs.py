import pytest
from mini.cli import _resolve_inputs

def test_resolve_inputs_expands_directory_and_glob(tmp_path):
    mp4 = tmp_path / "clipA.mp4"
    mov = tmp_path / "clipB.mov"
    mkv = tmp_path / "clipC.mkv"
    for path in (mp4, mov, mkv):
        path.write_bytes(b"test")

    files_from_dir = _resolve_inputs([str(tmp_path)])
    assert [p.name for p in files_from_dir] == ["clipA.mp4", "clipB.mov", "clipC.mkv"]

    files_from_glob = _resolve_inputs([str(tmp_path / "*.mp4")])
    assert [p.name for p in files_from_glob] == ["clipA.mp4"]


def test_resolve_inputs_raises_on_empty(tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(ValueError):
        _resolve_inputs([str(empty_dir)])

from metaclass_registry.cache import get_cache_file_path


def test_cache_projection_uses_normal_owner_without_creating(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "isolated"))
    projected = get_cache_file_path("declared.json", create=False)
    assert not projected.parent.exists()
    assert get_cache_file_path("declared.json") == projected
    assert projected.parent.is_dir()

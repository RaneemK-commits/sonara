import pytest

from sonara import config


def test_local_overrides_preserve_defaults_and_explicit_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    base = tmp_path / "config/sonara.toml"
    base.write_text('bed_id="BED-01"\n[audio]\ndevice=""\nsample_rate=16000\n', encoding="utf-8")
    (tmp_path / "config/intents.toml").write_text('', encoding="utf-8")
    assert config.load_config().section("audio")["device"] == ""
    local = tmp_path / "data/local.toml"
    local.write_text('bed_id="BED-02"\n[audio]\ndevice="test-mic"\n', encoding="utf-8")
    cfg = config.load_config()
    assert cfg.bed_id == "BED-02"
    assert cfg.section("audio") == {"device": "test-mic", "sample_rate": 16000}
    assert config.load_config(base).section("audio")["device"] == ""
    local.write_text('invalid = [', encoding="utf-8")
    with pytest.raises(config.tomllib.TOMLDecodeError):
        config.load_config()  # Never silently fall back to the default token/mic.

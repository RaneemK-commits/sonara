"""Load config/sonara.toml and config/intents.toml into simple dataclasses."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Intent:
    id: str
    label: str
    speak: str
    notify: bool = True
    control: bool = False


@dataclass
class Config:
    raw: dict
    intents: list[Intent]
    prompts: dict[str, str]
    root: Path = field(default=ROOT)

    def section(self, name: str) -> dict:
        return self.raw.get(name, {})

    @property
    def bed_id(self) -> str:
        return self.raw.get("bed_id", "BED-01")

    def path(self, rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else self.root / p

    def intent(self, intent_id: str) -> Intent | None:
        return next((i for i in self.intents if i.id == intent_id), None)

    @property
    def request_intents(self) -> list[Intent]:
        return [i for i in self.intents if not i.control]


def load_config(config_path: str | Path | None = None,
                intents_path: str | Path | None = None) -> Config:
    config_path = Path(config_path) if config_path else ROOT / "config" / "sonara.toml"
    intents_path = Path(intents_path) if intents_path else ROOT / "config" / "intents.toml"
    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    idata = tomllib.loads(intents_path.read_text(encoding="utf-8"))
    intents = [Intent(**i) for i in idata.get("intent", [])]
    return Config(raw=raw, intents=intents, prompts=dict(idata.get("prompts", {})))

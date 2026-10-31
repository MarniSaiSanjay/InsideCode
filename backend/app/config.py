import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIB = 1024 * 1024


@dataclass(frozen=True)
class Limits:
    max_zip_bytes: int = 20 * MIB
    max_expanded_bytes: int = 100 * MIB
    max_entries: int = 10_000
    max_files: int = 1_000
    max_file_bytes: int = 256 * 1024
    import_seconds: int = 120


@dataclass(frozen=True)
class Settings:
    state_dir: Path
    ai_key: str = ""
    ai_model: str = ""
    ai_base_url: str = "https://api.featherless.ai/v1"
    ui_dir: Path = ROOT / "frontend" / "dist"  # built UI, served when present
    limits: Limits = field(default_factory=Limits)

    @property
    def ai_configured(self) -> bool:
        return bool(self.ai_key and self.ai_model)


def load_settings() -> Settings:
    env = os.environ
    return Settings(
        state_dir=Path(env.get("INSIDECODE_STATE_DIR", ROOT / ".insidecode")),
        ai_key=env.get("FEATHERLESS_API_KEY", ""),
        ai_model=env.get("FEATHERLESS_MODEL", ""),
        ai_base_url=env.get("FEATHERLESS_BASE_URL", Settings.ai_base_url),
    )

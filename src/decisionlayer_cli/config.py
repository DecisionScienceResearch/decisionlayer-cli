"""Archwares™ API key profiles and base URL resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from platformdirs import user_config_dir

from .errors import ConfigError


ENV_KEYS = {
    "default": "DECISIONLAYER_API_KEY",
    "claimant": "DECISIONLAYER_API_KEY_CLAIMANT",
    "respondent": "DECISIONLAYER_API_KEY_RESPONDENT",
}
ENV_KEY_ALIASES = {
    "claimant": "DECISIONLAYER_CLAIMANT_API_KEY",
    "respondent": "DECISIONLAYER_RESPONDENT_API_KEY",
}


def _load_dotenv() -> None:
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(Path.cwd() / ".env.local", override=True)


def config_path() -> Path:
    override = os.environ.get("DECISIONLAYER_CONFIG")
    if override:
        path = Path(override).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    directory = Path(user_config_dir("decisionlayer", "decisionlayer"))
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "config.toml"


def _parse_stored(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def read_stored() -> dict[str, str]:
    path = config_path()
    if not path.exists():
        return {}
    return _parse_stored(path.read_text(encoding="utf-8"))


def write_stored(values: dict[str, str]) -> Path:
    path = config_path()
    lines = ["# DecisionLayer CLI config. Do not commit this file.", ""]
    for key, value in values.items():
        lines.append(f"{key} = {value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@dataclass
class Settings:
    base_url: str = "https://www.decisionlayer.ai"
    default_profile: str = "default"
    profiles: dict[str, str] = field(default_factory=dict)

    def api_key(self, profile: str) -> str | None:
        if profile in self.profiles and self.profiles[profile]:
            return self.profiles[profile]
        if profile != "default" and self.profiles.get("default"):
            return self.profiles["default"]
        return None

    def require_api_key(self, profile: str) -> str:
        key = self.api_key(profile)
        if not key:
            env_name = ENV_KEYS.get(profile, "DECISIONLAYER_API_KEY")
            raise ConfigError(
                f"No API key for profile {profile!r}. Run "
                f"`dl config set-key --profile {profile}` or set {env_name}."
            )
        return key


def load_settings(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    profile: str | None = None,
) -> Settings:
    _load_dotenv()
    stored = read_stored()
    resolved_base = (
        base_url
        or os.environ.get("DECISIONLAYER_BASE_URL")
        or stored.get("base_url")
        or "https://www.decisionlayer.ai"
    ).rstrip("/")
    profiles: dict[str, str] = {}
    for name, env_name in ENV_KEYS.items():
        alias = ENV_KEY_ALIASES.get(name)
        value = (
            os.environ.get(env_name)
            or (os.environ.get(alias) if alias else None)
            or stored.get(f"api_key_{name}")
            or ""
        )
        if value:
            profiles[name] = value
    if "default" not in profiles and os.environ.get("DECISIONLAYER_API_KEY"):
        profiles["default"] = os.environ["DECISIONLAYER_API_KEY"]
    if api_key:
        target = profile or "default"
        profiles[target] = api_key
    return Settings(base_url=resolved_base, default_profile=profile or "default", profiles=profiles)


def save_api_key(profile: str, api_key: str, base_url: str | None = None) -> Path:
    values = read_stored()
    values[f"api_key_{profile}"] = api_key.strip()
    if base_url:
        values["base_url"] = base_url.rstrip("/")
    return write_stored(values)


def save_base_url(url: str) -> Path:
    values = read_stored()
    values["base_url"] = url.rstrip("/")
    return write_stored(values)

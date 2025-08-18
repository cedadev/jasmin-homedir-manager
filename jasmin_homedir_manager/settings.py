import pathlib

import pydantic
import pydantic_settings


class DataEndpoints(pydantic.BaseModel):
    users: str


class Settings(pydantic_settings.BaseSettings):
    model_config = pydantic_settings.SettingsConfigDict(extra="forbid")

    client_id: str
    client_secret: str
    scopes: list[str]
    token_endpoint: str
    home_dir_folder: pathlib.Path
    data_endpoints: DataEndpoints

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[pydantic_settings.BaseSettings],
        init_settings: pydantic_settings.PydanticBaseSettingsSource,
        env_settings: pydantic_settings.PydanticBaseSettingsSource,
        dotenv_settings: pydantic_settings.PydanticBaseSettingsSource,
        file_secret_settings: pydantic_settings.PydanticBaseSettingsSource,
    ) -> tuple[pydantic_settings.PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            pydantic_settings.TomlConfigSettingsSource(
                settings_cls, toml_file="settings.toml"
            ),
        )

    @classmethod
    def from_toml(cls, toml_file: str | pathlib.Path) -> "Settings":
        """Load settings from a specific TOML file."""

        class _SettingsFromToml(cls):
            @classmethod
            def settings_customise_sources(
                cls,
                settings_cls: type[pydantic_settings.BaseSettings],
                init_settings: pydantic_settings.PydanticBaseSettingsSource,
                env_settings: pydantic_settings.PydanticBaseSettingsSource,
                dotenv_settings: pydantic_settings.PydanticBaseSettingsSource,
                file_secret_settings: pydantic_settings.PydanticBaseSettingsSource,
            ) -> tuple[pydantic_settings.PydanticBaseSettingsSource, ...]:
                return (
                    init_settings,
                    pydantic_settings.TomlConfigSettingsSource(
                        settings_cls, toml_file=toml_file
                    ),
                )

        return _SettingsFromToml()

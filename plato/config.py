import os
from dataclasses import dataclass, field


@dataclass
class PlatoSettings:
    base_url: str = field(
        default_factory=lambda: os.getenv(
            "PLATO_API_BASE_URL", "https://clinic.platomedical.com/api"
        )
    )
    token: str = field(default_factory=lambda: os.getenv("PLATO_API_TOKEN", ""))
    db_name: str = field(default_factory=lambda: os.getenv("PLATO_DB_NAME", "zolin"))


settings = PlatoSettings()

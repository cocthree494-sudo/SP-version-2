"""Register every application ORM mapping in standalone processes.

API route imports happen to load the domain models, but workers and maintenance
commands have narrower import graphs. Import this module at those process
boundaries before SQLAlchemy first configures its mappers.
"""

from app.domains.auth import models as _auth_models
from app.domains.bots import models as _bot_models
from app.domains.channels import models as _channel_models
from app.domains.chat import models as _chat_models
from app.domains.knowledge import models as _knowledge_models
from app.domains.provider_access import models as _provider_access_models
from app.domains.tenancy import models as _tenancy_models
from app.domains.usage import models as _usage_models
from app.domains.voice import models as _voice_models

_REGISTERED_MODULES = (
    _auth_models,
    _bot_models,
    _chat_models,
    _channel_models,
    _knowledge_models,
    _provider_access_models,
    _tenancy_models,
    _usage_models,
    _voice_models,
)


def register_model_mappings() -> None:
    """Provide an explicit, testable worker/bootstrap registration hook."""

    if len(_REGISTERED_MODULES) != 9:  # pragma: no cover - import invariant
        raise RuntimeError("Application ORM model registry is incomplete")


__all__ = ["register_model_mappings"]

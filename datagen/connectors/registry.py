"""
Connector plugin registry.

Discovers, registers, and instantiates connectors. Supports both
built-in connectors and third-party plugins via entry points.
"""

from __future__ import annotations

import importlib
import logging
from typing import Type

from datagen.connectors.base import BaseConnector, ConnectionConfig

logger = logging.getLogger(__name__)

# Global registry
_CONNECTORS: dict[str, Type[BaseConnector]] = {}


def register_connector(connector_class: Type[BaseConnector]) -> Type[BaseConnector]:
    """Register a connector class. Can be used as a decorator."""
    name = connector_class.CONNECTOR_TYPE
    _CONNECTORS[name] = connector_class
    logger.debug(f"Registered connector: {name} ({connector_class.DISPLAY_NAME})")
    return connector_class


def get_connector_class(connector_type: str) -> Type[BaseConnector] | None:
    """Get a registered connector class by type name."""
    return _CONNECTORS.get(connector_type)


def create_connector(config: ConnectionConfig) -> BaseConnector:
    """Create a connector instance from a connection config."""
    cls = get_connector_class(config.connector_type)
    if cls is None:
        raise ValueError(
            f"Unknown connector type: '{config.connector_type}'. "
            f"Available: {list(_CONNECTORS.keys())}"
        )
    return cls(config)


def list_connectors() -> list[dict]:
    """List all registered connectors with metadata."""
    return [
        {
            "type": cls.CONNECTOR_TYPE,
            "name": cls.DISPLAY_NAME,
            "category": cls.CATEGORY,
            "auth_methods": [m.value for m in cls.SUPPORTED_AUTH],
        }
        for cls in _CONNECTORS.values()
    ]


def discover_plugins():
    """Discover and load connector plugins from entry points and built-in modules."""
    # Load built-in connectors
    builtin_modules = [
        "datagen.connectors.postgres",
        "datagen.connectors.mongodb",
        "datagen.connectors.elasticsearch",
        "datagen.connectors.prometheus",
        "datagen.connectors.servicenow",
        "datagen.connectors.kafka",
        "datagen.connectors.aws_s3",
        "datagen.connectors.aws_dynamodb",
    ]

    for module_name in builtin_modules:
        try:
            importlib.import_module(module_name)
        except ImportError as e:
            logger.debug(f"Optional connector {module_name} not available: {e}")

    # Discover third-party plugins via entry points (Python 3.10+)
    try:
        from importlib.metadata import entry_points
        eps = entry_points()
        datagen_eps = eps.get("datagen.connectors", [])
        if hasattr(eps, 'select'):
            datagen_eps = eps.select(group="datagen.connectors")
        for ep in datagen_eps:
            try:
                connector_class = ep.load()
                register_connector(connector_class)
                logger.info(f"Loaded plugin connector: {ep.name}")
            except Exception as e:
                logger.warning(f"Failed to load plugin {ep.name}: {e}")
    except Exception:
        pass

    logger.info(f"Loaded {len(_CONNECTORS)} connectors: {list(_CONNECTORS.keys())}")


# Auto-discover on import
discover_plugins()

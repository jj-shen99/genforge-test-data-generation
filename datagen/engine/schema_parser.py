"""
JSON Schema parser with x-datagen extension support.

Parses JSON Schema draft 2020-12 documents, resolves $ref pointers,
and generates synthetic records using the appropriate generators.
"""

from __future__ import annotations

import copy
import json
import random
from pathlib import Path
from typing import Any

from datagen.engine.generators import (
    get_generator,
    weighted_choice,
    FAKER_PROVIDERS,
)


class SchemaParser:
    """Parses and resolves a JSON Schema document for generation."""

    def __init__(self, schema: dict | str | Path):
        if isinstance(schema, (str, Path)):
            path = Path(schema)
            if path.exists():
                with open(path) as f:
                    self.root = json.load(f)
            else:
                self.root = json.loads(str(schema))
        else:
            self.root = copy.deepcopy(schema)

        self._defs = self.root.get("$defs", self.root.get("definitions", {}))
        self._generated_ids: dict[str, list] = {}  # For x-datagen-ref tracking
        self._unique_sets: dict[str, set] = {}  # For x-datagen-unique tracking

    def resolve_ref(self, ref: str) -> dict:
        """Resolve a $ref pointer within the schema."""
        if ref.startswith("#/$defs/") or ref.startswith("#/definitions/"):
            parts = ref.split("/")
            name = parts[-1]
            return self._defs.get(name, {})
        return {}

    def resolve_schema(self, schema: dict) -> dict:
        """Recursively resolve $ref, allOf, oneOf, anyOf."""
        if "$ref" in schema:
            resolved = self.resolve_ref(schema["$ref"])
            merged = {**resolved, **{k: v for k, v in schema.items() if k != "$ref"}}
            return self.resolve_schema(merged)

        if "allOf" in schema:
            merged = {}
            for sub in schema["allOf"]:
                resolved = self.resolve_schema(sub)
                merged = _deep_merge(merged, resolved)
            rest = {k: v for k, v in schema.items() if k != "allOf"}
            return _deep_merge(merged, rest)

        if "oneOf" in schema:
            weights = schema.get("x-datagen-weight")
            chosen = weighted_choice(schema["oneOf"], weights)
            return self.resolve_schema(chosen)

        if "anyOf" in schema:
            weights = schema.get("x-datagen-weight")
            chosen = weighted_choice(schema["anyOf"], weights)
            return self.resolve_schema(chosen)

        return schema

    def generate(self, count: int = 1, context: dict | None = None) -> list[dict]:
        """Generate `count` records from the root schema."""
        self._unique_sets.clear()
        results = []
        for i in range(count):
            ctx = {**(context or {}), "_index": i, "_total": count, "_parser": self}
            record = generate_record(self.root, ctx)
            results.append(record)
        return results

    def register_generated_id(self, schema_ref: str, value: Any):
        """Track a generated ID for cross-schema foreign key references."""
        self._generated_ids.setdefault(schema_ref, []).append(value)

    def get_reference_values(self, ref: str) -> list:
        """Get previously generated values for a reference."""
        return self._generated_ids.get(ref, [])

    def check_unique(self, field_path: str, value: Any) -> bool:
        """Check if a value is unique for a given field path."""
        s = self._unique_sets.setdefault(field_path, set())
        key = str(value)
        if key in s:
            return False
        s.add(key)
        return True


def generate_record(schema: dict, context: dict | None = None) -> dict:
    """Generate a single record from an object schema."""
    parser: SchemaParser | None = (context or {}).get("_parser")
    if parser:
        schema = parser.resolve_schema(schema)

    if schema.get("type") != "object" and "properties" not in schema:
        return generate_value(schema, context)

    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    result = {}

    # First pass: generate non-dependent fields
    dependent_fields = []
    for field_name, field_schema in properties.items():
        if parser:
            field_schema = parser.resolve_schema(field_schema)

        if "x-datagen-depends-on" in field_schema:
            dependent_fields.append((field_name, field_schema))
            continue

        # Check null rate
        null_rate = field_schema.get("x-datagen-null-rate", 0)
        if null_rate > 0 and field_name not in required and random.random() < null_rate:
            result[field_name] = None
            continue

        value = _generate_field(field_name, field_schema, context, parser)
        result[field_name] = value

    # Date-pair post-processing: ensure start < end for x-datagen-date-pair fields
    date_pairs = {}
    for field_name, field_schema in properties.items():
        pair_role = field_schema.get("x-datagen-date-pair")
        if pair_role and field_name in result:
            date_pairs[pair_role] = field_name
    if "start" in date_pairs and "end" in date_pairs:
        s_key, e_key = date_pairs["start"], date_pairs["end"]
        s_val, e_val = result.get(s_key, ""), result.get(e_key, "")
        if s_val and e_val and s_val > e_val:
            result[s_key], result[e_key] = e_val, s_val

    # Second pass: generate dependent fields
    for field_name, field_schema in dependent_fields:
        dep = field_schema["x-datagen-depends-on"]
        dep_field = dep.get("field")
        dep_value = str(result.get(dep_field, ""))

        rules = dep.get("rules", {})
        if dep_value in rules:
            rule = rules[dep_value]
            override = {**field_schema, **rule}
            override.pop("x-datagen-depends-on", None)
            value = generate_value(override, context)
        else:
            # Default generation without dependency
            override = {k: v for k, v in field_schema.items() if k != "x-datagen-depends-on"}
            value = generate_value(override, context)

        result[field_name] = value

    return result


def generate_value(schema: dict, context: dict | None = None) -> Any:
    """Generate a single value from any schema definition."""
    parser: SchemaParser | None = (context or {}).get("_parser")
    if parser:
        schema = parser.resolve_schema(schema)

    # Handle x-datagen-ref (foreign key reference)
    ref = schema.get("x-datagen-ref")
    if ref and parser:
        values = parser.get_reference_values(ref)
        if values:
            return random.choice(values)

    # Handle const
    if "const" in schema:
        return schema["const"]

    # Handle enum
    if "enum" in schema:
        weights = schema.get("x-datagen-weight")
        return weighted_choice(schema["enum"], weights)

    # Handle x-datagen-faker
    faker_key = schema.get("x-datagen-faker")
    if faker_key and faker_key in FAKER_PROVIDERS:
        return FAKER_PROVIDERS[faker_key]()

    # Determine type
    schema_type = schema.get("type", "string")
    if isinstance(schema_type, list):
        # Multiple types — pick one (exclude null unless x-datagen-null-rate)
        types = [t for t in schema_type if t != "null"]
        schema_type = random.choice(types) if types else "null"

    schema_format = schema.get("format")

    generator = get_generator(schema_type, schema_format)
    if generator:
        return generator(schema, context)

    # Fallback
    return None


def _generate_field(
    field_name: str,
    field_schema: dict,
    context: dict | None,
    parser: SchemaParser | None,
) -> Any:
    """Generate a value for a named field, handling uniqueness and ID tracking."""
    is_unique = field_schema.get("x-datagen-unique", False)
    max_attempts = 100

    for attempt in range(max_attempts):
        value = generate_value(field_schema, context)

        if is_unique and parser:
            if parser.check_unique(field_name, value):
                break
            if attempt == max_attempts - 1:
                # Force uniqueness with suffix
                value = f"{value}_{context.get('_index', attempt)}"
                break
        else:
            break

    # Track generated IDs for foreign key references
    ref_track = field_schema.get("x-datagen-track-as")
    if ref_track and parser:
        parser.register_generated_id(ref_track, value)

    return value


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries."""
    result = {**base}
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_schema(path: str | Path) -> SchemaParser:
    """Convenience function to load a schema from file."""
    return SchemaParser(path)

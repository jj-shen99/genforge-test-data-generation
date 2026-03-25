"""
Multi-schema generation pipeline with cross-schema relationships.

Manages the dependency graph between schemas and ensures referential
integrity when generating linked datasets (e.g., ServiceNow incidents
referencing CMDB CIs and users).
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from datagen.engine.schema_parser import SchemaParser


@dataclass
class SchemaNode:
    """A schema in the dependency graph."""
    name: str
    schema: dict
    count: int = 100
    depends_on: list[str] = field(default_factory=list)
    generates_refs: dict[str, str] = field(default_factory=dict)
    # Maps field_name -> "schema_name.field_name" for tracking


@dataclass
class PipelineResult:
    """Result of a pipeline execution."""
    datasets: dict[str, list[dict]]  # schema_name -> records
    execution_order: list[str]
    duration_seconds: float
    total_records: int
    errors: list[str] = field(default_factory=list)


class GenerationPipeline:
    """Orchestrates multi-schema generation with dependency resolution."""

    def __init__(self):
        self.schemas: dict[str, SchemaNode] = {}
        self._shared_parser = SchemaParser({"type": "object", "properties": {}})

    def add_schema(
        self,
        name: str,
        schema: dict | str | Path,
        count: int = 100,
        depends_on: list[str] | None = None,
        ref_tracking: dict[str, str] | None = None,
    ) -> "GenerationPipeline":
        """Add a schema to the pipeline.

        Args:
            name: Unique name for this schema in the pipeline
            schema: JSON Schema dict, JSON string, or file path
            count: Number of records to generate
            depends_on: List of schema names this depends on
            ref_tracking: Maps field_name -> ref_key for ID tracking
                e.g. {"sys_id": "sys_user.sys_id"} means the sys_id field
                values will be available as "sys_user.sys_id" for foreign keys

        Returns:
            self for chaining
        """
        if isinstance(schema, (str, Path)):
            path = Path(schema)
            if path.exists():
                with open(path) as f:
                    schema_dict = json.load(f)
            else:
                schema_dict = json.loads(str(schema))
        else:
            schema_dict = schema

        self.schemas[name] = SchemaNode(
            name=name,
            schema=schema_dict,
            count=count,
            depends_on=depends_on or [],
            generates_refs=ref_tracking or {},
        )
        return self

    def resolve_order(self) -> list[str]:
        """Topological sort of schemas based on dependencies."""
        in_degree = {name: 0 for name in self.schemas}
        dependents = defaultdict(list)

        for name, node in self.schemas.items():
            for dep in node.depends_on:
                if dep in self.schemas:
                    in_degree[name] += 1
                    dependents[dep].append(name)

        # Kahn's algorithm
        queue = [name for name, deg in in_degree.items() if deg == 0]
        order = []

        while queue:
            # Sort for deterministic order
            queue.sort()
            current = queue.pop(0)
            order.append(current)
            for dependent in dependents[current]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(order) != len(self.schemas):
            missing = set(self.schemas.keys()) - set(order)
            raise ValueError(f"Circular dependency detected involving: {missing}")

        return order

    def execute(
        self,
        on_progress: Callable[[str, int, int], None] | None = None,
    ) -> PipelineResult:
        """Execute the pipeline, generating all schemas in dependency order.

        Args:
            on_progress: Callback(schema_name, records_done, total) for progress

        Returns:
            PipelineResult with all generated datasets
        """
        start_time = time.time()
        order = self.resolve_order()
        datasets: dict[str, list[dict]] = {}
        errors: list[str] = []
        total_records = 0

        for schema_name in order:
            node = self.schemas[schema_name]
            try:
                parser = SchemaParser(node.schema)

                # Inject reference values from dependencies
                parser._generated_ids = dict(self._shared_parser._generated_ids)

                # Generate records
                records = parser.generate(count=node.count)

                # Track reference values for downstream schemas
                for field_name, ref_key in node.generates_refs.items():
                    for record in records:
                        if field_name in record:
                            self._shared_parser.register_generated_id(
                                ref_key, record[field_name]
                            )

                datasets[schema_name] = records
                total_records += len(records)

                if on_progress:
                    on_progress(schema_name, len(records), node.count)

            except Exception as e:
                errors.append(f"Error generating {schema_name}: {e}")
                datasets[schema_name] = []

        duration = time.time() - start_time

        return PipelineResult(
            datasets=datasets,
            execution_order=order,
            duration_seconds=round(duration, 3),
            total_records=total_records,
            errors=errors,
        )


# ---------------------------------------------------------------------------
# Pre-built pipeline templates
# ---------------------------------------------------------------------------

def servicenow_itsm_pipeline(
    user_count: int = 50,
    ci_count: int = 200,
    incident_count: int = 500,
    change_count: int = 100,
) -> GenerationPipeline:
    """Pre-built pipeline for ServiceNow ITSM data with relationships."""
    pipeline = GenerationPipeline()

    # 1. Users (no dependencies)
    pipeline.add_schema(
        name="sys_user",
        schema={
            "type": "object",
            "properties": {
                "sys_id": {"type": "string", "format": "uuid", "x-datagen-unique": True},
                "user_name": {"type": "string", "x-datagen-faker": "internet.email"},
                "first_name": {"type": "string", "x-datagen-faker": "person.first_name"},
                "last_name": {"type": "string", "x-datagen-faker": "person.last_name"},
                "email": {"type": "string", "x-datagen-faker": "internet.email"},
                "title": {"type": "string", "x-datagen-faker": "job.title"},
                "department": {
                    "type": "string",
                    "enum": ["IT", "Engineering", "Operations", "Security", "Support", "DevOps"],
                    "x-datagen-weight": [20, 25, 15, 10, 20, 10],
                },
                "active": {"type": "boolean", "x-datagen-weight": 0.9},
            },
        },
        count=user_count,
        ref_tracking={"sys_id": "sys_user.sys_id"},
    )

    # 2. CMDB CIs (no dependencies)
    pipeline.add_schema(
        name="cmdb_ci",
        schema={
            "type": "object",
            "properties": {
                "sys_id": {"type": "string", "format": "uuid", "x-datagen-unique": True},
                "name": {"type": "string", "x-datagen-faker": "internet.domain"},
                "sys_class_name": {
                    "type": "string",
                    "enum": ["cmdb_ci_server", "cmdb_ci_vm", "cmdb_ci_app_server",
                             "cmdb_ci_database", "cmdb_ci_netgear", "cmdb_ci_service"],
                    "x-datagen-weight": [20, 25, 15, 15, 10, 15],
                },
                "operational_status": {
                    "type": "integer",
                    "enum": [1, 2, 5, 6],
                    "x-datagen-weight": [70, 15, 10, 5],
                },
                "ip_address": {"type": "string", "format": "ipv4"},
                "os": {
                    "type": "string",
                    "enum": ["Linux", "Windows Server 2022", "RHEL 9", "Ubuntu 22.04", "VMware ESXi"],
                    "x-datagen-weight": [30, 20, 20, 20, 10],
                },
                "environment": {
                    "type": "string",
                    "enum": ["Production", "Staging", "Development", "DR"],
                    "x-datagen-weight": [40, 25, 25, 10],
                },
            },
        },
        count=ci_count,
        ref_tracking={"sys_id": "cmdb_ci.sys_id"},
    )

    # 3. Incidents (depends on users and CIs)
    pipeline.add_schema(
        name="incident",
        schema={
            "type": "object",
            "properties": {
                "sys_id": {"type": "string", "format": "uuid", "x-datagen-unique": True},
                "number": {"type": "string", "pattern": "INC[0-9]{7}", "x-datagen-unique": True},
                "short_description": {"type": "string", "x-datagen-faker": "hacker.phrase"},
                "description": {"type": "string", "x-datagen-faker": "lorem.paragraph"},
                "priority": {
                    "type": "integer",
                    "enum": [1, 2, 3, 4],
                    "x-datagen-weight": [5, 20, 50, 25],
                },
                "urgency": {
                    "type": "integer",
                    "enum": [1, 2, 3],
                    "x-datagen-weight": [15, 45, 40],
                },
                "impact": {
                    "type": "integer",
                    "enum": [1, 2, 3],
                    "x-datagen-weight": [10, 40, 50],
                },
                "state": {
                    "type": "integer",
                    "enum": [1, 2, 3, 6, 7],
                    "x-datagen-weight": [15, 25, 20, 30, 10],
                },
                "category": {
                    "type": "string",
                    "enum": ["Network", "Hardware", "Software", "Database", "Security", "Cloud"],
                    "x-datagen-weight": [20, 15, 25, 15, 10, 15],
                },
                "opened_at": {
                    "type": "string",
                    "format": "date-time",
                    "x-datagen-time-pattern": {"base": "now-90d", "end": "now"},
                },
                "assigned_to": {"type": "string", "x-datagen-ref": "sys_user.sys_id"},
                "caller_id": {"type": "string", "x-datagen-ref": "sys_user.sys_id"},
                "cmdb_ci": {"type": "string", "x-datagen-ref": "cmdb_ci.sys_id"},
            },
        },
        count=incident_count,
        depends_on=["sys_user", "cmdb_ci"],
        ref_tracking={"sys_id": "incident.sys_id"},
    )

    # 4. Change requests (depends on users and CIs)
    pipeline.add_schema(
        name="change_request",
        schema={
            "type": "object",
            "properties": {
                "sys_id": {"type": "string", "format": "uuid", "x-datagen-unique": True},
                "number": {"type": "string", "pattern": "CHG[0-9]{7}", "x-datagen-unique": True},
                "short_description": {"type": "string", "x-datagen-faker": "hacker.phrase"},
                "type": {
                    "type": "string",
                    "enum": ["Normal", "Standard", "Emergency"],
                    "x-datagen-weight": [50, 35, 15],
                },
                "risk": {
                    "type": "string",
                    "enum": ["High", "Moderate", "Low"],
                    "x-datagen-weight": [15, 50, 35],
                },
                "state": {
                    "type": "integer",
                    "enum": [-5, -4, -3, -2, -1, 0, 3],
                    "x-datagen-weight": [5, 10, 15, 10, 5, 40, 15],
                },
                "start_date": {
                    "type": "string",
                    "format": "date-time",
                    "x-datagen-time-pattern": {"base": "now-60d", "end": "now+30d"},
                },
                "assigned_to": {"type": "string", "x-datagen-ref": "sys_user.sys_id"},
                "cmdb_ci": {"type": "string", "x-datagen-ref": "cmdb_ci.sys_id"},
            },
        },
        count=change_count,
        depends_on=["sys_user", "cmdb_ci"],
    )

    return pipeline

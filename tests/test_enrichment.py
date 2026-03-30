"""Tests for the schema enrichment function (_enrich_extracted_schema).

Verifies that extracted schemas get proper x-datagen-faker hints,
enums, format annotations, and pattern fields based on field names.
"""

import pytest

from datagen.api.server import _enrich_extracted_schema
from datagen.engine.generators import gen_string, FAKER_PROVIDERS


# ---------------------------------------------------------------------------
# Basic enrichment tests
# ---------------------------------------------------------------------------

class TestEnrichmentBasic:
    def test_name_field_gets_faker(self):
        schema = {"type": "object", "properties": {
            "name": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        assert result["properties"]["name"].get("x-datagen-faker") == "person.name"

    def test_first_name_field(self):
        schema = {"type": "object", "properties": {
            "first_name": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        assert result["properties"]["first_name"]["x-datagen-faker"] == "person.first_name"

    def test_last_name_field(self):
        schema = {"type": "object", "properties": {
            "last_name": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        assert result["properties"]["last_name"]["x-datagen-faker"] == "person.last_name"

    def test_email_field_gets_format(self):
        schema = {"type": "object", "properties": {
            "email": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        assert result["properties"]["email"]["format"] == "email"

    def test_phone_field(self):
        schema = {"type": "object", "properties": {
            "phone": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        assert result["properties"]["phone"]["x-datagen-faker"] == "phone.number"

    def test_city_field(self):
        schema = {"type": "object", "properties": {
            "city": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        assert result["properties"]["city"]["x-datagen-faker"] == "address.city"

    def test_country_field(self):
        schema = {"type": "object", "properties": {
            "country": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        assert result["properties"]["country"]["x-datagen-faker"] == "address.country"

    def test_company_field(self):
        schema = {"type": "object", "properties": {
            "company": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        assert result["properties"]["company"]["x-datagen-faker"] == "company.name"

    def test_url_field(self):
        schema = {"type": "object", "properties": {
            "url": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        assert result["properties"]["url"]["format"] == "uri"

    def test_ip_address_field(self):
        schema = {"type": "object", "properties": {
            "ip_address": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        assert result["properties"]["ip_address"].get("format") == "ipv4"

    def test_source_ip_field(self):
        schema = {"type": "object", "properties": {
            "source_ip": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        assert result["properties"]["source_ip"].get("format") == "ipv4"

    def test_description_field(self):
        schema = {"type": "object", "properties": {
            "description": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        assert result["properties"]["description"]["x-datagen-faker"] == "lorem.sentence"

    def test_number_field_gets_pattern(self):
        schema = {"type": "object", "properties": {
            "number": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        assert "pattern" in result["properties"]["number"]


# ---------------------------------------------------------------------------
# Enum enrichment tests
# ---------------------------------------------------------------------------

class TestEnrichmentEnums:
    def test_priority_gets_enum(self):
        schema = {"type": "object", "properties": {
            "priority": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        assert "enum" in result["properties"]["priority"]
        assert "1 - Critical" in result["properties"]["priority"]["enum"]

    def test_severity_gets_enum(self):
        schema = {"type": "object", "properties": {
            "severity": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        assert "enum" in result["properties"]["severity"]

    def test_impact_gets_enum(self):
        schema = {"type": "object", "properties": {
            "impact": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        assert "enum" in result["properties"]["impact"]

    def test_urgency_gets_enum(self):
        schema = {"type": "object", "properties": {
            "urgency": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        assert "enum" in result["properties"]["urgency"]

    def test_state_gets_enum(self):
        schema = {"type": "object", "properties": {
            "state": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        prop = result["properties"]["state"]
        assert "enum" in prop
        assert "New" in prop["enum"]
        assert "Closed" in prop["enum"]

    def test_category_gets_enum(self):
        schema = {"type": "object", "properties": {
            "category": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        assert "enum" in result["properties"]["category"]

    def test_active_gets_enum(self):
        schema = {"type": "object", "properties": {
            "active": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        assert result["properties"]["active"]["enum"] == ["true", "false"]


# ---------------------------------------------------------------------------
# Skip enrichment tests — fields that should NOT be modified
# ---------------------------------------------------------------------------

class TestEnrichmentSkips:
    def test_non_string_type_untouched(self):
        """Integer fields should not be enriched."""
        schema = {"type": "object", "properties": {
            "priority": {"type": "integer"},
        }}
        result = _enrich_extracted_schema(schema)
        assert "enum" not in result["properties"]["priority"]
        assert "x-datagen-faker" not in result["properties"]["priority"]

    def test_existing_faker_preserved(self):
        """Fields with existing x-datagen-faker should not be overwritten."""
        schema = {"type": "object", "properties": {
            "name": {"type": "string", "x-datagen-faker": "company.name"},
        }}
        result = _enrich_extracted_schema(schema)
        assert result["properties"]["name"]["x-datagen-faker"] == "company.name"

    def test_existing_enum_preserved(self):
        """Fields with existing enum should not be overwritten."""
        schema = {"type": "object", "properties": {
            "priority": {"type": "string", "enum": ["P1", "P2"]},
        }}
        result = _enrich_extracted_schema(schema)
        assert result["properties"]["priority"]["enum"] == ["P1", "P2"]

    def test_existing_format_preserved(self):
        """Fields with existing format like date-time should not be enriched."""
        schema = {"type": "object", "properties": {
            "opened_at": {"type": "string", "format": "date-time"},
        }}
        result = _enrich_extracted_schema(schema)
        assert "x-datagen-faker" not in result["properties"]["opened_at"]

    def test_existing_pattern_preserved(self):
        """Fields with existing pattern should not be enriched."""
        schema = {"type": "object", "properties": {
            "number": {"type": "string", "pattern": "REQ[0-9]{7}"},
        }}
        result = _enrich_extracted_schema(schema)
        assert result["properties"]["number"]["pattern"] == "REQ[0-9]{7}"

    def test_unrecognized_field_untouched(self):
        """Fields with names not matching any pattern should be left as-is."""
        schema = {"type": "object", "properties": {
            "xyzzy_foo_bar": {"type": "string"},
        }}
        result = _enrich_extracted_schema(schema)
        prop = result["properties"]["xyzzy_foo_bar"]
        assert "x-datagen-faker" not in prop
        assert "enum" not in prop
        assert "pattern" not in prop


# ---------------------------------------------------------------------------
# ServiceNow-style field enrichment
# ---------------------------------------------------------------------------

class TestEnrichmentServiceNow:
    def test_snow_incident_fields(self):
        """Simulate ServiceNow incident table fields."""
        schema = {"type": "object", "properties": {
            "number": {"type": "string"},
            "short_description": {"type": "string"},
            "description": {"type": "string"},
            "priority": {"type": "string"},
            "impact": {"type": "string"},
            "urgency": {"type": "string"},
            "state": {"type": "string"},
            "category": {"type": "string"},
            "subcategory": {"type": "string"},
            "assigned_to": {"type": "string"},
            "opened_by": {"type": "string"},
            "caller": {"type": "string"},
            "location": {"type": "string"},
            "active": {"type": "string"},
            "opened_at": {"type": "string", "format": "date-time"},
            "closed_at": {"type": "string", "format": "date-time"},
        }}
        result = _enrich_extracted_schema(schema)
        p = result["properties"]

        assert "pattern" in p["number"]
        assert p["short_description"]["x-datagen-faker"] == "lorem.sentence"
        assert p["description"]["x-datagen-faker"] == "lorem.sentence"
        assert "enum" in p["priority"]
        assert "enum" in p["impact"]
        assert "enum" in p["urgency"]
        assert "enum" in p["state"]
        assert "enum" in p["category"]
        assert "enum" in p["subcategory"]
        assert p["assigned_to"]["x-datagen-faker"] == "person.name"
        assert p["opened_by"]["x-datagen-faker"] == "person.name"
        assert p["caller"]["x-datagen-faker"] == "person.name"
        assert p["location"]["x-datagen-faker"] == "address.city"
        assert p["active"]["enum"] == ["true", "false"]
        # date-time fields should be left untouched
        assert "x-datagen-faker" not in p["opened_at"]
        assert "x-datagen-faker" not in p["closed_at"]


# ---------------------------------------------------------------------------
# Enriched schema generates valid data
# ---------------------------------------------------------------------------

class TestEnrichedSchemaGeneratesData:
    def test_enriched_fields_produce_valid_data(self):
        """All enriched faker/enum/pattern/format fields should generate valid data."""
        schema = {"type": "object", "properties": {
            "name": {"type": "string"},
            "email": {"type": "string"},
            "phone": {"type": "string"},
            "city": {"type": "string"},
            "priority": {"type": "string"},
            "state": {"type": "string"},
            "description": {"type": "string"},
            "number": {"type": "string"},
            "ip_address": {"type": "string"},
            "url": {"type": "string"},
        }}
        enriched = _enrich_extracted_schema(schema)
        for field_name, prop in enriched["properties"].items():
            result = gen_string(prop)
            assert isinstance(result, str), f"Field '{field_name}' did not produce a string"
            assert len(result) > 0, f"Field '{field_name}' produced empty string"

    def test_all_enriched_faker_keys_exist_in_providers(self):
        """Every x-datagen-faker value set by enrichment should exist in FAKER_PROVIDERS."""
        schema = {"type": "object", "properties": {
            "name": {"type": "string"},
            "first_name": {"type": "string"},
            "last_name": {"type": "string"},
            "phone": {"type": "string"},
            "city": {"type": "string"},
            "state": {"type": "string"},
            "country": {"type": "string"},
            "company": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "user_agent": {"type": "string"},
            "mac_address": {"type": "string"},
            "domain": {"type": "string"},
            "location": {"type": "string"},
            "address": {"type": "string"},
            "zip_code": {"type": "string"},
        }}
        enriched = _enrich_extracted_schema(schema)
        for field_name, prop in enriched["properties"].items():
            faker_key = prop.get("x-datagen-faker")
            if faker_key:
                assert faker_key in FAKER_PROVIDERS, (
                    f"Field '{field_name}' has x-datagen-faker='{faker_key}' "
                    f"which is not in FAKER_PROVIDERS"
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

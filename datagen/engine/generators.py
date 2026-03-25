"""
Data generation primitives for all JSON Schema types.

Each generator handles a specific data type and respects x-datagen-* extension
keywords for fine-grained control over distributions, patterns, and dependencies.
"""

from __future__ import annotations

import math
import random
import re
import string
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from faker import Faker

fake = Faker()

# ---------------------------------------------------------------------------
# Registry of generator functions keyed by (type, format)
# ---------------------------------------------------------------------------
_GENERATORS: dict[tuple[str, str | None], callable] = {}


def register(schema_type: str, schema_format: str | None = None):
    """Decorator to register a generator for a (type, format) pair."""
    def decorator(fn):
        _GENERATORS[(schema_type, schema_format)] = fn
        return fn
    return decorator


def get_generator(schema_type: str, schema_format: str | None = None):
    """Look up the best matching generator."""
    return _GENERATORS.get((schema_type, schema_format)) or _GENERATORS.get((schema_type, None))


# ---------------------------------------------------------------------------
# Faker provider mapping — x-datagen-faker: "person.name" etc.
# ---------------------------------------------------------------------------
FAKER_PROVIDERS: dict[str, callable] = {
    "person.name": lambda: fake.name(),
    "person.first_name": lambda: fake.first_name(),
    "person.last_name": lambda: fake.last_name(),
    "person.prefix": lambda: fake.prefix(),
    "internet.email": lambda: fake.email(),
    "internet.url": lambda: fake.url(),
    "internet.ipv4": lambda: fake.ipv4(),
    "internet.ipv6": lambda: fake.ipv6(),
    "internet.mac_address": lambda: fake.mac_address(),
    "internet.user_agent": lambda: fake.user_agent(),
    "internet.domain": lambda: fake.domain_name(),
    "address.full": lambda: fake.address(),
    "address.city": lambda: fake.city(),
    "address.state": lambda: fake.state(),
    "address.country": lambda: fake.country(),
    "address.zipcode": lambda: fake.zipcode(),
    "address.latitude": lambda: str(fake.latitude()),
    "address.longitude": lambda: str(fake.longitude()),
    "company.name": lambda: fake.company(),
    "company.bs": lambda: fake.bs(),
    "company.catch_phrase": lambda: fake.catch_phrase(),
    "phone.number": lambda: fake.phone_number(),
    "lorem.sentence": lambda: fake.sentence(),
    "lorem.paragraph": lambda: fake.paragraph(),
    "lorem.text": lambda: fake.text(max_nb_chars=200),
    "lorem.word": lambda: fake.word(),
    "hacker.phrase": lambda: fake.sentence(nb_words=6),
    "finance.credit_card": lambda: fake.credit_card_number(),
    "finance.iban": lambda: fake.iban(),
    "misc.uuid": lambda: str(uuid.uuid4()),
    "misc.md5": lambda: fake.md5(),
    "misc.sha256": lambda: fake.sha256(),
    "misc.color_hex": lambda: fake.hex_color(),
    "misc.file_path": lambda: fake.file_path(),
    "misc.mime_type": lambda: fake.mime_type(),
    "job.title": lambda: fake.job(),
}


# ---------------------------------------------------------------------------
# Distribution helpers
# ---------------------------------------------------------------------------

def sample_distribution(config: dict) -> float:
    """Sample a value from a statistical distribution."""
    dist_type = config.get("type", "uniform")
    if dist_type == "uniform":
        return random.uniform(config.get("min", 0), config.get("max", 1))
    elif dist_type == "gaussian" or dist_type == "normal":
        return random.gauss(config.get("mean", 0), config.get("stddev", 1))
    elif dist_type == "poisson":
        # Knuth algorithm for small lambda
        lam = config.get("lambda", config.get("rate", 5))
        L = math.exp(-lam)
        k, p = 0, 1.0
        while p > L:
            k += 1
            p *= random.random()
        return k - 1
    elif dist_type == "exponential":
        return random.expovariate(1.0 / config.get("mean", 1))
    elif dist_type == "histogram":
        bins = config.get("bins", [])
        weights = config.get("weights", [1] * len(bins))
        if bins:
            chosen = random.choices(range(len(bins)), weights=weights, k=1)[0]
            b = bins[chosen]
            if isinstance(b, (list, tuple)):
                return random.uniform(b[0], b[1])
            return b
    return random.random()


def weighted_choice(values: list, weights: list | None = None) -> Any:
    """Pick a value with optional probability weights."""
    if weights:
        return random.choices(values, weights=weights, k=1)[0]
    return random.choice(values)


# ---------------------------------------------------------------------------
# String generators
# ---------------------------------------------------------------------------

@register("string")
def gen_string(schema: dict, context: dict | None = None) -> str:
    """Generate a string value based on schema constraints."""
    # x-datagen-faker takes priority
    faker_key = schema.get("x-datagen-faker")
    if faker_key and faker_key in FAKER_PROVIDERS:
        return FAKER_PROVIDERS[faker_key]()

    # Enum with optional weights
    if "enum" in schema:
        weights = schema.get("x-datagen-weight")
        return weighted_choice(schema["enum"], weights)

    # Regex pattern — generate matching string
    pattern = schema.get("pattern")
    if pattern:
        return _gen_from_pattern(pattern)

    # Format-specific
    fmt = schema.get("format")
    if fmt == "date-time":
        return gen_datetime(schema, context)
    elif fmt == "date":
        return fake.date()
    elif fmt == "time":
        return fake.time()
    elif fmt == "email":
        return fake.email()
    elif fmt == "uri" or fmt == "url":
        return fake.url()
    elif fmt == "uuid":
        return str(uuid.uuid4())
    elif fmt == "ipv4":
        return fake.ipv4()
    elif fmt == "ipv6":
        return fake.ipv6()
    elif fmt == "hostname":
        return fake.hostname()

    # Default: lorem sentence
    min_len = schema.get("minLength", 5)
    max_len = schema.get("maxLength", 100)
    text = fake.text(max_nb_chars=max(max_len, 20))
    return text[:max_len] if len(text) > max_len else text


def _gen_from_pattern(pattern: str) -> str:
    """Generate a string matching a simple regex pattern.

    Supports: literal chars, [0-9], [a-z], [A-Z], {n}, {n,m}, +, *
    This is a simplified generator — not a full regex engine.
    """
    result = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == '[':
            # Character class
            end = pattern.index(']', i)
            char_class = pattern[i+1:end]
            i = end + 1
            # Check for quantifier
            count = _parse_quantifier(pattern, i)
            i += count[1]
            for _ in range(count[0]):
                result.append(_sample_char_class(char_class))
        elif c == '\\':
            i += 1
            if i < len(pattern):
                if pattern[i] == 'd':
                    count = _parse_quantifier(pattern, i + 1)
                    i += 1 + count[1]
                    for _ in range(count[0]):
                        result.append(random.choice(string.digits))
                elif pattern[i] == 'w':
                    count = _parse_quantifier(pattern, i + 1)
                    i += 1 + count[1]
                    for _ in range(count[0]):
                        result.append(random.choice(string.ascii_letters + string.digits + '_'))
                else:
                    result.append(pattern[i])
                    i += 1
        elif c in ('^', '$'):
            i += 1  # Skip anchors
        elif c == '.':
            count = _parse_quantifier(pattern, i + 1)
            i += 1 + count[1]
            for _ in range(count[0]):
                result.append(random.choice(string.ascii_letters + string.digits))
        else:
            result.append(c)
            i += 1
    return ''.join(result)


def _parse_quantifier(pattern: str, pos: int) -> tuple[int, int]:
    """Parse {n}, {n,m}, +, *, ? at position. Returns (count, chars_consumed)."""
    if pos >= len(pattern):
        return (1, 0)
    c = pattern[pos]
    if c == '{':
        end = pattern.index('}', pos)
        inner = pattern[pos+1:end]
        consumed = end - pos + 1
        if ',' in inner:
            parts = inner.split(',')
            lo = int(parts[0])
            hi = int(parts[1]) if parts[1] else lo + 5
            return (random.randint(lo, hi), consumed)
        return (int(inner), consumed)
    elif c == '+':
        return (random.randint(1, 5), 1)
    elif c == '*':
        return (random.randint(0, 5), 1)
    elif c == '?':
        return (random.randint(0, 1), 1)
    return (1, 0)


def _sample_char_class(cls: str) -> str:
    """Sample one character from a character class like 0-9, a-z, A-Z."""
    chars = []
    i = 0
    while i < len(cls):
        if i + 2 < len(cls) and cls[i+1] == '-':
            chars.extend(chr(c) for c in range(ord(cls[i]), ord(cls[i+2]) + 1))
            i += 3
        else:
            chars.append(cls[i])
            i += 1
    return random.choice(chars) if chars else '?'


# ---------------------------------------------------------------------------
# Numeric generators
# ---------------------------------------------------------------------------

@register("integer")
def gen_integer(schema: dict, context: dict | None = None) -> int:
    """Generate an integer value."""
    if "enum" in schema:
        weights = schema.get("x-datagen-weight")
        return weighted_choice(schema["enum"], weights)

    dist = schema.get("x-datagen-distribution")
    if dist:
        return int(round(sample_distribution(dist)))

    minimum = schema.get("minimum", 0)
    maximum = schema.get("maximum", 1000)
    step = schema.get("multipleOf", 1)
    return random.randrange(minimum, maximum + 1, step)


@register("number")
def gen_number(schema: dict, context: dict | None = None) -> float:
    """Generate a floating-point number."""
    if "enum" in schema:
        weights = schema.get("x-datagen-weight")
        return weighted_choice(schema["enum"], weights)

    dist = schema.get("x-datagen-distribution")
    if dist:
        val = sample_distribution(dist)
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None:
            val = max(val, minimum)
        if maximum is not None:
            val = min(val, maximum)
        return round(val, schema.get("x-datagen-precision", 4))

    minimum = schema.get("minimum", 0.0)
    maximum = schema.get("maximum", 1000.0)
    return round(random.uniform(minimum, maximum), schema.get("x-datagen-precision", 2))


# ---------------------------------------------------------------------------
# Boolean generator
# ---------------------------------------------------------------------------

@register("boolean")
def gen_boolean(schema: dict, context: dict | None = None) -> bool:
    """Generate a boolean with optional probability weighting."""
    weight = schema.get("x-datagen-weight", 0.5)
    if isinstance(weight, (list, tuple)):
        weight = weight[0] / sum(weight)  # Normalize [true_weight, false_weight]
    return random.random() < weight


# ---------------------------------------------------------------------------
# DateTime generator
# ---------------------------------------------------------------------------

@register("string", "date-time")
def gen_datetime(schema: dict, context: dict | None = None) -> str:
    """Generate an ISO 8601 datetime string."""
    time_pattern = schema.get("x-datagen-time-pattern", {})
    now = datetime.now(timezone.utc)

    base_str = time_pattern.get("base", "now-30d")
    base = _parse_time_base(base_str, now)

    end_str = time_pattern.get("end", "now")
    end = _parse_time_base(end_str, now)

    # Random point between base and end
    delta = (end - base).total_seconds()
    if delta <= 0:
        delta = 86400  # 1 day fallback
    offset = random.uniform(0, delta)
    dt = base + timedelta(seconds=offset)

    fmt = time_pattern.get("format", "iso")
    if fmt == "epoch":
        return str(int(dt.timestamp()))
    elif fmt == "epoch_ms":
        return str(int(dt.timestamp() * 1000))
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _parse_time_base(expr: str, now: datetime) -> datetime:
    """Parse time expressions like 'now', 'now-30d', 'now-2h', '2024-01-01'."""
    if expr == "now":
        return now
    if expr.startswith("now"):
        match = re.match(r"now([+-])(\d+)([smhdwMy])", expr)
        if match:
            sign = 1 if match.group(1) == '+' else -1
            amount = int(match.group(2))
            unit = match.group(3)
            multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800, 'M': 2592000, 'y': 31536000}
            seconds = amount * multipliers.get(unit, 86400)
            return now + timedelta(seconds=sign * seconds)
    try:
        return datetime.fromisoformat(expr.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return now - timedelta(days=30)


# ---------------------------------------------------------------------------
# Array generator
# ---------------------------------------------------------------------------

@register("array")
def gen_array(schema: dict, context: dict | None = None) -> list:
    """Generate an array of items based on the items schema."""
    min_items = schema.get("minItems", 1)
    max_items = schema.get("maxItems", 5)
    count = random.randint(min_items, max_items)

    items_schema = schema.get("items", {"type": "string"})
    unique = schema.get("uniqueItems", False) or schema.get("x-datagen-unique", False)

    from datagen.engine.schema_parser import generate_value
    results = []
    seen = set()
    attempts = 0
    while len(results) < count and attempts < count * 10:
        val = generate_value(items_schema, context)
        if unique:
            key = str(val)
            if key in seen:
                attempts += 1
                continue
            seen.add(key)
        results.append(val)
        attempts += 1

    return results


# ---------------------------------------------------------------------------
# Object generator (delegates to schema_parser for nested objects)
# ---------------------------------------------------------------------------

@register("object")
def gen_object(schema: dict, context: dict | None = None) -> dict:
    """Generate an object — delegates to schema_parser.generate_record."""
    from datagen.engine.schema_parser import generate_record
    return generate_record(schema, context)


# ---------------------------------------------------------------------------
# Null generator
# ---------------------------------------------------------------------------

@register("null")
def gen_null(schema: dict, context: dict | None = None) -> None:
    return None

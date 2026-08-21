import re
import logging

_IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

VALID_STRATEGIES = {'append', 'replace', 'truncate', 'fail'}

logger = logging.getLogger(__name__)


def validate_identifier(name: str, label: str = "identifier") -> str:
    if not name or not _IDENTIFIER_RE.match(name):
        raise ValueError(
            f"Invalid {label}: '{name}'. "
            "Only letters, digits and underscores allowed, must start with a letter or underscore."
        )
    return name


def validate_strategy(value: str) -> str:
    v = value.lower().strip()
    if v not in VALID_STRATEGIES:
        raise ValueError(
            f"Invalid strategy_destiny: '{value}'. "
            f"Must be one of: {', '.join(sorted(VALID_STRATEGIES))}"
        )
    return v


def sanitize_url(url: str) -> str:
    if not url:
        return url
    return re.sub(r'://([^:]+):([^@]+)@', r'://\1:***@', url)

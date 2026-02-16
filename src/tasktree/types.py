"""Custom Click parameter types for task argument validation."""

import re
from datetime import datetime
from ipaddress import IPv4Address, IPv6Address, ip_address
from typing import Any, Optional

import click


class HostnameType(click.ParamType):
    """
    Validates hostname format (not DNS resolution).
    """

    name = "hostname"

    # Simple hostname validation (RFC 1123)
    HOSTNAME_PATTERN = re.compile(
        r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63})*\.?$"
    )

    def convert(
        self, value: Any, param: Optional[click.Parameter], ctx: Optional[click.Context]
    ) -> str:
        """
        """
        if isinstance(value, str):
            if self.HOSTNAME_PATTERN.match(value):
                return value
        self.fail(f"{value!r} is not a valid hostname", param, ctx)


class EmailType(click.ParamType):
    """
    Validates email format (not deliverability).
    """

    name = "email"

    # Basic email validation (RFC 5322 simplified)
    EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

    def convert(
        self, value: Any, param: Optional[click.Parameter], ctx: Optional[click.Context]
    ) -> str:
        """
        """
        if isinstance(value, str):
            if self.EMAIL_PATTERN.match(value):
                return value
        self.fail(f"{value!r} is not a valid email address", param, ctx)


class IPType(click.ParamType):
    """
    Validates IP address (IPv4 or IPv6).
    """

    name = "ip"

    def convert(
        self, value: Any, param: Optional[click.Parameter], ctx: Optional[click.Context]
    ) -> str:
        """
        """
        try:
            ip_address(value)
            return str(value)
        except ValueError:
            self.fail(f"{value!r} is not a valid IP address", param, ctx)


class IPv4Type(click.ParamType):
    """
    Validates IPv4 address.
    """

    name = "ipv4"

    def convert(
        self, value: Any, param: Optional[click.Parameter], ctx: Optional[click.Context]
    ) -> str:
        """
        """
        try:
            IPv4Address(value)
            return str(value)
        except ValueError:
            self.fail(f"{value!r} is not a valid IPv4 address", param, ctx)


class IPv6Type(click.ParamType):
    """
    Validates IPv6 address.
    """

    name = "ipv6"

    def convert(
        self, value: Any, param: Optional[click.Parameter], ctx: Optional[click.Context]
    ) -> str:
        """
        """
        try:
            IPv6Address(value)
            return str(value)
        except ValueError:
            self.fail(f"{value!r} is not a valid IPv6 address", param, ctx)


class DateTimeType(click.ParamType):
    """
    Validates datetime in format YYYY-MM-DDTHH:MM:SS.
    """

    name = "datetime"

    def convert(
        self, value: Any, param: Optional[click.Parameter], ctx: Optional[click.Context]
    ) -> str:
        """
        """
        if isinstance(value, str):
            try:
                datetime.fromisoformat(value)
                return value
            except ValueError:
                pass
        self.fail(
            f"{value!r} is not a valid datetime (expected YYYY-MM-DDTHH:MM:SS format)",
            param,
            ctx,
        )


# Type registry for dynamic parameter creation
TYPE_MAPPING = {
    "str": click.STRING,
    "int": click.INT,
    "float": click.FLOAT,
    "bool": click.BOOL,
    "path": click.Path(),
    "datetime": DateTimeType(),
    "hostname": HostnameType(),
    "email": EmailType(),
    "ip": IPType(),
    "ipv4": IPv4Type(),
    "ipv6": IPv6Type(),
}


def get_click_type(
    type_name: str,
    min_val: int | float | None = None,
    max_val: int | float | None = None,
) -> click.ParamType:
    """
    Get Click parameter type by name with optional range constraints.

    Args:
    type_name: Type name from task definition (e.g., 'str', 'int', 'hostname')
    min_val: Optional minimum value for numeric types
    max_val: Optional maximum value for numeric types

    Returns:
    Click parameter type instance

    Raises:
    ValueError: If type_name is not recognized
    """
    if type_name not in TYPE_MAPPING:
        raise ValueError(f"Unknown type: {type_name}")

    # For int and float types, apply range constraints if specified
    if type_name == "int" and (min_val is not None or max_val is not None):
        return click.IntRange(min=min_val, max=max_val)
    elif type_name == "float" and (min_val is not None or max_val is not None):
        return click.FloatRange(min=min_val, max=max_val)

    return TYPE_MAPPING[type_name]

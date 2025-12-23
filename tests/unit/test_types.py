"""Unit tests for custom Click parameter types."""

import unittest

import click

from tasktree.types import (
    DateTimeType,
    EmailType,
    HostnameType,
    IPType,
    IPv4Type,
    IPv6Type,
    get_click_type,
)


class TestHostnameType(unittest.TestCase):
    """Tests for HostnameType validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.hostname_type = HostnameType()

    def test_hostname_valid(self):
        """Test valid hostnames pass validation."""
        valid_hostnames = [
            "example.com",
            "subdomain.example.com",
            "host-name.com",
            "a.b.c.d.example.com",
            "localhost",
            "example",
            "my-server-01",
        ]
        for hostname in valid_hostnames:
            result = self.hostname_type.convert(hostname, None, None)
            self.assertEqual(result, hostname)

    def test_hostname_invalid_characters(self):
        """Test hostnames with invalid characters fail."""
        invalid_hostnames = [
            "host@name.com",
            "host name.com",
            "host_name.com",
            "host..name.com",
            "-hostname.com",  # starts with hyphen
            "hostname-.com",  # label ends with hyphen
        ]
        for hostname in invalid_hostnames:
            with self.assertRaises(click.exceptions.BadParameter):
                self.hostname_type.convert(hostname, None, None)

    def test_hostname_too_long(self):
        """Test hostnames >253 characters fail."""
        # Create a hostname longer than 253 characters
        long_hostname = "a" * 254 + ".com"
        with self.assertRaises(click.exceptions.BadParameter):
            self.hostname_type.convert(long_hostname, None, None)

    def test_hostname_empty(self):
        """Test empty hostname fails."""
        with self.assertRaises(click.exceptions.BadParameter):
            self.hostname_type.convert("", None, None)


class TestEmailType(unittest.TestCase):
    """Tests for EmailType validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.email_type = EmailType()

    def test_email_valid(self):
        """Test valid email addresses pass."""
        valid_emails = [
            "user@example.com",
            "user+tag@example.co.uk",
            "firstname.lastname@example.com",
            "user123@test-domain.org",
            "a@b.c",
        ]
        for email in valid_emails:
            result = self.email_type.convert(email, None, None)
            self.assertEqual(result, email)

    def test_email_no_at(self):
        """Test email without @ fails."""
        with self.assertRaises(click.exceptions.BadParameter):
            self.email_type.convert("userexample.com", None, None)

    def test_email_no_domain(self):
        """Test email without domain fails."""
        with self.assertRaises(click.exceptions.BadParameter):
            self.email_type.convert("user@", None, None)

    def test_email_invalid_format(self):
        """Test malformed emails fail."""
        invalid_emails = [
            "@example.com",
            "user@",
            "user",
            "user @example.com",
            "user@domain",  # no TLD
        ]
        for email in invalid_emails:
            with self.assertRaises(click.exceptions.BadParameter):
                self.email_type.convert(email, None, None)


class TestIPTypes(unittest.TestCase):
    """Tests for IP address type validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.ip_type = IPType()
        self.ipv4_type = IPv4Type()
        self.ipv6_type = IPv6Type()

    def test_ip_valid_ipv4(self):
        """Test valid IPv4 addresses pass."""
        valid_ipv4 = [
            "192.168.1.1",
            "10.0.0.1",
            "127.0.0.1",
            "255.255.255.255",
        ]
        for ip in valid_ipv4:
            result = self.ip_type.convert(ip, None, None)
            self.assertEqual(result, ip)

    def test_ip_valid_ipv6(self):
        """Test valid IPv6 addresses pass."""
        valid_ipv6 = [
            "2001:0db8:85a3:0000:0000:8a2e:0370:7334",
            "::1",
            "fe80::1",
            "2001:db8::1",
        ]
        for ip in valid_ipv6:
            result = self.ip_type.convert(ip, None, None)
            self.assertEqual(result, ip)

    def test_ipv4_valid(self):
        """Test IPv4Type accepts valid IPv4 addresses."""
        result = self.ipv4_type.convert("192.168.1.1", None, None)
        self.assertEqual(result, "192.168.1.1")

    def test_ipv4_rejects_ipv6(self):
        """Test IPv4Type rejects IPv6 addresses."""
        with self.assertRaises(click.exceptions.BadParameter):
            self.ipv4_type.convert("2001:db8::1", None, None)

    def test_ipv6_valid(self):
        """Test IPv6Type accepts valid IPv6 addresses."""
        result = self.ipv6_type.convert("::1", None, None)
        self.assertEqual(result, "::1")

    def test_ipv6_rejects_ipv4(self):
        """Test IPv6Type rejects IPv4 addresses."""
        with self.assertRaises(click.exceptions.BadParameter):
            self.ipv6_type.convert("192.168.1.1", None, None)

    def test_ip_invalid(self):
        """Test invalid IP formats fail."""
        invalid_ips = [
            "256.256.256.256",
            "not-an-ip",
            "192.168.1",
            "192.168.1.1.1",
            "",
        ]
        for ip in invalid_ips:
            with self.assertRaises(click.exceptions.BadParameter):
                self.ip_type.convert(ip, None, None)

    def test_ip_empty(self):
        """Test empty IP fails."""
        with self.assertRaises(click.exceptions.BadParameter):
            self.ip_type.convert("", None, None)


class TestDateTimeType(unittest.TestCase):
    """Tests for DateTimeType validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.datetime_type = DateTimeType()

    def test_datetime_iso_format(self):
        """Test ISO format datetimes pass."""
        valid_datetimes = [
            "2023-01-15T10:30:00",
            "2023-12-31T23:59:59",
            "2023-01-01T00:00:00",
            "2023-06-15T14:30:45",
        ]
        for dt in valid_datetimes:
            result = self.datetime_type.convert(dt, None, None)
            self.assertEqual(result, dt)

    def test_datetime_invalid_format(self):
        """Test non-ISO formats fail."""
        invalid_datetimes = [
            "2023/01/15T10:30:00",  # slashes instead of hyphens
            "15-01-2023T10:30:00",  # wrong order
            "not-a-datetime",
            "2023-13-01T10:30:00",  # invalid month
            "2023-01-32T10:30:00",  # invalid day
        ]
        for dt in invalid_datetimes:
            with self.assertRaises(click.exceptions.BadParameter):
                self.datetime_type.convert(dt, None, None)

    def test_datetime_empty(self):
        """Test empty datetime fails."""
        with self.assertRaises(click.exceptions.BadParameter):
            self.datetime_type.convert("", None, None)


class TestGetClickType(unittest.TestCase):
    """Tests for get_click_type() function."""

    def test_get_click_type_str(self):
        """Test returns STRING for 'str'."""
        result = get_click_type("str")
        self.assertEqual(result, click.STRING)

    def test_get_click_type_int(self):
        """Test returns INT for 'int'."""
        result = get_click_type("int")
        self.assertEqual(result, click.INT)

    def test_get_click_type_float(self):
        """Test returns FLOAT for 'float'."""
        result = get_click_type("float")
        self.assertEqual(result, click.FLOAT)

    def test_get_click_type_bool(self):
        """Test returns BOOL for 'bool'."""
        result = get_click_type("bool")
        self.assertEqual(result, click.BOOL)

    def test_get_click_type_path(self):
        """Test returns Path for 'path'."""
        result = get_click_type("path")
        self.assertIsInstance(result, click.Path)

    def test_get_click_type_custom_types(self):
        """Test returns custom types (hostname, email, ip, etc)."""
        custom_types = {
            "hostname": HostnameType,
            "email": EmailType,
            "ip": IPType,
            "ipv4": IPv4Type,
            "ipv6": IPv6Type,
            "datetime": DateTimeType,
        }
        for type_name, expected_class in custom_types.items():
            result = get_click_type(type_name)
            self.assertIsInstance(result, expected_class)

    def test_get_click_type_unknown(self):
        """Test raises ValueError for unknown type."""
        with self.assertRaises(ValueError) as cm:
            get_click_type("unknown_type")
        self.assertIn("Unknown type", str(cm.exception))

    def test_get_click_type_case_sensitivity(self):
        """Test type names are case-sensitive."""
        # 'str' should work, 'STR' should not
        self.assertEqual(get_click_type("str"), click.STRING)
        with self.assertRaises(ValueError):
            get_click_type("STR")


if __name__ == "__main__":
    unittest.main()

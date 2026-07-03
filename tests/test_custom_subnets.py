"""PORT-12: custom subnet list for the network scanner.

Когда ``shared_config.custom_subnets`` непустой, сканер должен пройти по
каждому указанному CIDR; пустой список или невалидные записи → авто-детект
одной подсети (поведение до v1.4.0). Логика построения списка сетей
вынесена в NetworkScanner._build_networks(), что делает её тестируемой
без запуска реального nmap.
"""
import ipaddress
from unittest.mock import MagicMock

import pytest


def _scanner_with(custom_subnets):
    """Build a NetworkScanner-ish object with only the attrs _build_networks
    touches. We attach the method directly to avoid importing the full
    scanning module (which pulls nmap/getmac at top level)."""
    from actions.scanning import NetworkScanner
    ns = NetworkScanner.__new__(NetworkScanner)
    ns.shared_data = MagicMock()
    ns.shared_data.custom_subnets = custom_subnets
    ns.logger = MagicMock()
    # get_network should only be called on the fallback path.
    ns.get_network = MagicMock(return_value=ipaddress.IPv4Network("192.168.1.0/24"))
    return ns


class TestBuildNetworks:
    def test_empty_custom_subnets_falls_back_to_auto_detect(self):
        ns = _scanner_with([])
        nets = ns._build_networks()
        assert nets == [ipaddress.IPv4Network("192.168.1.0/24")], (
            "Empty custom_subnets must auto-detect a single network.")
        ns.get_network.assert_called_once()

    def test_none_custom_subnets_falls_back_to_auto_detect(self):
        ns = _scanner_with(None)
        nets = ns._build_networks()
        assert len(nets) == 1
        ns.get_network.assert_called_once()

    def test_custom_subnets_parsed_as_list(self):
        ns = _scanner_with(["10.0.0.0/24", "172.16.5.0/28"])
        nets = ns._build_networks()
        assert nets == [
            ipaddress.IPv4Network("10.0.0.0/24"),
            ipaddress.IPv4Network("172.16.5.0/28"),
        ]
        # Auto-detect must NOT run when explicit subnets are provided.
        ns.get_network.assert_not_called()

    def test_invalid_entries_are_skipped_valid_one_used(self):
        ns = _scanner_with(["not-a-cidr", "10.0.0.0/24", "999.999.999.999"])
        nets = ns._build_networks()
        assert nets == [ipaddress.IPv4Network("10.0.0.0/24")]
        ns.get_network.assert_not_called()

    def test_all_invalid_custom_subnets_falls_back_to_auto_detect(self):
        ns = _scanner_with(["garbage", "also-garbage"])
        nets = ns._build_networks()
        assert len(nets) == 1, (
            "If every custom entry is invalid, must fall back to auto-detect "
            "rather than scanning nothing.")
        ns.get_network.assert_called_once()

    def test_non_strict_cidr_normalization(self):
        """A bare IP (no prefix) must be accepted via strict=False."""
        ns = _scanner_with(["192.168.0.50"])
        nets = ns._build_networks()
        assert nets == [ipaddress.IPv4Network("192.168.0.50/32")]


class TestCustomSubnetsConfig:
    def test_default_config_has_custom_subnets(self):
        from shared import SharedData
        sd = SharedData.__new__(SharedData)
        cfg = sd.get_default_config()
        assert "custom_subnets" in cfg, "custom_subnets must be a config key."
        assert cfg["custom_subnets"] == [], (
            "Default must be empty list (= auto-detect, pre-v1.4.0 behaviour).")

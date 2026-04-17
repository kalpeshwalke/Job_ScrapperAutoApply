"""
MCP Configuration Manager

Manages loading, validation, and access to MCP (Model Context Protocol) configuration
for the Playwright MCP server integration.

Reads configuration from `.kiro/settings/mcp.json` or a configurable path,
and provides typed access to server settings, auto-approval rules, and logging config.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)


# Default MCP configuration used when no config file is found
DEFAULT_MCP_CONFIG = {
    "mcpServers": {
        "playwright": {
            "command": "npx",
            "args": ["-y", "@playwright/mcp-server"],
            "enabled": True,
            "autoApprove": [
                "playwright_navigate",
                "playwright_click",
                "playwright_fill",
                "playwright_select_option",
                "playwright_hover",
                "playwright_screenshot",
                "playwright_evaluate",
                "playwright_get_text",
                "playwright_get_attribute",
                "playwright_wait_for_selector",
                "playwright_press_key",
            ],
            "timeout": 30000,
            "env": {},
        }
    },
    "fallback": {
        "enabled": True,
        "strategy": "dom_toolkit",
    },
    "logging": {
        "enabled": True,
        "log_tool_calls": True,
        "log_tool_results": True,
        "log_latency": True,
        "log_errors": True,
        "structured_json": True,
    },
    "global": {
        "mcp_enabled": True,
        "config_version": "1.0",
    },
}

# Required top-level keys for a valid MCP config
_REQUIRED_KEYS = {"mcpServers", "global"}

# Required keys inside a server entry
_REQUIRED_SERVER_KEYS = {"command", "args"}


class MCPConfigManager:
    """
    Manager for MCP configuration.

    Loads, validates, and provides typed access to MCP settings including
    server configuration, auto-approval rules, timeouts, and logging options.

    Usage:
        manager = MCPConfigManager()                     # auto-discovers config
        manager = MCPConfigManager("path/to/mcp.json")   # explicit path

        if manager.is_mcp_enabled():
            pw_config = manager.get_playwright_config()
            client = MCPClient(pw_config)
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize MCPConfigManager.

        Args:
            config_path: Explicit path to MCP JSON config file.
                         If None, auto-discovers from `.kiro/settings/mcp.json`
                         relative to the project root.
        """
        self._config: Dict[str, Any] = {}
        self._config_path: Optional[str] = None
        self._loaded = False
        self._validation_errors: List[str] = []

        # Resolve and load config
        self._config_path = self._resolve_config_path(config_path)
        self._config = self.load_config(self._config_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Load and parse MCP configuration from a JSON file.

        If the file is missing or invalid, falls back to built-in defaults
        so the system can always start.

        Args:
            config_path: Path to the JSON config file.

        Returns:
            Parsed configuration dictionary.
        """
        self._validation_errors = []

        if config_path is None or not os.path.exists(config_path):
            if config_path is not None:
                logger.warning(
                    "MCP config file not found at '%s'. Using default configuration.",
                    config_path,
                )
            else:
                logger.info("No MCP config path specified. Using default configuration.")

            self._config = dict(DEFAULT_MCP_CONFIG)
            self._loaded = True
            logger.info("MCP configuration loaded from defaults")
            return self._config

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                raw_config = json.load(f)

            if not isinstance(raw_config, dict):
                raise ValueError("MCP config root must be a JSON object")

            # Validate structure
            self._validate_config(raw_config)

            if self._validation_errors:
                for error in self._validation_errors:
                    logger.error("MCP config validation error: %s", error)
                logger.warning(
                    "MCP config has %d validation error(s). "
                    "Merging with defaults to fill gaps.",
                    len(self._validation_errors),
                )
                # Merge: defaults first, then user config on top
                raw_config = self._merge_with_defaults(raw_config)

            self._config = raw_config
            self._loaded = True
            logger.info(
                "MCP configuration loaded successfully from '%s'", config_path
            )
            return self._config

        except json.JSONDecodeError as e:
            logger.error(
                "Invalid JSON in MCP config file '%s': %s", config_path, e
            )
            self._validation_errors.append(f"Invalid JSON: {e}")
            self._config = dict(DEFAULT_MCP_CONFIG)
            self._loaded = True
            return self._config

        except Exception as e:
            logger.error(
                "Failed to load MCP config from '%s': %s",
                config_path,
                e,
                exc_info=True,
            )
            self._validation_errors.append(f"Load error: {e}")
            self._config = dict(DEFAULT_MCP_CONFIG)
            self._loaded = True
            return self._config

    def is_mcp_enabled(self) -> bool:
        """
        Check whether MCP integration is enabled in the configuration.

        Returns:
            True if MCP is globally enabled AND the Playwright server entry
            is also enabled. False otherwise.
        """
        global_enabled = (
            self._config.get("global", {}).get("mcp_enabled", True)
        )
        playwright_enabled = (
            self._config
            .get("mcpServers", {})
            .get("playwright", {})
            .get("enabled", True)
        )
        return bool(global_enabled and playwright_enabled)

    def get_playwright_config(self) -> Dict[str, Any]:
        """
        Extract the Playwright MCP server configuration.

        Returns a dictionary suitable for passing directly to ``MCPClient``,
        containing command, args, timeout, autoApprove list, and env vars.

        Returns:
            Playwright server configuration dictionary.
        """
        servers = self._config.get("mcpServers", {})
        pw_config = servers.get("playwright", {})

        if not pw_config:
            logger.warning(
                "No 'playwright' entry in mcpServers. Returning defaults."
            )
            pw_config = DEFAULT_MCP_CONFIG["mcpServers"]["playwright"]

        return {
            "command": pw_config.get("command", "npx"),
            "args": pw_config.get("args", ["-y", "@playwright/mcp-server"]),
            "enabled": pw_config.get("enabled", True),
            "autoApprove": pw_config.get("autoApprove", []),
            "timeout": pw_config.get("timeout", 30000),
            "env": pw_config.get("env", {}),
        }

    def get_auto_approval_settings(self) -> Dict[str, Any]:
        """
        Get tool auto-approval rules from the Playwright server config.

        Returns:
            Dictionary with:
                - ``auto_approve_tools``: list of tool name patterns approved
                  for automatic execution (no user confirmation).
                - ``auto_approve_enabled``: whether auto-approval is active
                  (True when the list is non-empty).
        """
        pw_config = self.get_playwright_config()
        auto_approve_list = pw_config.get("autoApprove", [])

        return {
            "auto_approve_tools": auto_approve_list,
            "auto_approve_enabled": len(auto_approve_list) > 0,
        }

    def get_fallback_config(self) -> Dict[str, Any]:
        """
        Get fallback configuration for when MCP is unavailable.

        Returns:
            Fallback configuration dictionary with ``enabled`` and ``strategy``.
        """
        fallback = self._config.get("fallback", {})
        return {
            "enabled": fallback.get("enabled", True),
            "strategy": fallback.get("strategy", "dom_toolkit"),
        }

    def get_logging_config(self) -> Dict[str, Any]:
        """
        Get MCP logging configuration.

        Returns:
            Logging configuration dictionary with flags for what to log.
        """
        log_cfg = self._config.get("logging", {})
        return {
            "enabled": log_cfg.get("enabled", True),
            "log_tool_calls": log_cfg.get("log_tool_calls", True),
            "log_tool_results": log_cfg.get("log_tool_results", True),
            "log_latency": log_cfg.get("log_latency", True),
            "log_errors": log_cfg.get("log_errors", True),
            "structured_json": log_cfg.get("structured_json", True),
        }

    def get_timeout_ms(self) -> int:
        """
        Get the configured MCP tool execution timeout in milliseconds.

        Returns:
            Timeout in milliseconds (default: 30000).
        """
        pw_config = self.get_playwright_config()
        return int(pw_config.get("timeout", 30000))

    def get_config_version(self) -> str:
        """
        Get the configuration file version string.

        Returns:
            Version string (e.g., '1.0').
        """
        return self._config.get("global", {}).get("config_version", "unknown")

    def get_validation_errors(self) -> List[str]:
        """
        Get any validation errors encountered during config loading.

        Returns:
            List of error description strings (empty if config is valid).
        """
        return list(self._validation_errors)

    @property
    def config_path(self) -> Optional[str]:
        """Path to the loaded configuration file (None if using defaults)."""
        return self._config_path

    @property
    def raw_config(self) -> Dict[str, Any]:
        """Raw configuration dictionary (read-only copy)."""
        return dict(self._config)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_config_path(self, explicit_path: Optional[str]) -> Optional[str]:
        """
        Resolve the MCP config file path.

        Priority:
        1. Explicit path argument
        2. `.kiro/settings/mcp.json` relative to project root

        Args:
            explicit_path: User-supplied path, or None.

        Returns:
            Resolved absolute path, or None if no file can be located.
        """
        if explicit_path:
            resolved = os.path.abspath(explicit_path)
            logger.debug("Using explicit MCP config path: %s", resolved)
            return resolved

        # Walk upward from this file's directory to find the project root
        # containing `.kiro/settings/mcp.json`
        search_dir = Path(__file__).resolve().parent
        for _ in range(10):  # up to 10 levels
            candidate = search_dir / ".kiro" / "settings" / "mcp.json"
            if candidate.exists():
                resolved = str(candidate)
                logger.debug("Auto-discovered MCP config: %s", resolved)
                return resolved
            parent = search_dir.parent
            if parent == search_dir:
                break
            search_dir = parent

        logger.debug("No MCP config file auto-discovered")
        return None

    def _validate_config(self, config: Dict[str, Any]) -> None:
        """
        Validate the structure of a loaded MCP config dictionary.

        Populates ``self._validation_errors`` with any issues found.

        Args:
            config: Parsed JSON config to validate.
        """
        # Check required top-level keys
        for key in _REQUIRED_KEYS:
            if key not in config:
                self._validation_errors.append(
                    f"Missing required top-level key: '{key}'"
                )

        # Validate mcpServers section
        servers = config.get("mcpServers", {})
        if not isinstance(servers, dict):
            self._validation_errors.append(
                "'mcpServers' must be a JSON object"
            )
            return

        # Validate each server entry
        for name, server_cfg in servers.items():
            if not isinstance(server_cfg, dict):
                self._validation_errors.append(
                    f"Server '{name}' config must be a JSON object"
                )
                continue

            for req_key in _REQUIRED_SERVER_KEYS:
                if req_key not in server_cfg:
                    self._validation_errors.append(
                        f"Server '{name}' missing required key: '{req_key}'"
                    )

            # Validate timeout is a positive number
            timeout = server_cfg.get("timeout")
            if timeout is not None:
                if not isinstance(timeout, (int, float)) or timeout <= 0:
                    self._validation_errors.append(
                        f"Server '{name}' timeout must be a positive number, "
                        f"got: {timeout}"
                    )

            # Validate autoApprove is a list of strings
            auto_approve = server_cfg.get("autoApprove")
            if auto_approve is not None:
                if not isinstance(auto_approve, list):
                    self._validation_errors.append(
                        f"Server '{name}' autoApprove must be a list"
                    )
                elif not all(isinstance(item, str) for item in auto_approve):
                    self._validation_errors.append(
                        f"Server '{name}' autoApprove must contain only strings"
                    )

        # Validate global section
        global_cfg = config.get("global", {})
        if not isinstance(global_cfg, dict):
            self._validation_errors.append("'global' must be a JSON object")

        # Validate logging section (optional)
        logging_cfg = config.get("logging")
        if logging_cfg is not None and not isinstance(logging_cfg, dict):
            self._validation_errors.append("'logging' must be a JSON object")

        # Validate fallback section (optional)
        fallback_cfg = config.get("fallback")
        if fallback_cfg is not None and not isinstance(fallback_cfg, dict):
            self._validation_errors.append("'fallback' must be a JSON object")

    def _merge_with_defaults(self, user_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep-merge user config on top of defaults.

        User values take precedence; defaults fill any gaps.

        Args:
            user_config: User-provided configuration dictionary.

        Returns:
            Merged configuration dictionary.
        """
        merged = self._deep_merge(dict(DEFAULT_MCP_CONFIG), user_config)
        return merged

    @staticmethod
    def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively merge ``override`` into ``base``.

        For nested dicts, merging is recursive. For all other types,
        ``override`` values win.

        Args:
            base: Base dictionary (modified in place and returned).
            override: Dictionary whose values take precedence.

        Returns:
            The merged dictionary (same reference as ``base``).
        """
        for key, value in override.items():
            if (
                key in base
                and isinstance(base[key], dict)
                and isinstance(value, dict)
            ):
                MCPConfigManager._deep_merge(base[key], value)
            else:
                base[key] = value
        return base

    def __repr__(self) -> str:
        return (
            f"MCPConfigManager("
            f"path={self._config_path!r}, "
            f"loaded={self._loaded}, "
            f"mcp_enabled={self.is_mcp_enabled()}, "
            f"errors={len(self._validation_errors)})"
        )

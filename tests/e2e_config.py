"""
E2E Test Configuration Module

This module loads and validates YAML-based E2E test profile configurations
for Playwright browser automation tests. SDETs can modify profiles.yaml
without changing source code.
"""

import yaml
import jsonschema
from pathlib import Path
from typing import Dict, Any, List
import sys
import argparse


class E2EConfigError(Exception):
    """Exception raised for E2E configuration errors."""

    pass


class E2EConfig:
    """
    E2E test configuration loader and validator.

    Loads test profiles from YAML files and provides validated configuration
    data for Playwright browser automation tests.
    """

    def __init__(self, config_file: str = "playwright-e2e/profiles.yaml"):
        """
        Initialize E2E configuration.

        Args:
            config_file: Path to the YAML configuration file
        """
        self.config_path = Path(config_file)
        self.schema_path = Path("playwright-e2e/profile-schema.yaml")
        self.config = self._load_and_validate_config()

    def _load_yaml_file(self, file_path: Path) -> Dict[str, Any]:
        """Load and parse a YAML file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            raise E2EConfigError(f"Configuration file not found: {file_path}")
        except yaml.YAMLError as e:
            raise E2EConfigError(f"Invalid YAML in {file_path}: {e}")

    def _load_and_validate_config(self) -> Dict[str, Any]:
        """Load configuration and validate against schema."""
        if not self.config_path.exists():
            raise E2EConfigError(f"E2E configuration file not found: {self.config_path}")

        # Load configuration
        config = self._load_yaml_file(self.config_path)

        # Load and validate schema if available
        if self.schema_path.exists():
            try:
                schema = self._load_yaml_file(self.schema_path)
                jsonschema.validate(config, schema)
            except jsonschema.ValidationError as e:
                raise E2EConfigError(f"Configuration validation failed: {e.message}")
            except Exception as e:
                # Schema validation is optional - continue without it
                print(f"Warning: Could not validate schema: {e}")

        return config

    def get_profiles(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all test profiles.

        Returns:
            Dictionary of profile_name -> profile_config
        """
        return self.config.get("profiles", {})

    def get_profile(self, profile_name: str) -> Dict[str, Any]:
        """
        Get a specific test profile with defaults applied.

        Args:
            profile_name: Name of the profile to retrieve

        Returns:
            Profile configuration dictionary

        Raises:
            E2EConfigError: If profile not found
        """
        profiles = self.get_profiles()
        if profile_name not in profiles:
            available_profiles = list(profiles.keys())
            raise E2EConfigError(f"Profile '{profile_name}' not found. Available profiles: {available_profiles}")

        profile = profiles[profile_name].copy()

        # Apply defaults
        profile.setdefault("timeout_minutes", 10)
        profile.setdefault("description", f"E2E test profile: {profile_name}")

        # Merge browser overrides if present
        browser_overrides = profile.pop("browser_overrides", {})
        if browser_overrides:
            profile["browser_overrides"] = browser_overrides

        return profile

    def get_browser_settings(self, profile_name: str = None) -> Dict[str, Any]:
        """
        Get browser settings, optionally merged with profile overrides.

        Args:
            profile_name: Optional profile name to merge overrides from

        Returns:
            Browser configuration dictionary
        """
        settings = self.config.get("browser_settings", {}).copy()

        # Apply defaults
        defaults = {
            "headless": False,
            "slow_mo": 500,
            "viewport": {"width": 1280, "height": 720},
            "timeout": 60000,
            "screenshot_on_failure": True,
            "video_recording": False,
        }

        for key, default_value in defaults.items():
            settings.setdefault(key, default_value)

        # Apply profile-specific overrides
        if profile_name:
            try:
                profile = self.get_profile(profile_name)
                browser_overrides = profile.get("browser_overrides", {})
                settings.update(browser_overrides)
            except E2EConfigError:
                # Profile not found, use defaults
                pass

        return settings

    def get_page_settings(self) -> Dict[str, Any]:
        """
        Get page interaction settings.

        Returns:
            Page settings dictionary
        """
        settings = self.config.get("page_settings", {}).copy()

        # Apply defaults
        defaults = {"navigation_timeout": 30000, "wait_for_selector_timeout": 10000, "form_submission_timeout": 5000}

        for key, default_value in defaults.items():
            settings.setdefault(key, default_value)

        return settings

    def get_server_settings(self) -> Dict[str, Any]:
        """
        Get server configuration settings.

        Returns:
            Server settings dictionary
        """
        settings = self.config.get("server_settings", {}).copy()

        # Apply defaults
        defaults = {"port": 8002, "startup_timeout": 30, "log_level": "info"}

        for key, default_value in defaults.items():
            settings.setdefault(key, default_value)

        return settings

    def list_profiles(self) -> List[str]:
        """
        Get list of available profile names.

        Returns:
            List of profile names
        """
        return list(self.get_profiles().keys())

    def validate_profile(self, profile_name: str) -> bool:
        """
        Validate a specific profile configuration.

        Args:
            profile_name: Name of profile to validate

        Returns:
            True if profile is valid

        Raises:
            E2EConfigError: If profile is invalid
        """
        profile = self.get_profile(profile_name)

        # Check required fields
        required_fields = ["name", "pdf_file", "model", "detail_level", "concurrency"]
        for field in required_fields:
            if field not in profile:
                raise E2EConfigError(f"Profile '{profile_name}' missing required field: {field}")

        # Validate PDF file exists
        pdf_path = Path("playwright-e2e") / profile["pdf_file"]
        if not pdf_path.exists():
            raise E2EConfigError(f"Profile '{profile_name}' references non-existent PDF: {pdf_path}")

        # Validate detail_level
        if profile["detail_level"] not in ["low", "high"]:
            raise E2EConfigError(f"Profile '{profile_name}' has invalid detail_level: {profile['detail_level']}")

        # Validate concurrency
        concurrency = profile["concurrency"]
        if not isinstance(concurrency, int) or concurrency < 1 or concurrency > 100:
            raise E2EConfigError(f"Profile '{profile_name}' has invalid concurrency: {concurrency}")

        return True

    def get_profile_summary(self, profile_name: str) -> str:
        """
        Get a human-readable summary of a profile.

        Args:
            profile_name: Name of profile to summarize

        Returns:
            Formatted profile summary string
        """
        try:
            profile = self.get_profile(profile_name)
            return (
                f"Profile: {profile_name}\n"
                f"  Name: {profile['name']}\n"
                f"  Description: {profile.get('description', 'No description')}\n"
                f"  PDF File: {profile['pdf_file']}\n"
                f"  Model: {profile['model']}\n"
                f"  Detail Level: {profile['detail_level']}\n"
                f"  Concurrency: {profile['concurrency']}\n"
                f"  Timeout: {profile['timeout_minutes']} minutes"
            )
        except E2EConfigError as e:
            return f"Error loading profile '{profile_name}': {e}"


def main():
    """Command-line interface for E2E configuration management."""
    parser = argparse.ArgumentParser(description="E2E Test Configuration Manager")
    parser.add_argument("--list", action="store_true", help="List all available profiles")
    parser.add_argument("--validate", action="store_true", help="Validate all profiles")
    parser.add_argument("--profile", help="Show details for specific profile")
    parser.add_argument("--dry-run", action="store_true", help="Validate profile without running test")

    args = parser.parse_args()

    try:
        config = E2EConfig()

        if args.list:
            profiles = config.list_profiles()
            if profiles:
                print("Available E2E test profiles:")
                for profile_name in profiles:
                    profile = config.get_profile(profile_name)
                    print(f"  {profile_name}: {profile['name']}")
            else:
                print("No E2E test profiles configured.")
                return 1

        elif args.validate:
            profiles = config.list_profiles()
            if not profiles:
                print("No profiles to validate.")
                return 1

            all_valid = True
            for profile_name in profiles:
                try:
                    config.validate_profile(profile_name)
                    print(f"✓ Profile '{profile_name}' is valid")
                except E2EConfigError as e:
                    print(f"✗ Profile '{profile_name}' is invalid: {e}")
                    all_valid = False

            return 0 if all_valid else 1

        elif args.profile:
            if args.dry_run:
                try:
                    config.validate_profile(args.profile)
                    print(f"✓ Profile '{args.profile}' is valid and ready to run")
                    return 0
                except E2EConfigError as e:
                    print(f"✗ Profile '{args.profile}' is invalid: {e}")
                    return 1
            else:
                print(config.get_profile_summary(args.profile))

        else:
            parser.print_help()
            return 1

    except E2EConfigError as e:
        print(f"Configuration error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

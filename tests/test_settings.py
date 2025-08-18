import pathlib
import tempfile
import unittest

from jasmin_homedir_manager.settings import DataEndpoints, Settings


class TestSettings(unittest.TestCase):
    def test_settings_loads_from_test_fixture(self):
        """Test that settings can be loaded from a fixture TOML file."""
        fixture_path = pathlib.Path(__file__).parent / "fixtures" / "test_settings.toml"

        settings = Settings.from_toml(fixture_path)

        self.assertEqual(settings.client_id, "test_client_id")
        self.assertEqual(settings.client_secret, "test_client_secret")
        self.assertEqual(settings.scopes, ["test.scope.read", "test.scope.write"])
        self.assertEqual(
            settings.token_endpoint, "https://test.example.com/oauth/token/"
        )
        self.assertEqual(settings.home_dir_folder, pathlib.Path("/tmp/test_home"))
        self.assertEqual(
            settings.data_endpoints.users, "https://test.example.com/api/v1/users/"
        )

    def test_settings_validation_missing_required_fields(self):
        """Test that settings validation fails when required fields are missing."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", delete=False
        ) as temp_file:
            temp_file.write(
                """
client_id = "test_client_id"
# Missing client_secret and other required fields
"""
            )
            temp_file.flush()

            with self.assertRaises(Exception):
                Settings.from_toml(temp_file.name)

    def test_settings_data_endpoints_validation(self):
        """Test that DataEndpoints validation works correctly."""
        data_endpoints = DataEndpoints(users="https://example.com/users/")
        self.assertEqual(data_endpoints.users, "https://example.com/users/")

        with self.assertRaises(Exception):
            DataEndpoints()

    def test_settings_missing_file_raises_error(self):
        """Test that when settings file is missing, it raises an appropriate error."""
        with self.assertRaises(Exception):
            Settings.from_toml("nonexistent.toml")

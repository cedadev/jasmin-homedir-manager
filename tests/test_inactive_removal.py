"""Tests for the inactive account removal command."""

import datetime
import json
import pathlib
import shutil
import tempfile
import unittest
import unittest.mock

from jasmin_homedir_manager.commands.inactive_removal import \
    InactiveRemovalCommand
from jasmin_homedir_manager.settings import Settings


class TestInactiveRemovalCommand(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Load API response fixtures once for all tests."""
        fixtures_path = (
            pathlib.Path(__file__).parent / "fixtures" / "api_responses.json"
        )
        with open(fixtures_path) as f:
            cls.api_fixtures = json.load(f)

    def setUp(self):
        """Create fake filesystem for testing removal process."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_home_dir = pathlib.Path(self.temp_dir) / "home" / "users"
        self.temp_home_dir.mkdir(parents=True)
        self.temp_pending_deletion_dir = (
            pathlib.Path(self.temp_dir) / "home" / "users" / ".pending_deletion"
        )
        self.temp_pending_deletion_dir.mkdir(parents=True)

        self.test_settings = Settings(
            client_id="test_client",
            client_secret="test_secret",
            scopes=["test.scope"],
            token_endpoint="https://test.example.com/oauth/token/",
            home_dir_folder=self.temp_home_dir,
            pending_deletion_folder=self.temp_pending_deletion_dir,
            pending_deletion_inactive_days=455,
            removal_inactive_days=547,
            data_endpoints={"users": "https://test.example.com/api/users/"},
        )

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir)

    def create_test_pending_deletion_directory(self, username: str) -> pathlib.Path:
        """Create a test user directory in pending deletion."""
        user_dir = self.temp_pending_deletion_dir / username
        user_dir.mkdir()
        (user_dir / "test_file.txt").write_text("test content")
        (user_dir / "test_dir").mkdir()
        (user_dir / "test_dir" / "nested_file.txt").write_text("nested content")
        return user_dir

    def get_mock_api_response(self, fixture_key: str, homeDirectory=None):
        """Get mock API response from fixture."""
        response_data = self.api_fixtures[fixture_key].copy()

        if homeDirectory is not None:
            response_data["account"]["homeDirectory"] = homeDirectory
        return response_data

    def test_execute_with_inactive_users_success(self):
        """Test successful removal of inactive users from pending deletion."""
        removal_user1_dir = self.create_test_pending_deletion_directory("removal001")
        removal_user2_dir = self.create_test_pending_deletion_directory("removal002")

        users_list_response = self.get_mock_api_response("users_list_inactive_removal")

        user_detail_removal001 = self.get_mock_api_response(
            "user_detail_removal001",
            homeDirectory=str(self.temp_home_dir / "removal001"),
        )
        user_detail_removal002 = self.get_mock_api_response(
            "user_detail_removal002",
            homeDirectory=str(self.temp_home_dir / "removal002"),
        )

        command = InactiveRemovalCommand(
            self.test_settings, dry_run=False, careful=False
        )

        with unittest.mock.patch.object(
            command, "get_authenticated_client"
        ) as mock_get_client:
            mock_client = unittest.mock.MagicMock()
            mock_get_client.return_value = mock_client

            mock_client.get.side_effect = [
                unittest.mock.MagicMock(json=lambda: users_list_response),
                unittest.mock.MagicMock(json=lambda: user_detail_removal001),
                unittest.mock.MagicMock(json=lambda: user_detail_removal002),
            ]

            command.execute()

            self.assertFalse(removal_user1_dir.exists())
            self.assertFalse(removal_user2_dir.exists())

            expected_patch_calls = [
                unittest.mock.call(
                    "https://test.example.com/api/users/removal001/",
                    data={"lifecycle_state": "ACCNT_DEL_HOME_REMOVED"},
                ),
                unittest.mock.call(
                    "https://test.example.com/api/users/removal002/",
                    data={"lifecycle_state": "ACCNT_DEL_HOME_REMOVED"},
                ),
            ]
            mock_client.patch.assert_has_calls(expected_patch_calls, any_order=True)

    def test_execute_with_dry_run_mode(self):
        """Test dry run mode doesn't make actual changes."""
        removal_user_dir = self.create_test_pending_deletion_directory("removal001")

        users_list_response = self.get_mock_api_response(
            "users_list_single_inactive_removal"
        )
        user_detail_response = self.get_mock_api_response(
            "user_detail_removal001",
            homeDirectory=str(self.temp_home_dir / "removal001"),
        )

        command = InactiveRemovalCommand(
            self.test_settings, dry_run=True, careful=False
        )

        with unittest.mock.patch.object(
            command, "get_authenticated_client"
        ) as mock_get_client:
            mock_client = unittest.mock.MagicMock()
            mock_get_client.return_value = mock_client

            mock_client.get.side_effect = [
                unittest.mock.MagicMock(json=lambda: users_list_response),
                unittest.mock.MagicMock(json=lambda: user_detail_response),
            ]

            command.execute()

            self.assertTrue(removal_user_dir.exists())
            self.assertTrue((removal_user_dir / "test_file.txt").exists())

            mock_client.patch.assert_not_called()

    def test_execute_skips_recently_deactivated_users(self):
        """Test that recently deactivated users are skipped."""
        removal_user_dir = self.create_test_pending_deletion_directory("removal003")

        users_list_response = [
            {
                "username": "removal003",
                "url": "https://test.example.com/api/users/removal003/",
            }
        ]
        user_detail_response = self.get_mock_api_response(
            "user_detail_removal_recently"
        )

        command = InactiveRemovalCommand(
            self.test_settings, dry_run=False, careful=False
        )

        with unittest.mock.patch.object(
            command, "get_authenticated_client"
        ) as mock_get_client:
            mock_client = unittest.mock.MagicMock()
            mock_get_client.return_value = mock_client

            mock_client.get.side_effect = [
                unittest.mock.MagicMock(json=lambda: users_list_response),
                unittest.mock.MagicMock(json=lambda: user_detail_response),
            ]

            command.execute()

            self.assertTrue(removal_user_dir.exists())

            mock_client.patch.assert_not_called()

    def test_execute_skips_nonexistent_pending_deletion_directory(self):
        """Test that users with non-existent pending deletion directories are skipped."""
        users_list_response = self.get_mock_api_response(
            "users_list_single_inactive_removal"
        )
        user_detail_response = self.get_mock_api_response(
            "user_detail_removal_nonexistent_pending"
        )

        command = InactiveRemovalCommand(
            self.test_settings, dry_run=False, careful=False
        )

        with unittest.mock.patch.object(
            command, "get_authenticated_client"
        ) as mock_get_client:
            mock_client = unittest.mock.MagicMock()
            mock_get_client.return_value = mock_client

            mock_client.get.side_effect = [
                unittest.mock.MagicMock(json=lambda: users_list_response),
                unittest.mock.MagicMock(json=lambda: user_detail_response),
            ]

            command.execute()

            mock_client.patch.assert_not_called()

    def test_confirm_user_removal_careful_mode_yes(self):
        """Test user confirmation in careful mode when user says yes."""
        command = InactiveRemovalCommand(
            self.test_settings, dry_run=False, careful=True
        )

        user = {"username": "removal001"}
        pending_deletion_dir = pathlib.Path("/home/users/.pending_deletion/removal001")

        with unittest.mock.patch("click.prompt", return_value="yes"):
            result = command.confirm_operation(
                f"User: {user['username']}\nPending Deletion Directory: {pending_deletion_dir}",
                "removal",
            )
            self.assertTrue(result)

    def test_confirm_user_removal_careful_mode_skip(self):
        """Test user confirmation in careful mode when user says skip."""
        command = InactiveRemovalCommand(
            self.test_settings, dry_run=False, careful=True
        )

        user = {"username": "removal001"}
        pending_deletion_dir = pathlib.Path("/home/users/.pending_deletion/removal001")

        with unittest.mock.patch("click.prompt", return_value="skip"):
            result = command.confirm_operation(
                f"User: {user['username']}\nPending Deletion Directory: {pending_deletion_dir}",
                "removal",
            )
            self.assertFalse(result)

    def test_confirm_user_removal_careful_mode_abort(self):
        """Test user confirmation in careful mode when user says abort."""
        import click

        command = InactiveRemovalCommand(
            self.test_settings, dry_run=False, careful=True
        )

        user = {"username": "removal001"}
        pending_deletion_dir = pathlib.Path("/home/users/.pending_deletion/removal001")

        with unittest.mock.patch("click.prompt", return_value="abort"):
            with self.assertRaises(click.Abort):
                command.confirm_operation(
                    f"User: {user['username']}\nPending Deletion Directory: {pending_deletion_dir}",
                    "removal",
                )

    def test_confirm_user_removal_not_careful_mode(self):
        """Test user confirmation when not in careful mode."""
        command = InactiveRemovalCommand(
            self.test_settings, dry_run=False, careful=False
        )

        user = {"username": "removal001"}
        pending_deletion_dir = pathlib.Path("/home/users/.pending_deletion/removal001")

        result = command.confirm_operation(
            f"User: {user['username']}\nPending Deletion Directory: {pending_deletion_dir}",
            "removal",
        )
        self.assertTrue(result)

    def test_execute_with_careful_mode_skip(self):
        """Test that removal is skipped when user chooses skip in careful mode."""
        removal_user_dir = self.create_test_pending_deletion_directory("removal001")

        users_list_response = self.get_mock_api_response(
            "users_list_single_inactive_removal"
        )
        user_detail_response = self.get_mock_api_response(
            "user_detail_removal001",
            homeDirectory=str(self.temp_home_dir / "removal001"),
        )

        command = InactiveRemovalCommand(
            self.test_settings, dry_run=False, careful=True
        )

        with unittest.mock.patch.object(
            command, "get_authenticated_client"
        ) as mock_get_client:
            mock_client = unittest.mock.MagicMock()
            mock_get_client.return_value = mock_client

            mock_client.get.side_effect = [
                unittest.mock.MagicMock(json=lambda: users_list_response),
                unittest.mock.MagicMock(json=lambda: user_detail_response),
            ]

            with unittest.mock.patch("click.prompt", return_value="skip"):
                command.execute()

                self.assertTrue(removal_user_dir.exists())

                mock_client.patch.assert_not_called()

"""Tests for the inactive account pending deletion command."""

import datetime
import json
import pathlib
import shutil
import tempfile
import unittest
import unittest.mock

from jasmin_homedir_manager.commands.inactive_pending_deletion import \
    InactivePendingDeletionCommand
from jasmin_homedir_manager.settings import Settings


class TestInactivePendingDeletionCommand(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Load API response fixtures once for all tests."""
        fixtures_path = (
            pathlib.Path(__file__).parent / "fixtures" / "api_responses.json"
        )
        with open(fixtures_path) as f:
            cls.api_fixtures = json.load(f)

    def setUp(self):
        """Create fake filesystem for testing pending deletion process."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_home_dir = pathlib.Path(self.temp_dir) / "home" / "users"
        self.temp_home_dir.mkdir(parents=True)
        self.temp_pending_deletion_dir = (
            pathlib.Path(self.temp_dir) / "home" / "users" / ".pending_deletion"
        )

        self.test_settings = Settings(
            client_id="test_client",
            client_secret="test_secret",
            scopes=["test.scope"],
            token_endpoint="https://test.example.com/oauth/token/",
            home_dir_folder=self.temp_home_dir,
            pending_deletion_folder=self.temp_pending_deletion_dir,
            pending_deletion_inactive_days=365,
            removal_inactive_days=547,
            data_endpoints={"users": "https://test.example.com/api/users/"},
        )

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir)

    def create_test_user_home_directory(self, username: str) -> pathlib.Path:
        """Create a test user home directory."""
        user_home = self.temp_home_dir / username
        user_home.mkdir()
        (user_home / "test_file.txt").write_text("test content")
        (user_home / "test_dir").mkdir()
        (user_home / "test_dir" / "nested_file.txt").write_text("nested content")
        return user_home

    def get_mock_api_response(self, fixture_key: str, homeDirectory=None):
        """Get mock API response from fixture."""
        response_data = self.api_fixtures[fixture_key].copy()

        if homeDirectory is not None:
            response_data["account"]["homeDirectory"] = homeDirectory
        return response_data

    def make_mock_passwd_entry(self, shell: str = "/usr/sbin/nologin"):
        """Create a fake passwd entry with the given shell."""
        mock_entry = unittest.mock.MagicMock()
        mock_entry.pw_shell = shell
        return mock_entry

    def test_execute_with_inactive_users_success(self):
        """Test successful pending deletion of inactive users."""
        inactive_user1_home = self.create_test_user_home_directory("inactive001")
        inactive_user2_home = self.create_test_user_home_directory("inactive002")

        users_list_response = self.get_mock_api_response(
            "users_list_inactive_pending_deletion"
        )

        user_detail_inactive001 = self.get_mock_api_response(
            "user_detail_inactive001", homeDirectory=str(inactive_user1_home)
        )
        user_detail_inactive002 = self.get_mock_api_response(
            "user_detail_inactive002", homeDirectory=str(inactive_user2_home)
        )

        command = InactivePendingDeletionCommand(
            self.test_settings, dry_run=False, careful=False
        )

        with unittest.mock.patch.object(
            command, "get_authenticated_client"
        ) as mock_get_client, unittest.mock.patch(
            "pwd.getpwnam", return_value=self.make_mock_passwd_entry()
        ):
            mock_client = unittest.mock.MagicMock()
            mock_get_client.return_value = mock_client

            mock_client.get.side_effect = [
                unittest.mock.MagicMock(json=lambda: users_list_response),
                unittest.mock.MagicMock(json=lambda: user_detail_inactive001),
                unittest.mock.MagicMock(json=lambda: user_detail_inactive002),
            ]

            command.execute()

            self.assertFalse(inactive_user1_home.exists())
            self.assertFalse(inactive_user2_home.exists())

            pending_deletion_user1 = self.temp_pending_deletion_dir / "inactive001"
            pending_deletion_user2 = self.temp_pending_deletion_dir / "inactive002"
            self.assertTrue(pending_deletion_user1.exists())
            self.assertTrue(pending_deletion_user2.exists())
            self.assertTrue((pending_deletion_user1 / "test_file.txt").exists())
            self.assertTrue((pending_deletion_user2 / "test_file.txt").exists())

            expected_patch_calls = [
                unittest.mock.call(
                    "https://test.example.com/api/users/inactive001/",
                    data={"lifecycle_state": "ACCNT_DEL_HOME_MOVED"},
                ),
                unittest.mock.call(
                    "https://test.example.com/api/users/inactive002/",
                    data={"lifecycle_state": "ACCNT_DEL_HOME_MOVED"},
                ),
            ]
            mock_client.patch.assert_has_calls(expected_patch_calls, any_order=True)

    def test_execute_with_dry_run_mode(self):
        """Test dry run mode doesn't make actual changes."""
        inactive_user_home = self.create_test_user_home_directory("inactive001")

        users_list_response = self.get_mock_api_response(
            "users_list_single_inactive_pending_deletion"
        )
        user_detail_response = self.get_mock_api_response(
            "user_detail_inactive001", homeDirectory=str(inactive_user_home)
        )

        command = InactivePendingDeletionCommand(
            self.test_settings, dry_run=True, careful=False
        )

        with unittest.mock.patch.object(
            command, "get_authenticated_client"
        ) as mock_get_client, unittest.mock.patch(
            "pwd.getpwnam", return_value=self.make_mock_passwd_entry()
        ):
            mock_client = unittest.mock.MagicMock()
            mock_get_client.return_value = mock_client

            mock_client.get.side_effect = [
                unittest.mock.MagicMock(json=lambda: users_list_response),
                unittest.mock.MagicMock(json=lambda: user_detail_response),
            ]

            command.execute()

            self.assertTrue(inactive_user_home.exists())
            self.assertTrue((inactive_user_home / "test_file.txt").exists())

            self.assertFalse(self.temp_pending_deletion_dir.exists())

            mock_client.patch.assert_not_called()

    def test_execute_skips_recently_deactivated_users(self):
        """Test that recently deactivated users are skipped."""
        inactive_user_home = self.create_test_user_home_directory("inactive003")

        users_list_response = [
            {
                "username": "inactive003",
                "url": "https://test.example.com/api/users/inactive003/",
            }
        ]
        user_detail_response = self.get_mock_api_response(
            "user_detail_inactive_recently", homeDirectory=str(inactive_user_home)
        )

        command = InactivePendingDeletionCommand(
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

            self.assertTrue(inactive_user_home.exists())

            self.assertFalse(self.temp_pending_deletion_dir.exists())

            mock_client.patch.assert_not_called()

    def test_execute_skips_mismatched_home_directory(self):
        """Test that users with mismatched home directories are skipped."""
        inactive_user_home = self.create_test_user_home_directory("inactive001")

        users_list_response = self.get_mock_api_response(
            "users_list_single_inactive_pending_deletion"
        )
        user_detail_response = self.get_mock_api_response(
            "user_detail_inactive_mismatched_home"
        )

        command = InactivePendingDeletionCommand(
            self.test_settings, dry_run=False, careful=False
        )

        with unittest.mock.patch.object(
            command, "get_authenticated_client"
        ) as mock_get_client, unittest.mock.patch(
            "pwd.getpwnam", return_value=self.make_mock_passwd_entry()
        ):
            mock_client = unittest.mock.MagicMock()
            mock_get_client.return_value = mock_client

            mock_client.get.side_effect = [
                unittest.mock.MagicMock(json=lambda: users_list_response),
                unittest.mock.MagicMock(json=lambda: user_detail_response),
            ]

            command.execute()

            self.assertTrue(inactive_user_home.exists())

            mock_client.patch.assert_not_called()

    def test_execute_skips_nonexistent_home_directory(self):
        """Test that users with non-existent home directories are skipped."""
        users_list_response = self.get_mock_api_response(
            "users_list_single_inactive_pending_deletion"
        )

        nonexistent_home = self.temp_home_dir / "inactive001"
        user_detail_response = self.get_mock_api_response(
            "user_detail_inactive_nonexistent_home",
            homeDirectory=str(nonexistent_home),
        )

        command = InactivePendingDeletionCommand(
            self.test_settings, dry_run=False, careful=False
        )

        with unittest.mock.patch.object(
            command, "get_authenticated_client"
        ) as mock_get_client, unittest.mock.patch(
            "pwd.getpwnam", return_value=self.make_mock_passwd_entry()
        ):
            mock_client = unittest.mock.MagicMock()
            mock_get_client.return_value = mock_client

            mock_client.get.side_effect = [
                unittest.mock.MagicMock(json=lambda: users_list_response),
                unittest.mock.MagicMock(json=lambda: user_detail_response),
            ]

            command.execute()

            mock_client.patch.assert_not_called()

    def test_execute_skips_user_not_in_passwd(self):
        """Test that users not found in passwd are skipped."""
        inactive_user_home = self.create_test_user_home_directory("inactive001")

        users_list_response = self.get_mock_api_response(
            "users_list_single_inactive_pending_deletion"
        )
        user_detail_response = self.get_mock_api_response(
            "user_detail_inactive001", homeDirectory=str(inactive_user_home)
        )

        command = InactivePendingDeletionCommand(
            self.test_settings, dry_run=False, careful=False
        )

        with unittest.mock.patch.object(
            command, "get_authenticated_client"
        ) as mock_get_client, unittest.mock.patch(
            "pwd.getpwnam", side_effect=KeyError("inactive001")
        ):
            mock_client = unittest.mock.MagicMock()
            mock_get_client.return_value = mock_client

            mock_client.get.side_effect = [
                unittest.mock.MagicMock(json=lambda: users_list_response),
                unittest.mock.MagicMock(json=lambda: user_detail_response),
            ]

            command.execute()

            self.assertTrue(inactive_user_home.exists())

            mock_client.patch.assert_not_called()

    def test_execute_skips_user_with_non_nologin_shell(self):
        """Test that users whose shell is not /usr/sbin/nologin are skipped."""
        inactive_user_home = self.create_test_user_home_directory("inactive001")

        users_list_response = self.get_mock_api_response(
            "users_list_single_inactive_pending_deletion"
        )
        user_detail_response = self.get_mock_api_response(
            "user_detail_inactive001", homeDirectory=str(inactive_user_home)
        )

        command = InactivePendingDeletionCommand(
            self.test_settings, dry_run=False, careful=False
        )

        with unittest.mock.patch.object(
            command, "get_authenticated_client"
        ) as mock_get_client, unittest.mock.patch(
            "pwd.getpwnam",
            return_value=self.make_mock_passwd_entry(shell="/bin/bash"),
        ):
            mock_client = unittest.mock.MagicMock()
            mock_get_client.return_value = mock_client

            mock_client.get.side_effect = [
                unittest.mock.MagicMock(json=lambda: users_list_response),
                unittest.mock.MagicMock(json=lambda: user_detail_response),
            ]

            command.execute()

            self.assertTrue(inactive_user_home.exists())

            mock_client.patch.assert_not_called()

    def test_confirm_user_operation_careful_mode_yes(self):
        """Test user confirmation in careful mode when user says yes."""
        command = InactivePendingDeletionCommand(
            self.test_settings, dry_run=False, careful=True
        )

        user = {"username": "inactive001"}
        home_dir = pathlib.Path("/home/users/inactive001")

        with unittest.mock.patch("click.prompt", return_value="yes"):
            result = command.confirm_operation(
                f"User: {user['username']}\nHome Directory: {home_dir}",
                "pending deletion",
            )
            self.assertTrue(result)

    def test_confirm_user_operation_careful_mode_skip(self):
        """Test user confirmation in careful mode when user says skip."""
        command = InactivePendingDeletionCommand(
            self.test_settings, dry_run=False, careful=True
        )

        user = {"username": "inactive001"}
        home_dir = pathlib.Path("/home/users/inactive001")

        with unittest.mock.patch("click.prompt", return_value="skip"):
            result = command.confirm_operation(
                f"User: {user['username']}\nHome Directory: {home_dir}",
                "pending deletion",
            )
            self.assertFalse(result)

    def test_confirm_user_operation_careful_mode_abort(self):
        """Test user confirmation in careful mode when user says abort."""
        import click

        command = InactivePendingDeletionCommand(
            self.test_settings, dry_run=False, careful=True
        )

        user = {"username": "inactive001"}
        home_dir = pathlib.Path("/home/users/inactive001")

        with unittest.mock.patch("click.prompt", return_value="abort"):
            with self.assertRaises(click.Abort):
                command.confirm_operation(
                    f"User: {user['username']}\nHome Directory: {home_dir}",
                    "pending deletion",
                )

    def test_confirm_user_operation_not_careful_mode(self):
        """Test user confirmation when not in careful mode."""
        command = InactivePendingDeletionCommand(
            self.test_settings, dry_run=False, careful=False
        )

        user = {"username": "inactive001"}
        home_dir = pathlib.Path("/home/users/inactive001")

        result = command.confirm_operation(
            f"User: {user['username']}\nHome Directory: {home_dir}",
            "pending deletion",
        )
        self.assertTrue(result)

    def test_execute_with_careful_mode_skip(self):
        """Test that pending deletion is skipped when user chooses skip in careful mode."""
        inactive_user_home = self.create_test_user_home_directory("inactive001")

        users_list_response = self.get_mock_api_response(
            "users_list_single_inactive_pending_deletion"
        )
        user_detail_response = self.get_mock_api_response(
            "user_detail_inactive001", homeDirectory=str(inactive_user_home)
        )

        command = InactivePendingDeletionCommand(
            self.test_settings, dry_run=False, careful=True
        )

        with unittest.mock.patch.object(
            command, "get_authenticated_client"
        ) as mock_get_client, unittest.mock.patch(
            "pwd.getpwnam", return_value=self.make_mock_passwd_entry()
        ):
            mock_client = unittest.mock.MagicMock()
            mock_get_client.return_value = mock_client

            mock_client.get.side_effect = [
                unittest.mock.MagicMock(json=lambda: users_list_response),
                unittest.mock.MagicMock(json=lambda: user_detail_response),
            ]

            with unittest.mock.patch("click.prompt", return_value="skip"):
                command.execute()

                self.assertTrue(inactive_user_home.exists())

                mock_client.patch.assert_not_called()

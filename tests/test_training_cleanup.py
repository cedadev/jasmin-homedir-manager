"""Tests for the training account cleanup command."""

import json
import pathlib
import shutil
import tempfile
import unittest
import unittest.mock

from jasmin_homedir_manager.commands.training_cleanup import TrainingCleanupCommand
from jasmin_homedir_manager.settings import Settings


class TestTrainingCleanupCommand(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Load API response fixtures once for all tests."""
        fixtures_path = (
            pathlib.Path(__file__).parent / "fixtures" / "api_responses.json"
        )
        with open(fixtures_path) as f:
            cls.api_fixtures = json.load(f)

    def setUp(self):
        """Create fake filesystem for testing deletion process."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_home_dir = pathlib.Path(self.temp_dir) / "home" / "users"
        self.temp_home_dir.mkdir(parents=True)
        self.temp_fast_remove = self.temp_home_dir / ".fast-remove"
        self.temp_fast_remove.mkdir()

        self.test_settings = Settings(
            client_id="test_client",
            client_secret="test_secret",
            scopes=["test.scope"],
            token_endpoint="https://test.example.com/oauth/token/",
            home_dir_folder=self.temp_home_dir,
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

        # Allow overriding home directory location.
        if homeDirectory is not None:
            response_data["account"]["homeDirectory"] = homeDirectory
        return response_data

    def test_execute_with_training_users_success(self):
        """Test successful cleanup of training users."""
        train_user1_home = self.create_test_user_home_directory("train001")
        train_user2_home = self.create_test_user_home_directory("train002")

        # Get mock API responses from fixtures
        users_list_response = self.get_mock_api_response("users_list_training")

        user_detail_train001 = self.get_mock_api_response(
            "user_detail_train001", homeDirectory=str(train_user1_home)
        )
        user_detail_train002 = self.get_mock_api_response(
            "user_detail_train002", homeDirectory=str(train_user2_home)
        )

        command = TrainingCleanupCommand(
            self.test_settings, dry_run=False, careful=False
        )

        with unittest.mock.patch.object(
            command, "get_authenticated_client"
        ) as mock_get_client:
            mock_client = unittest.mock.MagicMock()
            mock_get_client.return_value = mock_client

            # Mock the initial users list request
            mock_client.get.side_effect = [
                unittest.mock.MagicMock(json=lambda: users_list_response),
                unittest.mock.MagicMock(json=lambda: user_detail_train001),
                unittest.mock.MagicMock(json=lambda: user_detail_train002),
            ]

            with unittest.mock.patch("subprocess.run") as mock_subprocess:
                command.execute()

                # Verify directories were moved to .fast-remove
                self.assertFalse(train_user1_home.exists())
                self.assertFalse(train_user2_home.exists())

                # Verify subprocess calls to create new home directories
                expected_calls = [
                    unittest.mock.call(
                        ["/usr/sbin/mkhomedir_helper", "train001"], check=False
                    ),
                    unittest.mock.call(
                        ["/usr/sbin/mkhomedir_helper", "train002"], check=False
                    ),
                ]
                mock_subprocess.assert_has_calls(expected_calls, any_order=True)

                # Verify API calls to update user lifecycle state
                expected_patch_calls = [
                    unittest.mock.call(
                        "https://test.example.com/api/users/train001/",
                        data={"lifecycle_state": "NORMAL"},
                    ),
                    unittest.mock.call(
                        "https://test.example.com/api/users/train002/",
                        data={"lifecycle_state": "NORMAL"},
                    ),
                ]
                mock_client.patch.assert_has_calls(expected_patch_calls, any_order=True)

    def test_execute_with_dry_run_mode(self):
        """Test dry run mode doesn't make actual changes."""
        train_user_home = self.create_test_user_home_directory("train001")

        users_list_response = self.get_mock_api_response("users_list_single_training")
        user_detail_response = self.get_mock_api_response(
            "user_detail_train001", homeDirectory=str(train_user_home)
        )

        command = TrainingCleanupCommand(
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

            with unittest.mock.patch("subprocess.run") as mock_subprocess:
                command.execute()

                # Verify directories still exist (not moved)
                self.assertTrue(train_user_home.exists())
                self.assertTrue((train_user_home / "test_file.txt").exists())

                # Verify no subprocess calls were made
                mock_subprocess.assert_not_called()

                # Verify no API patch calls were made
                mock_client.patch.assert_not_called()

    def test_execute_skips_non_training_users(self):
        """Test that non-training users are skipped."""
        regular_user_home = self.create_test_user_home_directory("regularuser")

        users_list_response = self.get_mock_api_response("users_list_non_training")
        user_detail_response = self.get_mock_api_response(
            "user_detail_regularuser", homeDirectory=str(regular_user_home)
        )

        command = TrainingCleanupCommand(
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

            with unittest.mock.patch("subprocess.run") as mock_subprocess:
                command.execute()

                # Verify directory still exists (not cleaned up)
                self.assertTrue(regular_user_home.exists())

                # Verify no subprocess or patch calls
                mock_subprocess.assert_not_called()
                mock_client.patch.assert_not_called()

    def test_execute_skips_mismatched_home_directory(self):
        """Test that users with mismatched home directories are skipped."""
        train_user_home = self.create_test_user_home_directory("train001")

        users_list_response = self.get_mock_api_response("users_list_single_training")
        user_detail_response = self.get_mock_api_response("user_detail_mismatched_home")

        command = TrainingCleanupCommand(
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

            with unittest.mock.patch("subprocess.run") as mock_subprocess:
                command.execute()

                # Verify directory still exists (not cleaned up)
                self.assertTrue(train_user_home.exists())

                # Verify no subprocess or patch calls
                mock_subprocess.assert_not_called()
                mock_client.patch.assert_not_called()

    def test_execute_skips_nonexistent_home_directory(self):
        """Test that users with non-existent home directories are skipped."""
        users_list_response = self.get_mock_api_response("users_list_single_training")

        # Home directory path is correct but doesn't exist
        nonexistent_home = self.temp_home_dir / "train001"
        user_detail_response = self.get_mock_api_response(
            "user_detail_nonexistent_home", homeDirectory=str(nonexistent_home)
        )

        command = TrainingCleanupCommand(
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

            with unittest.mock.patch("subprocess.run") as mock_subprocess:
                command.execute()

                # Verify no subprocess or patch calls
                mock_subprocess.assert_not_called()
                mock_client.patch.assert_not_called()

    def test_confirm_user_cleanup_careful_mode_yes(self):
        """Test user confirmation in careful mode when user says yes."""
        command = TrainingCleanupCommand(
            self.test_settings, dry_run=False, careful=True
        )

        user = {"username": "train001"}
        home_dir = pathlib.Path("/home/users/train001")

        with unittest.mock.patch("click.prompt", return_value="yes"):
            result = command.confirm_user_cleanup(user, home_dir, careful=True)
            self.assertTrue(result)

    def test_confirm_user_cleanup_careful_mode_skip(self):
        """Test user confirmation in careful mode when user says skip."""
        command = TrainingCleanupCommand(
            self.test_settings, dry_run=False, careful=True
        )

        user = {"username": "train001"}
        home_dir = pathlib.Path("/home/users/train001")

        with unittest.mock.patch("click.prompt", return_value="skip"):
            result = command.confirm_user_cleanup(user, home_dir, careful=True)
            self.assertFalse(result)

    def test_confirm_user_cleanup_careful_mode_abort(self):
        """Test user confirmation in careful mode when user says abort."""
        import click

        command = TrainingCleanupCommand(
            self.test_settings, dry_run=False, careful=True
        )

        user = {"username": "train001"}
        home_dir = pathlib.Path("/home/users/train001")

        with unittest.mock.patch("click.prompt", return_value="abort"):
            with self.assertRaises(click.Abort):
                command.confirm_user_cleanup(user, home_dir, careful=True)

    def test_confirm_user_cleanup_not_careful_mode(self):
        """Test user confirmation when not in careful mode."""
        command = TrainingCleanupCommand(
            self.test_settings, dry_run=False, careful=False
        )

        user = {"username": "train001"}
        home_dir = pathlib.Path("/home/users/train001")

        result = command.confirm_user_cleanup(user, home_dir, careful=False)
        self.assertTrue(result)

    def test_execute_with_careful_mode_skip(self):
        """Test that cleanup is skipped when user chooses skip in careful mode."""
        train_user_home = self.create_test_user_home_directory("train001")

        users_list_response = self.get_mock_api_response("users_list_single_training")
        user_detail_response = self.get_mock_api_response(
            "user_detail_train001", homeDirectory=str(train_user_home)
        )

        command = TrainingCleanupCommand(
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
                with unittest.mock.patch("subprocess.run") as mock_subprocess:
                    command.execute()

                    # Verify directory still exists (not cleaned up)
                    self.assertTrue(train_user_home.exists())

                    # Verify no subprocess or patch calls
                    mock_subprocess.assert_not_called()
                    mock_client.patch.assert_not_called()

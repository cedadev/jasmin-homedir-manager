"""Training account cleanup command."""

import pathlib
import shutil
import subprocess

import click

from .base import BaseCommand
from .path_security import validate_path_containment, validate_username


class TrainingCleanupCommand(BaseCommand):
    """Command to clean up training user accounts."""

    def execute(self) -> None:
        """Execute the training account cleanup."""
        client = self.get_authenticated_client()

        # Get a list of all training users which need to be cleaned up from the accounts portal.
        response = client.get(
            self.settings.data_endpoints.users,
            headers={"Accept": "application/json"},
            params={
                "user_type": "TRAINING",
                "lifecycle_state": "AWAITING_CLEANUP",
                "is_active": "false",
            },
        )

        # Iterate through the users doing the cleanup.
        for user in response.json():
            # Get the more detailed view of the user, so we can lookup where LDAP thinks the home directory is.
            response = client.get(user["url"])
            user_detailed = response.json()

            username = user_detailed["username"]

            if not validate_username(username):
                self.logger.critical(
                    "Username validation failed for %s, username contains invalid characters or path traversal sequences.",
                    username,
                )
                continue

            # Get the home directory from LDAP, and also guess the home directory path from the username.
            home_directory = pathlib.Path(user_detailed["account"]["homeDirectory"])
            home_directory_constructed = self.settings.home_dir_folder / username

            # Check user is training account.
            if not username.startswith("train"):
                self.logger.critical(
                    "Did nothing for %s, since the username does not start with train.",
                    username,
                )
            # Check home path matches that expected.
            elif home_directory != home_directory_constructed:
                self.logger.error(
                    "Home directory path check failed for %s. Home directory in LDAP (%s) did not match expected (%s)",
                    username,
                    home_directory,
                    home_directory_constructed,
                )
            elif not validate_path_containment(
                home_directory_constructed, self.settings.home_dir_folder
            ):
                self.logger.error(
                    "Path containment validation failed for %s. Resolved path (%s) is not within expected directory (%s)",
                    username,
                    home_directory_constructed.resolve(),
                    self.settings.home_dir_folder.resolve(),
                )
            # Check home directory is a directory.
            elif not home_directory_constructed.is_dir():
                self.logger.error("Home directory did not exist for %s", username)
            elif home_directory_constructed.is_symlink():
                self.logger.error(
                    "Home directory is a symlink for %s. This is not allowed for security reasons.",
                    username,
                )
            # Check if careful mode is enabled and confirm with user.
            elif not self.confirm_operation(
                f"User: {username}\nHome Directory: {home_directory_constructed}",
                "cleanup",
            ):
                self.logger.error(
                    "Careful mode enabled and user asked to skip %s", username
                )
            else:
                # This is the main logic.
                self.logger.info(
                    "Removing home directory %s", home_directory_constructed
                )

                if self.dry_run:
                    click.echo(f"[DRY RUN] Would remove {home_directory_constructed}")
                    click.echo(f"[DRY RUN] Would create empty home for {username}")
                    click.echo(f"[DRY RUN] Would update {username} to DORMANT state")
                else:
                    shutil.rmtree(home_directory_constructed)

                    # Make an empty home directory.
                    subprocess.run(
                        ["/usr/sbin/mkhomedir_helper", username], check=False
                    )

                    # Mark the user as dormant in the portal.
                    response = client.patch(
                        user["url"], data={"lifecycle_state": "DORMANT"}
                    )

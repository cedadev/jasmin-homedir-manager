"""Inactive account removal command."""

import datetime
import pathlib
import shutil

import click

from .base import BaseCommand
from .path_security import validate_path_containment, validate_username


class InactiveRemovalCommand(BaseCommand):
    """Command to remove inactive user accounts from pending deletion."""

    def execute(self) -> None:
        """Execute the inactive account removal."""
        client = self.get_authenticated_client()

        response = client.get(
            self.settings.data_endpoints.users,
            headers={"Accept": "application/json"},
            params={
                "user_type": "STANDARD",
                "lifecycle_state": "ACCNT_DEL_HOME_MOVED",
                "is_active": "false",
            },
        )

        for user in response.json():
            response = client.get(user["url"])
            user_detailed = response.json()

            username = user_detailed["username"]

            if not validate_username(username):
                self.logger.error(
                    "Username validation failed for %s, username contains invalid characters or path traversal sequences.",
                    username,
                )
                continue

            deactivated_at = datetime.datetime.fromisoformat(
                user_detailed["deactivated_at"].replace("Z", "+00:00")
            )
            days_inactive = (datetime.datetime.now(datetime.UTC) - deactivated_at).days

            if days_inactive < self.settings.removal_inactive_days:
                self.logger.info(
                    "Skipping %s, only inactive for %d days (threshold: %d)",
                    username,
                    days_inactive,
                    self.settings.removal_inactive_days,
                )
                continue

            home_directory = pathlib.Path(user_detailed["account"]["homeDirectory"])
            home_directory_constructed = self.settings.home_dir_folder / username
            pending_deletion_directory = (
                self.settings.pending_deletion_folder / username
            )

            if home_directory != home_directory_constructed:
                self.logger.error(
                    "Home directory path check failed for %s. Home directory in LDAP (%s) did not match expected (%s)",
                    username,
                    home_directory,
                    home_directory_constructed,
                )
            elif not validate_path_containment(
                pending_deletion_directory, self.settings.pending_deletion_folder
            ):
                self.logger.error(
                    "Path containment validation failed for %s. Resolved path (%s) is not within expected directory (%s)",
                    username,
                    pending_deletion_directory.resolve(),
                    self.settings.pending_deletion_folder.resolve(),
                )
            elif not pending_deletion_directory.is_dir():
                self.logger.error(
                    "Pending deletion directory did not exist for %s", username
                )
            elif pending_deletion_directory.is_symlink():
                self.logger.error(
                    "Pending deletion directory is a symlink for %s. This is not allowed for security reasons.",
                    username,
                )
            elif not self.confirm_operation(
                f"User: {username}\nPending Deletion Directory: {pending_deletion_directory}",
                "home directory removal",
            ):
                self.logger.error(
                    "Careful mode enabled and user asked to skip %s", username
                )
            else:
                self.logger.info(
                    "Removing pending deletion directory %s", pending_deletion_directory
                )

                if self.dry_run:
                    click.echo(f"[DRY RUN] Would remove {pending_deletion_directory}")
                    click.echo(
                        f"[DRY RUN] Would update {username} to ACCNT_DEL_HOME_REMOVED state"
                    )
                else:
                    shutil.rmtree(pending_deletion_directory)

                    response = client.patch(
                        user["url"], data={"lifecycle_state": "ACCNT_DEL_HOME_REMOVED"}
                    )

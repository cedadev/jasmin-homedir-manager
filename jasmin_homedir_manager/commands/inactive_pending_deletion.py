"""Inactive account pending deletion command."""

import datetime
import pathlib
import shutil

import click

from .base import BaseCommand
from .path_security import validate_path_containment, validate_username


class InactivePendingDeletionCommand(BaseCommand):
    """Command to move inactive home directories to pending deletion folder."""

    def execute(self) -> None:
        """Execute the inactive account pending deletion."""
        client = self.get_authenticated_client()

        response = client.get(
            self.settings.data_endpoints.users,
            headers={"Accept": "application/json"},
            params={
                "user_type": "STANDARD",
                "lifecycle_state": "ACCNT_DEL_NOTIFIED",
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

            if days_inactive < self.settings.pending_deletion_inactive_days:
                self.logger.info(
                    "Skipping %s, only inactive for %d days (threshold: %d)",
                    username,
                    days_inactive,
                    self.settings.pending_deletion_inactive_days,
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
                home_directory_constructed, self.settings.home_dir_folder
            ):
                self.logger.error(
                    "Path containment validation failed for %s. Resolved path (%s) is not within expected directory (%s)",
                    username,
                    home_directory_constructed.resolve(),
                    self.settings.home_dir_folder.resolve(),
                )
            elif not validate_path_containment(
                pending_deletion_directory, self.settings.pending_deletion_folder
            ):
                self.logger.error(
                    "Destination path containment validation failed for %s. Resolved path (%s) is not within expected directory (%s)",
                    username,
                    pending_deletion_directory.resolve(),
                    self.settings.pending_deletion_folder.resolve(),
                )
            elif not home_directory_constructed.is_dir():
                self.logger.error("Home directory did not exist for %s", username)
            elif home_directory_constructed.is_symlink():
                self.logger.error(
                    "Home directory is a symlink for %s. This is not allowed for security reasons.",
                    username,
                )
            elif pending_deletion_directory.exists():
                self.logger.error(
                    "Destination already exists for %s at %s. Cannot move to avoid data collision.",
                    username,
                    pending_deletion_directory,
                )
            elif not self.confirm_operation(
                f"User: {username}\nHome Directory: {home_directory_constructed}",
                "home directory move",
            ):
                self.logger.error(
                    "Careful mode enabled and user asked to skip %s", username
                )
            else:
                self.logger.info(
                    "Moving home directory %s to pending deletion",
                    home_directory_constructed,
                )

                if self.dry_run:
                    click.echo(
                        f"[DRY RUN] Would move {home_directory_constructed} to {pending_deletion_directory}"
                    )
                    click.echo(
                        f"[DRY RUN] Would update {username} to ACCNT_DEL_HOME_MOVED state"
                    )
                else:
                    self.settings.pending_deletion_folder.mkdir(
                        parents=True, exist_ok=True
                    )
                    shutil.move(
                        str(home_directory_constructed), str(pending_deletion_directory)
                    )

                    response = client.patch(
                        user["url"], data={"lifecycle_state": "ACCNT_DEL_HOME_MOVED"}
                    )

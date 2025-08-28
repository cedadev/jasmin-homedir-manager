"""Training account cleanup command."""

import pathlib
import shutil
import subprocess

import click

from .base import BaseCommand


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

            # Get the home directory from LDAP, and also guess the home directory path from the username.
            home_directory = pathlib.Path(user_detailed["account"]["homeDirectory"])
            home_directory_constructed = (
                self.settings.home_dir_folder / user_detailed["username"]
            )

            # Check user is training account.
            if not user["username"].startswith("train"):
                self.logger.critical(
                    "Did nothing for %s, since the username does not start with train.",
                    user["username"],
                )
            # Check home path matches that expected.
            elif home_directory != home_directory_constructed:
                self.logger.error(
                    "Home directory path check failed for %s. Home directory in LDAP (%s) did not match expected (%s)",
                    user["username"],
                    home_directory,
                    home_directory_constructed,
                )
            # Check home directory is a directory.
            elif not home_directory.is_dir():
                self.logger.error(
                    "Home directory did not exist for %s", user["username"]
                )
            # Check if careful mode is enabled and confirm with user.
            elif not self.confirm_user_cleanup(user, home_directory, self.careful):
                self.logger.error(
                    "Careful mode enabled and user asked to skip %s", user["username"]
                )
            else:
                # This is the main logic.
                self.logger.info("Removing home directory %s", home_directory)

                if self.dry_run:
                    click.echo(f"[DRY RUN] Would move {home_directory} to .fast-remove")
                    click.echo(
                        f"[DRY RUN] Would create empty home for {user['username']}"
                    )
                    click.echo(
                        f"[DRY RUN] Would update {user['username']} to NORMAL state"
                    )
                else:
                    # Do the delete
                    shutil.rmtree(home_directory)

                    # Make an empty home directory.
                    subprocess.run(
                        ["/usr/sbin/mkhomedir_helper", user["username"]], check=False
                    )

                    # Mark the user as dormant in the portal.
                    response = client.patch(
                        user["url"], data={"lifecycle_state": "NORMAL"}
                    )

    def confirm_user_cleanup(
        self, user: dict, home_dir: pathlib.Path, careful: bool
    ) -> bool:
        """Safe confirmation for user cleanup operations."""
        if not careful:
            return True

        click.echo(f"\n{'='*50}")
        click.echo(f"User: {user['username']}")
        click.echo(f"Home Directory: {home_dir}")
        click.echo(f"{'='*50}")

        # Require typing "yes" for destructive operations
        confirmation: str = click.prompt(
            "Type 'yes' to proceed with cleanup, 'skip' to skip, or 'abort' to exit",
            type=click.Choice(["yes", "skip", "abort"], case_sensitive=False),
        )

        if confirmation == "abort":
            click.echo("Operation aborted by user")
            raise click.Abort()

        return confirmation == "yes"

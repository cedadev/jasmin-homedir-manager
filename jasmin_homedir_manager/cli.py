"""CLI entry point."""

import logging

import click

from .commands import training_cleanup
from .settings import Settings


@click.group()
@click.option(
    "--settings-file",
    type=click.Path(exists=True),
    help="Path to settings TOML file",
    default="settings.toml",
)
@click.option(
    "--dry-run/--no-dry-run",
    default=True,
    help="Show what would be done without executing",
)
@click.option(
    "--careful/--no-careful",
    is_flag=True,
    default=True,
    help="Prompt before each operation",
)
@click.pass_context
def cli(ctx: click.Context, settings_file: str, dry_run: bool, careful: bool) -> None:
    """JASMIN Home Directory Manager."""
    ctx.ensure_object(dict)
    ctx.obj["settings_file"] = settings_file
    ctx.obj["dry_run"] = dry_run
    ctx.obj["careful"] = careful

    logging.basicConfig(
        level=logging.INFO,
    )

    # Reduce httpx log noise
    logging.getLogger("httpx").setLevel(logging.ERROR)

    if dry_run:
        click.echo("DRY RUN MODE: No actual changes will be made")


@cli.command()
@click.pass_context
def cleanup_training_accounts(ctx: click.Context) -> None:
    """Clean up training user accounts."""
    settings = Settings.from_toml(ctx.obj["settings_file"])

    command = training_cleanup.TrainingCleanupCommand(
        settings=settings,
        dry_run=ctx.obj["dry_run"],
        careful=ctx.obj["careful"],
    )
    command.execute()


if __name__ == "__main__":
    cli()

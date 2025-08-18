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
    "--dry-run",
    is_flag=True,
    help="Show what would be done without executing",
)
@click.option(
    "--careful",
    is_flag=True,
    help="Prompt before each operation",
)
@click.pass_context
def cli(ctx, settings_file, dry_run, careful):
    """JASMIN Home Directory Manager."""
    ctx.ensure_object(dict)
    ctx.obj["settings_file"] = settings_file
    ctx.obj["dry_run"] = dry_run
    ctx.obj["careful"] = careful

    logging.basicConfig(
        level=logging.INFO,
    )

    if dry_run:
        click.echo("DRY RUN MODE: No actual changes will be made")


@cli.command()
@click.pass_context
def cleanup_training_accounts(ctx):
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

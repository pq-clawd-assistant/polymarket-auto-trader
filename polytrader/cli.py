import asyncio

import typer

from polytrader.runner import run_forever, run_once

app = typer.Typer(no_args_is_help=True)


@app.command()
def once():
    """Run one scan/decision/execute cycle."""
    asyncio.run(run_once())


@app.command()
def run():
    """Run forever (sleeping between cycles)."""
    asyncio.run(run_forever())

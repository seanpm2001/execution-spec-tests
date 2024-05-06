"""
CLI entry points for the main pytest-based commands provided by
execution-spec-tests.

These can be directly accessed in a prompt if the user has directly installed
the package via:

```
python -m venv venv
source venv/bin/activate
pip install -e .
# or
pip install -e .[doc,lint,test]
```

Then, the entry points can be executed via:

```
fill --help
# for example, or
fill --collect-only
```

They can also be executed (and debugged) directly in an interactive python
shell:

```
from src.cli.pytest_commands import fill
from click.testing import CliRunner

runner = CliRunner()
result = runner.invoke(fill, ["--help"])
print(result.output)
```
"""

import sys
from typing import Any, Callable, List

import click
import pytest

# Define a custom type for decorators, which are functions that return functions.
Decorator = Callable[[Callable[..., Any]], Callable[..., Any]]


@click.command(context_settings=dict(ignore_unknown_options=True))
def tf() -> None:
    """
    The `tf` command, deprecated as of 2023-06.
    """
    print(
        "The `tf` command-line tool has been superseded by `fill`. Try:\n\n"
        "fill --help\n\n"
        "or see the online docs:\n"
        "https://ethereum.github.io/execution-spec-tests/getting_started/executing_tests_command_line/"  # noqa: E501
    )
    sys.exit(1)


def common_click_options(func: Callable[..., Any]) -> Decorator:
    """
    Define common click options for fill and other pytest-based commands.

    Note that we don't verify any other options here, rather pass them
    directly to the pytest command for processing.
    """
    func = click.option(
        "-h",
        "--help",
        "help_flag",
        is_flag=True,
        default=False,
        expose_value=True,
        help="Show help message.",
    )(func)

    func = click.option(
        "--pytest-help",
        "pytest_help_flag",
        is_flag=True,
        default=False,
        expose_value=True,
        help="Show pytest's help message.",
    )(func)

    func = click.option(
        "--no-html",
        "no_html_flag",
        is_flag=True,
        default=False,
        expose_value=True,
        help="Do not generate pytest's HTML report.",
    )(func)

    func = click.option(
        "--html",
        "pytest_html_path",
        type=str,
        default=None,
        expose_value=True,
        help="Generate pytest's HTML report.",
    )(func)

    func = click.option(
        "--output",
        "output_path",
        type=str,
        default=None,
        expose_value=True,
        help="Fixture output path.",
    )(func)

    return click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)(func)


def handle_help_flags(
    pytest_args: List[str], help_flag: bool, pytest_help_flag: bool
) -> List[str]:
    """
    Modifies the help arguments passed to the click CLI command before forwarding to
    the pytest command.

    This is to make `--help` more useful because `pytest --help` is extremely
    verbose and lists all flags from pytest and pytest plugins.
    """
    if help_flag:
        return ["--test-help"]
    elif pytest_help_flag:
        return ["--help"]
    else:
        return list(pytest_args)


def default_fill_output_directory() -> str:
    """
    Returns the default output directory used for the fill command.
    """
    return "fixtures"


def default_html_report_name(command="fill") -> str:
    """
    Returns the default HTML report path used for the fill command.
    """
    if command == "fill":
        return "report_fill.html"
    raise ValueError(f"Unknown command: {command}")


def handle_html_report_flags(
    pytest_args: List[str],
    no_html_flag: bool,
    pytest_html_path: str,
    output_path: str,
) -> List[str]:
    """
    Modifies the html report arguments passed to the click CLI command before forwarding to
    the pytest command.

    This is to achieve the following behavior by default:

    1. If no flags are passed, write the html report to the default output
        directory.
    2. If an output directory is passed, write the html report to that directory.
    """
    if no_html_flag:
        return list(pytest_args) + [f"--output={default_fill_output_directory()}"]
    if output_path and pytest_html_path:
        return list(pytest_args) + [
            f"--html={pytest_html_path}",
            f"--output={output_path}",
        ]
    if pytest_html_path:
        return list(pytest_args) + [
            f"--html={pytest_html_path}",
            f"--output={default_fill_output_directory()}",
        ]
    if output_path:
        return list(pytest_args) + [
            f"--html={output_path}/{default_html_report_name('fill')}",
            f"--output={output_path}",
        ]
    # use default options for both
    return list(pytest_args) + [
        f"--html={default_fill_output_directory()}/{default_html_report_name('fill')}",
        f"--output={default_fill_output_directory()}",
    ]


@click.command(context_settings=dict(ignore_unknown_options=True))
@common_click_options
def fill(
    pytest_args: List[str],
    help_flag: bool,
    pytest_help_flag: bool,
    no_html_flag: bool,
    pytest_html_path: str,
    output_path: str,
) -> None:
    """
    Entry point for the fill command.
    """
    updated_args = handle_help_flags(pytest_args, help_flag, pytest_help_flag)
    final_args = handle_html_report_flags(
        updated_args, no_html_flag, pytest_html_path, output_path
    )
    result = pytest.main(final_args)
    sys.exit(result)

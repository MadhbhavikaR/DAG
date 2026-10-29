"""Tests for the example CLI."""


def test_package_imports() -> None:
    """The package should expose a version."""
    from dag_template_python import __version__

    assert __version__ == "0.1.0"


def test_main(capsys) -> None:
    """The CLI should print a helpful greeting."""
    from dag_template_python.cli import main

    main()

    captured = capsys.readouterr()
    assert captured.out == "Hello from dag-template-python!\n"

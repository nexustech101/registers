import pytest

import functionals.cli as cli
from functionals.cli import CommandExecutionError


@pytest.fixture(autouse=True)
def _reset_registry():
    cli.reset_registry()
    yield
    cli.reset_registry()


class TestCliErrorHandling:
    def test_run_wraps_unhandled_handler_exception(self):
        @cli.register(description="Boom")
        @cli.option("--boom")
        def boom() -> None:
            raise RuntimeError("boom")

        with pytest.raises(CommandExecutionError, match="Command 'boom' failed: boom"):
            cli.run(["boom"], print_result=False)

    def test_parse_error_exits_with_code_2(self):
        @cli.register(description="Add")
        @cli.option("--add")
        @cli.argument("x", type=int)
        def add(x: int) -> int:
            return x + 1

        with pytest.raises(SystemExit) as exc:
            cli.run(["add", "not-an-int"], print_result=False)

        assert exc.value.code == 2

    def test_empty_argv_prints_help_menu(self, capsys, monkeypatch):
        class _PipeLikeStdin:
            def isatty(self) -> bool:
                return False

        monkeypatch.setattr("functionals.cli.registry.sys.stdin", _PipeLikeStdin())

        @cli.register(description="Noop")
        @cli.option("--noop")
        def noop() -> None:
            return None

        assert cli.run([], print_result=False) is None
        out = capsys.readouterr().out
        assert "Decorates CLI" in out
        assert "Shell builtins" in out
        assert "Registered commands" in out

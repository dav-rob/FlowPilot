import json
import os
import sys
import pytest
from flowpilot.config import load_local_env
from flowpilot.models import _run_process


def test_local_configuration_loads_without_overriding_exported_values(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("TYPESAFE_API_KEY", "existing-test-key")
    monkeypatch.delenv("JEV_MODEL", raising=False)
    monkeypatch.delenv("FLOWPILOT_MAX_ITERATIONS", raising=False)
    path = tmp_path / ".env"
    path.write_text(
        '# Local config\nTYPESAFE_API_KEY=local-test-key\nexport JEV_MODEL="test-model" # comment\nFLOWPILOT_MAX_ITERATIONS=9\nHOME=/unrelated\n'
    )
    original_home = os.environ.get("HOME")
    load_local_env(path)
    assert os.environ["TYPESAFE_API_KEY"] == "existing-test-key"
    assert os.environ["JEV_MODEL"] == "test-model"
    assert os.environ["FLOWPILOT_MAX_ITERATIONS"] == "9"
    assert os.environ.get("HOME") == original_home


def test_local_configuration_does_not_expand_or_execute_values(tmp_path, monkeypatch):
    monkeypatch.delenv("JEV_MODEL", raising=False)
    path = tmp_path / ".env"
    path.write_text("JEV_MODEL='$(touch should-never-exist)'\n")
    load_local_env(path)
    assert os.environ["JEV_MODEL"] == "$(touch should-never-exist)"
    assert not (tmp_path / "should-never-exist").exists()


def test_configuration_errors_never_echo_secret_values(tmp_path):
    path = tmp_path / ".env"
    path.write_text('TYPESAFE_API_KEY="dummy-unclosed-secret\n')
    with pytest.raises(ValueError) as exc:
        load_local_env(path)
    assert "dummy-unclosed-secret" not in str(exc.value)
    assert "line 1" in str(exc.value)
    load_local_env(tmp_path / "missing.env")


def test_cli_children_do_not_receive_jev_credentials(tmp_path):
    outcome = _run_process(
        [
            sys.executable,
            "-c",
            'import json,os; print(json.dumps({k: k in os.environ for k in ["TYPESAFE_API_KEY","JEV_API_KEY","FLOWPILOT_MAX_ITERATIONS"]}))',
        ],
        cwd=tmp_path,
        env={
            **os.environ,
            "TYPESAFE_API_KEY": "dummy-primary-key",
            "JEV_API_KEY": "dummy-alias-key",
            "FLOWPILOT_MAX_ITERATIONS": "9",
        },
        timeout=5,
    )
    assert outcome.code == 0
    assert json.loads(outcome.stdout) == {
        "TYPESAFE_API_KEY": False,
        "JEV_API_KEY": False,
        "FLOWPILOT_MAX_ITERATIONS": True,
    }

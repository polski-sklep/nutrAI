"""A mis-typed model id must stop the process, not quietly mis-price a month.

`llm.client.price()` falls back to Sonnet's rate for a model it does not
recognise. That is correct there — raising after the API call has been made
would throw away a parse that has already been paid for — but it means a typo
in a model id surfaces only as a `/spend` total that is wrong by an unknown
factor. The check therefore runs at import, before anything can be spent.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from nutrai import config


def test_the_shipped_configuration_is_priced():
    config._check_models_are_priced()


def test_a_bogus_id_is_rejected():
    with pytest.raises(ValueError, match="not present in config.PRICES"):
        config._check_models_are_priced({"MODEL_CHEAP": "claude-haiku-9-9-does-not-exist"})


def test_the_error_names_the_setting_and_the_value():
    """A message that does not say which of the five is wrong is not much help."""
    with pytest.raises(ValueError) as exc:
        config._check_models_are_priced(
            {"MODEL_PLAN": "typo-opus", "MODEL_TEXT": config.MODEL_TEXT}
        )
    assert "MODEL_PLAN" in str(exc.value)
    assert "typo-opus" in str(exc.value)
    # The correctly-configured one is not blamed.
    assert "MODEL_TEXT" not in str(exc.value)


def test_every_priced_model_passes():
    for mid in config.PRICES:
        config._check_models_are_priced({"MODEL_X": mid})


def test_import_of_config_fails_with_a_bogus_id():
    """The real contract: importing the module raises, so the bot cannot start.

    Run in a subprocess. Reloading config in-process would leave every module
    that did `from .config import ...` holding references into a half-built
    module, and the failure would land in an unrelated test later.
    """
    proc = subprocess.run(
        [sys.executable, "-c", "import nutrai.config"],
        env={"PATH": "/usr/bin:/bin", "MODEL_CHEAP": "not-a-real-model", "PYTHONPATH": "."},
        capture_output=True,
        text=True,
        check=False,  # a non-zero exit is the whole point
    )
    assert proc.returncode != 0, "a bogus model id let the process start"
    assert "not present in config.PRICES" in proc.stderr
    assert "MODEL_CHEAP" in proc.stderr


def test_import_of_config_succeeds_with_the_defaults():
    proc = subprocess.run(
        [sys.executable, "-c", "import nutrai.config"],
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": "."},
        capture_output=True,
        text=True,
        check=False,  # assert on the code so a failure prints stderr
    )
    assert proc.returncode == 0, proc.stderr

#
# This is pytest plugin providing fixtures for tests.
#

import importlib
from contextlib import contextmanager, ExitStack
from typing import ContextManager, Iterator
from unittest.mock import patch

import pytest


@contextmanager
def nested(*contexts) -> Iterator[list]:
    with ExitStack() as stack:
        yield [stack.enter_context(context) for context in contexts]


def _patches(*args, prefix: str = "") -> ContextManager:
    """Takes a list of module/class paths to patch and an optional prefix

    The prefix is used to prefix all of the paths

    The patches are applied in a nested set of context managers.

    The yields (mocks) are yielded as a tuple.
    """

    patched = []
    prefix = f"{prefix}." if prefix else ""
    for arg in args:
        if isinstance(arg, (list, tuple)):
            path, kwargs = arg
            patched.append(patch(f"{prefix}{path}", **kwargs))
        else:
            patched.append(patch(f"{prefix}{arg}"))
    return nested(*patched)


@pytest.fixture
def patches():
    return _patches


def _pytest_target(module_path):
    module = importlib.import_module(module_path)

    with patch(f"{module_path}.python_pytest") as m_pytest:
        module.main("arg1", "arg2", "arg3")

    assert (
        list(m_pytest.main.call_args)
        == [('arg1', 'arg2', 'arg3', '--cov', ".".join(module_path.split(".")[:-1])), {}])


@pytest.fixture
def check_pytest_target():
    return _pytest_target

import pytest

from pyvst import SimpleHost


def _find_test_synths():
    return _find_test_plugins('.test_synths_paths.txt')


def _find_test_effects():
    return _find_test_plugins('.test_effects_paths.txt')


def _find_test_plugins(paths_file):
    """
        One plugin path per line in a file
        """
    with open('.test_synth_paths.txt') as f:
        path = f.read().strip()

    lines = path.split('\n')
    lines = [x.strip() for x in lines]
    lines = [x for x in lines if not x.startswith('#')]
    return lines


_VST_SYNTHS = _find_test_synths()
_VST_EFFECTS = _find_test_effects()


@pytest.fixture(params=_VST_SYNTHS)
def vst_synths(request):
    return request.param


@pytest.fixture(params=_VST_EFFECTS)
def vst_effects(request):
    return request.param


@pytest.fixture()
def host(vst_synths):
    """SimpleHost containing a loaded synth vst."""
    host = SimpleHost(vst_synths)
    return host

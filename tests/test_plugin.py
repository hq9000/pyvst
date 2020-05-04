# import numpy as np

from pyvst import VstPlugin, SimpleHost


def test_plugin(vst_synth_path):
    vst = VstPlugin(vst_synth_path)
    assert vst.num_params > 0

    # All the vsts we test are synths
    assert vst.is_synth


def test_get_set_param(vst_synth_path):
    vst = VstPlugin(vst_synth_path)
    vst.set_param_value(0, 1.)
    assert vst.get_param_value(0) == 1.
    vst.set_param_value(0, .2)
    assert (vst.get_param_value(0) - .2) / 2. < 0.00001


def test_open_close(vst_synth_path):
    vst = VstPlugin(vst_synth_path)
    vst.open()
    vst.close()


def test_segfault(vst_synth_path):
    """
    Reproducing a weird segfault.
    It segfaults with numpy>=1.14 ... no idea why.
    """
    host = SimpleHost()

    vst = VstPlugin(vst_synth_path, host._callback)
    vst.set_sample_rate(44100.)
    vst.set_block_size(512)

    import numpy as np
    print(np.ones(shape=(1, 1)))
    vst.process(sample_frames=512)


def test_process_replacing_effect(vst_effect_path):
    host = SimpleHost()
    vst = VstPlugin(vst_effect_path, host._callback)

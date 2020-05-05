import contextlib
from ctypes import (cdll, POINTER, c_double,
                    c_void_p, c_int, c_float, c_int32,
                    byref, string_at, create_string_buffer)
from warnings import warn

import numpy as np
from wurlitzer import pipes

from .vstwrap import (
    AudioMasterOpcodes,
    AEffect,
    AEffectOpcodes,
    AUDIO_MASTER_CALLBACK_TYPE,
    vst_int_ptr,
    VstPinProperties,
    VstParameterProperties,
    VstPlugCategory,
    VstAEffectFlags,
)

# define kEffectMagic CCONST ('V', 's', 't', 'P')
# or: MAGIC = int.from_bytes(b'VstP', 'big')
MAGIC = 1450406992


def _default_audio_master_callback(effect, opcode, *args):
    """Version naive audio master callback. This mimicks more than minimal host."""
    if opcode == AudioMasterOpcodes.audioMasterVersion:
        return 2400
    return 0


class VstPlugin:
    def __init__(self, filename, audio_master_callback=None, verbose=False):
        """
        :param verbose: Set to True to show the plugin's stdout/stderr. By default (False),
            we capture it.
        """
        self.verbose = verbose

        if audio_master_callback is None:
            audio_master_callback = _default_audio_master_callback
        self._lib = cdll.LoadLibrary(filename)

        functions_to_try = [
            'VSTPluginMain',
            'main'
        ]

        entry_function = None
        for name in functions_to_try:
            if hasattr(self._lib, name):
                entry_function = getattr(self._lib, name)
                break

        assert entry_function is not None, "None of the supported entry functions found in " + filename

        entry_function.argtypes = [AUDIO_MASTER_CALLBACK_TYPE]
        entry_function.restype = POINTER(AEffect)

        with pipes() if not verbose else contextlib.suppress():
            self._effect = entry_function(AUDIO_MASTER_CALLBACK_TYPE(
                audio_master_callback)).contents

        assert self._effect.magic == MAGIC

        if self.vst_version != 2400:
            warn('This plugin is not a VST2.4 plugin.')

    def open(self):
        self._dispatch(AEffectOpcodes.effOpen)

    def close(self):
        self._dispatch(AEffectOpcodes.effClose)

    def resume(self):
        self._dispatch(AEffectOpcodes.effMainsChanged, value=1)

    def suspend(self):
        self._dispatch(AEffectOpcodes.effMainsChanged, value=0)

    def _dispatch(self, opcode, index=0, value=0, ptr=None, opt=0.):
        if ptr is None:
            ptr = c_void_p()
        with pipes() if not self.verbose else contextlib.suppress():
            output = self._effect.dispatcher(byref(self._effect), c_int32(opcode), c_int32(index),
                                             vst_int_ptr(value), ptr, c_float(opt))
        return output

    # Parameters
    #
    @property
    def num_params(self):
        return self._effect.num_params

    def _get_param_attr(self, index, opcode):
        # It should be VstStringConstants.kVstMaxParamStrLen == 8 but I've encountered some VST
        # with more that would segfault.
        buf = create_string_buffer(64)
        self._dispatch(opcode, index=index, ptr=byref(buf))
        return string_at(buf).decode()

    def get_param_name(self, index):
        return self._get_param_attr(index, AEffectOpcodes.effGetParamName)

    def get_param_label(self, index):
        return self._get_param_attr(index, AEffectOpcodes.effGetParamLabel)

    def get_param_display(self, index):
        return self._get_param_attr(index, AEffectOpcodes.effGetParamDisplay)

    def get_param_value(self, index):
        return self._effect.get_parameter(byref(self._effect), c_int(index))

    def set_param_value(self, index, value):
        self._effect.set_parameter(byref(self._effect), index, value)

    def get_param_properties(self, index):
        props = VstParameterProperties()
        self._dispatch(AEffectOpcodes.effGetParameterProperties, index=index, ptr=byref(props))
        return props

    @property
    def vst_version(self):
        return self._dispatch(AEffectOpcodes.effGetVstVersion)

    @property
    def num_inputs(self):
        return self._effect.num_inputs

    @property
    def num_outputs(self):
        return self._effect.num_outputs

    @property
    def num_midi_in(self):
        return self._dispatch(AEffectOpcodes.effGetNumMidiInputChannels)

    @property
    def num_midi_out(self):
        return self._dispatch(AEffectOpcodes.effGetNumMidiOutputChannels)

    def get_input_properties(self, index):
        props = VstPinProperties()
        is_supported = self._dispatch(AEffectOpcodes.effGetInputProperties, index=index,
                                      ptr=byref(props))
        props.is_supported = is_supported
        return props

    def get_output_properties(self, index):
        props = VstPinProperties()
        is_supported = self._dispatch(AEffectOpcodes.effGetOutputProperties, index=index, ptr=byref(props))
        props.is_supported = is_supported
        return props

    @property
    def plug_category(self):
        return VstPlugCategory(self._dispatch(AEffectOpcodes.effGetPlugCategory))

    # Processing
    #

    def _allocate_array(self, shape, c_type):
        """
        as the first param
        accepts an array or a tuple of exactly two integers.
        1. the first will be considered as number of channels (2 = left and right)
        2. the second is the length of the buffer

        the second param is the the sample data type
        """
        assert len(shape) == 2
        insides = [(c_type * shape[1])() for i in range(shape[0])]
        out = (POINTER(c_type) * shape[0])(*insides)
        return out

    def process_replacing(self, outputs, inputs=None):
        """
        given two numpy ndarrays, writes some data into outputs.
        Importantly, does not allocate any buffers, everything is expected to be
        provided by the caller

        :type inputs: np.ndarray|None
        :type outputs: np.ndarray

        :return: None
        """
        if inputs is not None:
            assert inputs.dtype == outputs.dtype
            assert inputs.shape[0] == self.num_inputs
            assert outputs.shape[0] == self.num_outputs

        if outputs.dtype == np.float32:
            is_double = False
        elif outputs.dtype == np.float64:
            is_double = True
        else:
            raise ValueError("requested processing precision is neither float32 nor float64")

        if is_double and not self.can_double_replacing:
            raise ValueError("float64 processing requested but this plugin does not support it")

        if is_double:
            c_type = c_double
            process_fn = self._effect.process_double_replacing
        else:
            c_type = c_float
            process_fn = self._effect.process_replacing

        sample_frames = inputs.shape[1]
        inputs_as_ctypes = (POINTER(c_type) * self.num_inputs)(*[row.ctypes.data_as(POINTER(c_type))
                                                                 for row in inputs])
        outputs_as_ctypes = (POINTER(c_type) * self.num_outputs)(*[row.ctypes.data_as(POINTER(c_type))
                                                                   for row in outputs])

        with pipes() if not self.verbose else contextlib.suppress():
            process_fn(
                byref(self._effect),
                inputs_as_ctypes,
                outputs_as_ctypes,
                sample_frames,
            )

        pass

    def process(self, input=None, sample_frames=None, double=None):

        if double is None:
            if input is not None:
                double = input.dtype == np.float64
            else:
                double = self.can_double_replacing

        if double:
            c_type = c_double
            process_fn = self._effect.process_double_replacing
        else:
            c_type = c_float
            process_fn = self._effect.process_replacing

        if input is None:
            input = self._allocate_array((self.num_inputs, sample_frames), c_type)
        else:
            input = (POINTER(c_type) * self.num_inputs)(*[row.ctypes.data_as(POINTER(c_type))
                                                          for row in input])
        if sample_frames is None:
            raise ValueError('You must provide `sample_frames` when there is no input')

        output = self._allocate_array((self.num_outputs, sample_frames), c_type)

        with pipes() if not self.verbose else contextlib.suppress():
            process_fn(
                byref(self._effect),
                input,
                output,
                sample_frames,
            )
        output = np.vstack([
            np.ctypeslib.as_array(output[i], shape=(sample_frames,))
            for i in range(self.num_outputs)
        ])
        return output

    def process_events(self, vst_events):
        self._dispatch(AEffectOpcodes.effProcessEvents, ptr=byref(vst_events))

    def set_block_size(self, max_block_size):
        self._dispatch(AEffectOpcodes.effSetBlockSize, value=max_block_size)

    def set_sample_rate(self, sample_rate):
        self._dispatch(AEffectOpcodes.effSetSampleRate, opt=sample_rate)

    @property
    def is_synth(self):
        return self._effect.flags & VstAEffectFlags.effFlagsIsSynth

    @property
    def can_double_replacing(self):
        return bool(self._effect.flags & VstAEffectFlags.effFlagsCanDoubleReplacing)

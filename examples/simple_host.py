import argparse
from pyvst import SimpleHost


def _print_params(vst, max_params=10):
    """Prints the parameters of a VST with its current value."""
    for i in range(min(vst.num_params, max_params)):
        print('{}: {}'.format(
            vst.get_param_name(i),
            vst.get_param_value(i),
        ))


def main(vst_filename):
    host = SimpleHost(vst_filename, sample_rate=48000.)
    _print_params(host.vst)

    sound = host.play_note(note=64, note_duration=1.)
    print(sound)
    print(sound.shape)

    host.vst.set_param_value(index=0, value=1.)
    host.vst.set_param_value(index=1, value=0.5)

    _print_params(host.vst)

    sound = host.play_note(note=64, note_duration=1.)
    print(sound)
    print(sound.shape)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('vst', help='path to .so file')
    args = parser.parse_args()

    main(args.vst)

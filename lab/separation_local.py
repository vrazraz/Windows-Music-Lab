"""Pinned local model resolver for audio-separator, without registry downloads.

The architecture/inference remains audio-separator's implementation. Its dynamic
download resolver is replaced only for the two studio-supported local profiles.
This avoids fetching registries on a first offline run with already-present weights.
"""
from pathlib import Path

ROFORMER = 'model_bs_roformer_ep_317_sdr_12.9755.ckpt'
ROFORMER_CONFIG = 'model_bs_roformer_ep_317_sdr_12.9755.yaml'
DEMUCS = 'htdemucs_ft.yaml'
DEMUCS_WEIGHTS = ('f7e0c4bc-ba3fe64a.th', 'd12395a8-e57c48e6.th',
                  '92cfc3b6-ef3bcb9c.th', '04573f0d-f3cf25b2.th')


def local_separator_class(base):
    class LocalSeparator(base):
        def download_model_files(self, model_filename):
            directory = Path(self.model_file_dir)
            if model_filename == ROFORMER:
                required, kind, config = (ROFORMER, ROFORMER_CONFIG), 'MDXC', ROFORMER_CONFIG
            elif model_filename == DEMUCS:
                required, kind, config = (DEMUCS, *DEMUCS_WEIGHTS), 'Demucs', DEMUCS
            else:
                raise ValueError('unsupported local separation model: ' + model_filename)
            missing = [name for name in required if not (directory/name).is_file() or (directory/name).stat().st_size == 0]
            if missing:
                raise FileNotFoundError('local separation assets are missing: ' + ', '.join(missing))
            self.model_is_uvr_vip = False
            self.model_friendly_name = model_filename
            return model_filename, kind, model_filename, str(directory/model_filename), str(directory/config)

        def download_file_if_not_exists(self, url, filepath):
            path = Path(filepath)
            if not path.is_file() or path.stat().st_size == 0:
                raise FileNotFoundError('automatic separation downloads are disabled; install the approved local file: ' + str(path))
            return None
    return LocalSeparator

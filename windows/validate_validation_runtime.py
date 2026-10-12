"""Offline import/manifest validation for an installed approved profile, no inference."""
import argparse, hashlib, importlib, importlib.metadata, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'lab'))
from platform_runtime import configure_runtime
p=argparse.ArgumentParser();p.add_argument('profile',choices=['core','art']);args=p.parse_args()
configure_runtime(ROOT,artist=args.profile=='art')
cache=ROOT/'windows/cache/validation-runtime'
modules={'core':['torch','torchaudio','numpy','scipy','soundfile','faster_whisper','ctranslate2','mutagen','mido','PIL'],
         'art':['torch','torchvision','numpy','scipy','PIL','diffusers','transformers','accelerate','peft','safetensors']}
for module in modules[args.profile]:
    importlib.import_module(module)
if args.profile=='art':
    from diffusers import StableDiffusionXLPipeline
import torch
assert torch.__version__=='2.11.0+cu128' and torch.version.cuda=='12.8','Expected official CUDA wheel build'
snapshot=cache/f'installed-{args.profile}.json'
lock=ROOT/f'windows/requirements-validation-{args.profile}.lock.txt'
assert snapshot.is_file() and lock.is_file()
packages=json.loads(snapshot.read_text(encoding='utf8'))
for row in packages:
    assert importlib.metadata.version(row['name'])==row['version'],'Snapshot differs from installed packages'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
data={'pythonRelativePath':'.venv-art/Scripts/python.exe' if args.profile=='art' else '.venv/Scripts/python.exe',
      'installedSnapshotRelativePath':snapshot.relative_to(ROOT).as_posix(),'installedSnapshotSha256':digest(snapshot),
      'lockFileRelativePath':lock.relative_to(ROOT).as_posix(),'lockFileSha256':digest(lock),
      'importChecksPassed':True,'cudaBuild':torch.__version__,'cudaToolkitBuild':torch.version.cuda,
      'packageCount':len(packages),'gpuInferenceRun':False}
(cache/f'validated-{args.profile}.json').write_text(json.dumps(data,indent=2),encoding='utf8')
print(json.dumps({'profile':args.profile,**data}))
"""Resolve binary dependency metadata with the installed pip 23 tool only.

pip's regular dry run eagerly downloads all wheels. This process-local wrapper
retains resolved metadata for its JSON report and skips that redundant full-wheel
step. It never installs, patches pip files, or imports candidate packages. The
independent publisher audit and SHA256 offline install remain mandatory.
"""
import argparse, sys
from pathlib import Path
import pip
from pip._internal.cli.main import main as pip_main
from pip._internal.operations.prepare import RequirementPreparer
from pip._internal.utils.direct_url_helpers import direct_url_from_link
p=argparse.ArgumentParser();p.add_argument('profile',choices=['core','art']);args=p.parse_args()
if pip.__version__!='23.0.1': raise SystemExit('Metadata-only resolver supports bundled pip 23.0.1; review before using another pip.')
root=Path(__file__).resolve().parents[1]
original=RequirementPreparer.prepare_linked_requirement

def metadata_only(self,req,parallel_builds=False):
    if not req.link or not req.link.is_wheel: raise RuntimeError('Only binary wheels may be resolved')
    dist=original(self,req,parallel_builds=parallel_builds)
    req._validation_resolved_dist=dist
    req.get_dist=lambda:dist
    if not req.download_info: req.download_info=direct_url_from_link(req.link)
    return dist

def no_full_wheel_step(self,reqs,parallel_builds=False):
    for req in reqs:
        if not req.link or not req.link.is_wheel or not hasattr(req,'_validation_resolved_dist'):
            raise RuntimeError('Incomplete/non-binary metadata; refusing report')
    print('Metadata resolved; redundant full-wheel dry-run download skipped.',flush=True)
RequirementPreparer.prepare_linked_requirement=metadata_only
RequirementPreparer.prepare_linked_requirements_more=no_full_wheel_step
sys.exit(pip_main(['install','--dry-run','--ignore-installed','--only-binary=:all:','--use-feature=fast-deps',
                  '--report',str(root/f'windows/cache/validation-runtime/report-{args.profile}.json'),
                  '-r',str(root/f'windows/requirements-validation-{args.profile}.txt')]))
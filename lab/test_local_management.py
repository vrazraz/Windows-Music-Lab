"""File-only Windows management checks; no installed models or external tools.
Run: py -3.10 lab/test_local_management.py
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import weights
import updates
import platform_runtime as runtime

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / 'lab/cache/management-tests'
FIXTURES.mkdir(parents=True, exist_ok=True)
assert FIXTURES.resolve().is_relative_to(ROOT.resolve())


class ManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=FIXTURES)
        self.root = Path(self.temp.name)
        for directory in ('windows', 'models', 'user'):
            (self.root / directory).mkdir()
        (self.root / 'VERSION').write_text('2.0.0-rc5')
        self.env = mock.patch.dict(os.environ, {'RUACH_OFFLINE':'1', 'RUACH_MODELS_DIR':''})
        self.env.start()
        self.network = mock.patch('urllib.request.urlopen', side_effect=AssertionError('network used'))
        self.network.start()
        self.run = mock.patch('subprocess.run', side_effect=AssertionError('subprocess used'))
        self.run.start()
        self.popen = mock.patch('subprocess.Popen', side_effect=AssertionError('Popen used'))
        self.popen.start()
        weights.JOB.clear()

    def tearDown(self):
        self.popen.stop(); self.run.stop(); self.network.stop(); self.env.stop()
        self.temp.cleanup()

    def _manifest(self, name, value):
        runtime.write_json(self.root / 'windows' / name, value)

    def test_local_model_listing_has_truthful_size_verdicts_without_sha_claim(self):
        rows = [{'filename':f'{name}.gguf','size':3,'sha256':'1'*64} for name in ('present','partial','missing')]
        self._manifest('downloads.json', {'models':rows})
        (self.root / 'models/present.gguf').write_bytes(b'abc')
        (self.root / 'models/partial.gguf').write_bytes(b'a')
        result = weights.listing(self.root)
        self.assertEqual(result['mode'], 'local')
        self.assertFalse(result['download_enabled'])
        self.assertFalse(result['script'])
        self.assertIsNone(result['job'])
        self.assertEqual(result['last']['counts']['here'],1)
        self.assertEqual(result['last']['counts']['differs'],1)
        self.assertEqual(result['last']['counts']['missing'],1)
        self.assertEqual(result['last']['counts']['fetched'],0)
        self.assertIn('No remote lookup', result['notice'])
        self.assertIn('SHA256 validation', result['notice'])
        self.assertEqual(result['last']['parts'][0]['rows'][0]['verification'],'size_only')

    def test_sync_local_check_does_not_spawn_bash_or_mutate_job(self):
        self._manifest('downloads.json', {'models':[]})
        result = weights.check(self.root)
        self.assertEqual(result['last']['mode'],'local-presence-and-size')
        self.assertEqual(weights.JOB,{})
        self.assertFalse(weights.running())

    def test_audio_and_art_pinned_metadata_files_are_inventory_only(self):
        self._manifest('full-audio-models.json', {'models':[{'profile':'whisper','destination':'whisper/model.bin','size':3,'revision':'pin','license':'MIT'}]})
        self._manifest('full-art-models.json', {'models':[{'id':'fixture','directory':'artwork/fixture','revision':'pin','license':'test','files':[{'path':'file.bin','size':3,'sha256':'2'*64}]}]})
        result=weights.listing(self.root)
        self.assertEqual([p['part'] for p in result['last']['parts']],['whisper','artwork:fixture'])
        self.assertEqual(result['last']['counts']['missing'],2)

    def test_explicit_external_base_model_root_is_read_only(self):
        external=self.root/'configured-models'; external.mkdir(); (external/'fixture.gguf').write_bytes(b'abc')
        self._manifest('downloads.json', {'models':[{'filename':'fixture.gguf','size':3}]})
        with mock.patch.dict(os.environ, {'RUACH_MODELS_DIR':str(external)}):
            result=weights.listing(self.root)
        self.assertEqual(result['last']['counts']['here'],1)
        self.assertEqual((external/'fixture.gguf').read_bytes(),b'abc')

    def test_manifest_traversal_never_probes_outside_directory(self):
        self._manifest('downloads.json', {'models':[{'filename':'../VERSION','size':9}]})
        result=weights.listing(self.root)
        self.assertEqual(result['last']['counts']['unknown'],1)
        self.assertEqual(result['last']['counts']['here'],0)

    def test_invalid_metadata_still_has_usable_status(self):
        (self.root/'windows/downloads.json').write_bytes(b'not json')
        result=weights.listing(self.root)
        self.assertEqual(result['mode'],'local')
        self.assertTrue(result['metadata_errors'])
        self.assertFalse(result['download_enabled'])

    def test_direct_fetch_and_internal_launch_paths_fail_before_side_effects(self):
        for call in (lambda:weights.fetch(self.root,{'part':'missing'}),
                     lambda:weights._start(self.root,[],'test','fetch',False),
                     lambda:weights._say(self.root,[]),
                     lambda:weights._run(self.root,[],False)):
            with self.assertRaisesRegex(ValueError,'disabled'):
                call()
        self.assertEqual(weights.JOB,{})

    def test_windows_is_manual_even_if_offline_flag_was_removed(self):
        with mock.patch.object(runtime,'WINDOWS',True), mock.patch.dict(os.environ, {'RUACH_OFFLINE':'0','WINDOWS_MUSIC_LAB_LOCAL_ONLY':'0'}):
            self.assertFalse(updates.can_run(self.root)[0])
            with self.assertRaisesRegex(ValueError,'disabled'):
                weights.fetch(self.root,{'part':'missing'})
            status, result=updates.run(self.root,self.root/'user','2.0.0',False)
            self.assertEqual(status,409)
            self.assertEqual(result['status'],'disabled')

    def test_update_status_and_check_are_local_and_fork_named(self):
        before=list((self.root/'user').iterdir())
        for result in (updates.status(self.root,self.root/'user'),updates.check(self.root,self.root/'user')):
            self.assertFalse(result['can_run'])
            self.assertFalse(result['running'])
            self.assertFalse(result['check_performed'])
            self.assertTrue(result['lookup_disabled'])
            self.assertEqual(result['error'],'')
            self.assertEqual(result['repo'],'vrazraz/Windows-Music-Lab')
            self.assertIn('git fetch origin',result['why'])
        self.assertEqual(list((self.root/'user').iterdir()),before)

    def test_cached_upstream_releases_never_offer_fork_apply(self):
        runtime.write_json(self.root/'user/updates.json',{'repo':'igrbible/Ruach_Studio','latest':{'tag':'v99.0.0','url':'https://github.com/igrbible/Ruach_Studio'},'checked':123})
        result=updates.status(self.root,self.root/'user')
        self.assertIsNone(result['latest'])
        self.assertEqual(result['checked'],0)
        self.assertTrue(result['upstream_cache_ignored'])
        code, reply=updates.run(self.root,self.root/'user','99.0.0',False)
        self.assertEqual(code,409)
        self.assertNotIn('started',reply)
        self.assertIn('never apply igrbible upstream',reply['error'])

    def test_invalid_or_bom_state_cannot_break_local_status(self):
        file=self.root/'user/updates.json'
        for payload in (b'[]', b'not json', b'\xef\xbb\xbf{"repo":"vrazraz/Windows-Music-Lab","latest":false}'):
            file.write_bytes(payload)
            result=updates.status(self.root,self.root/'user')
            self.assertEqual(result['mode'],'local')
            self.assertFalse(result['can_run'])
            self.assertIsNone(result['latest'])

    def test_known_fork_cache_is_labelled_cached_only(self):
        runtime.write_json(self.root/'user/updates.json',{'repo':'vrazraz/Windows-Music-Lab','latest':{'tag':'v99.0.0'},'checked':123})
        result=updates.status(self.root,self.root/'user')
        self.assertTrue(result['cached_only'])
        self.assertFalse(result['check_performed'])
        self.assertFalse(result['can_run'])

    def test_internal_git_helper_is_blocked_in_local_management(self):
        code, out, error=updates._git(self.root,'fetch','origin')
        self.assertEqual(code,126)
        self.assertEqual(out,'')
        self.assertIn('manually',error)


if __name__=='__main__':
    unittest.main(verbosity=2)

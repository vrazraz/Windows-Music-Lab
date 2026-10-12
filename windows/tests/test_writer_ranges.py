"""Counter/resume invariants for Writer's shared bounded transport; no HTTP."""
import hashlib
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
W=load("writer_setup","writer_setup.py")
R=load("writer_ranges","writer_ranges.py")

class Ranges(unittest.TestCase):
    def setUp(self):
        cache=HERE/"cache/writer-tests";cache.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=cache)
        self.root=Path(self.temp.name).resolve()
    def tearDown(self):self.temp.cleanup()
    def test_failure_then_resume_charges_delta_and_keeps_source_cost(self):
        ledger=W.Ledger(self.root,0)
        ledger.data["total_body_bytes"]=1234
        path=self.root/"models/writer/fixture.gguf"
        payload=b"synthetic payload";digest=hashlib.sha256(payload).hexdigest()
        fake=types.SimpleNamespace(staged_bytes=lambda *a:0)
        def failed(module,asset,opener,data,data_path,pending,other,workers):
            self.assertEqual(workers,6)
            self.assertEqual(module.CAP,W.CAP-1234-W.LICENSE_BYTES)
            self.assertIn("writer/model-segments",str(module.destination("windows/cache/listener/segments/x")).replace("\\","/"))
            data["charged_payload_upper_bound"]+=20
            data["received_payload_bytes"]+=5
            module.write_json(data_path,data)
            raise RuntimeError("synthetic interrupted range")
        fake.receive=failed
        with patch.dict(sys.modules,{"writer_setup":W,"listener_parallel":fake}),self.assertRaises(RuntimeError):
            R.receive(ledger,path,len(payload),digest)
        self.assertEqual(ledger.data["total_body_bytes"],1254)
        self.assertEqual(ledger.data["writer_model_ranges"]["received_payload_bytes"],5)
        def resumed(module,asset,opener,data,data_path,pending,other,workers):
            data["charged_payload_upper_bound"]+=len(payload)
            data["received_payload_bytes"]+=len(payload)
            path.parent.mkdir(parents=True);path.write_bytes(payload)
            module.write_json(data_path,data)
        fake.receive=resumed
        with patch.dict(sys.modules,{"writer_setup":W,"listener_parallel":fake}):
            R.receive(ledger,path,len(payload),digest)
        self.assertEqual(ledger.data["total_body_bytes"],1254+len(payload))
        self.assertEqual(ledger.data["artifacts"][path.relative_to(self.root).as_posix()]["sha256"],digest)
        self.assertEqual(ledger.data["conservative_extra_bytes"],1234+15)

if __name__=="__main__":unittest.main()

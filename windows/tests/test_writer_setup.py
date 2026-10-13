"""Synthetic installer checks; no HTTP, vendor build or models are executed."""
import hashlib
import importlib.util
import io
import json
import stat
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location("writer_setup",Path(__file__).resolve().parents[1]/"writer_setup.py")
W=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(W)


def blob(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


class Installer(unittest.TestCase):
    def setUp(self):
        cache=Path(__file__).resolve().parents[1]/"cache"/"writer-tests"
        cache.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=cache)
        self.root=Path(self.temp.name).resolve()

    def tearDown(self):
        self.temp.cleanup()

    def ledger(self):
        return W.Ledger(self.root,0)

    def test_atomic_counter_waits_for_windows_reader_to_close(self):
        path=self.root/"counter.json"
        W.atomic_json(path,{"value":1})
        ready=threading.Event()
        def reader():
            with path.open("rb") as handle:
                ready.set();time.sleep(.12)
        thread=threading.Thread(target=reader);thread.start();self.assertTrue(ready.wait(2))
        try:W.atomic_json(path,{"value":2})
        finally:thread.join(2)
        self.assertEqual(json.loads(path.read_text())["value"],2)
        self.assertFalse(path.with_name(path.name+".part").exists())

    def test_head_resolution_never_drains_redirect_body(self):
        class Reply:
            def __init__(self,status,headers):
                self.status,self.headers,self.closed=status,headers,False
            def __enter__(self):return self
            def __exit__(self,*args):self.closed=True
            def read(self,*args):raise AssertionError("HEAD resolver must not read a redirect body")
        first=Reply(302,{"Location":"https://cdn.example/immutable"})
        final=Reply(206,{})
        opener=type("Opener",(),{})()
        calls=[]
        def opened(req,timeout):
            calls.append(req)
            return first if len(calls)==1 else final
        opener.open=opened
        with patch.object(W.urllib.request,"build_opener",return_value=opener):
            url,hops=W.final_https_url("https://official.example/pin",headers={"Range":"bytes=0-15"})
        self.assertEqual((url,hops),("https://cdn.example/immutable",1))
        self.assertTrue(first.closed and final.closed)
        self.assertTrue(all(req.get_method()=="HEAD" for req in calls))
        self.assertTrue(all(req.get_header("Range")=="bytes=0-15" for req in calls))

    def test_head_resolution_blocks_https_downgrade_before_follow(self):
        class Reply:
            status=302
            headers={"Location":"http://untrusted.example/file"}
            def __enter__(self):return self
            def __exit__(self,*args):pass
        opener=type("Opener",(),{"open":lambda *args,**kwargs:Reply()})()
        with patch.object(W.urllib.request,"build_opener",return_value=opener),self.assertRaisesRegex(RuntimeError,"leaves HTTPS"):
            W.final_https_url("https://official.example/pin")

    def test_cached_artifact_sha_mismatch_blocks_without_network(self):
        led=self.ledger();file=led.cache/"fixture.bin";file.write_bytes(b"first")
        led.data["artifacts"][file.relative_to(self.root).as_posix()]={"size":5,"sha256":W.sha256(file)}
        led.save();file.write_bytes(b"other")
        with patch.object(W.subprocess,"Popen") as proc,self.assertRaises(RuntimeError):
            led.get("https://github.com/fixture",file,max_file_bytes=10)
        proc.assert_not_called()

    def test_verified_partial_finalizes_without_http(self):
        led=self.ledger();file=led.cache/"model.bin";part=file.with_name(file.name+".part");part.write_bytes(b"test")
        with patch.object(W.subprocess,"Popen") as proc:
            led.get("https://github.com/fixture",file,4,hashlib.sha256(b"test").hexdigest())
        proc.assert_not_called();self.assertEqual(file.read_bytes(),b"test")

    def test_network_cap_blocks_before_process(self):
        led=self.ledger();led.data["total_body_bytes"]=W.CAP-2
        with patch.object(W.subprocess,"Popen") as proc,patch.object(W,"guard"),self.assertRaises(RuntimeError):
            led.get("https://github.com/fixture",led.cache/"model.bin",4,hashlib.sha256(b"test").hexdigest())
        proc.assert_not_called()

    def test_safe_zip_name_rejects_traversal_drive_backslash_reserved(self):
        prefix="llama.cpp-"+W.PIN
        for name in (prefix+"/../x",prefix+"/C:/x",prefix+"\\x",prefix+"/NUL",prefix+"/a. ", "/"+prefix+"/x"):
            with self.subTest(name=name),self.assertRaises(ValueError):
                W.safe_archive_name(name,prefix)
        self.assertEqual(W.safe_archive_name(prefix+"/src/файл.cpp",prefix),"src/файл.cpp")

    def source_fixture(self,bad=None):
        files={"CMakeLists.txt":b"# fixture\n","LICENSE":b"MIT fixture\n","src/файл.cpp":b"int main(){}\n"}
        tree_sha="b"*40
        commit={"sha":W.PIN,"tree":{"sha":tree_sha}}
        tree={"sha":tree_sha,"truncated":False,"tree":[{"path":name,"type":"blob","mode":"100644","size":len(data),"sha":blob(data)} for name,data in files.items()]}
        led=self.ledger()
        paths={}
        for label,value in (("llama-source-commit.json",commit),("llama-source-tree-"+tree_sha+".json",tree)):
            path=led.cache/label;W.atomic_json(path,value);paths[label]=path
        archive=led.cache/"llama-source.zip"
        with zipfile.ZipFile(archive,"w") as zipped:
            for name,data in files.items():
                info=zipfile.ZipInfo("llama.cpp-"+W.PIN+"/"+name)
                info.create_system=3;info.external_attr=(stat.S_IFREG|0o644)<<16
                if bad=="hash" and name=="LICENSE":data=b"bad fixture\n"
                if bad=="symlink" and name=="LICENSE":info.external_attr=(stat.S_IFLNK|0o777)<<16
                zipped.writestr(info,data)
            if bad=="case":zipped.writestr("llama.cpp-"+W.PIN+"/license",files["LICENSE"])
            if bad=="traversal":zipped.writestr("llama.cpp-"+W.PIN+"/../escape",b"bad")
        paths[archive.name]=archive
        led.get=lambda url,destination,*args,**kwargs:paths[destination.name]
        return led

    def test_every_source_blob_verified_and_provenance_not_githead(self):
        led=self.source_fixture()
        with patch.object(W,"guard"):W.source(led)
        proof=json.loads((self.root/"vendor/llama.cpp/source-pin.json").read_text())
        self.assertEqual(proof["verified_blob_count"],3)
        self.assertEqual(proof["revision"],W.PIN)
        self.assertFalse(proof["fabricated_git_head"])
        self.assertFalse((self.root/"vendor/llama.cpp/.git").exists())

    def test_source_reuse_rejects_untracked_build_input(self):
        led=self.source_fixture()
        with patch.object(W,"guard"):W.source(led)
        target=self.root/"vendor/llama.cpp"
        (target/"src/extra.cpp").write_bytes(b"synthetic untracked build input")
        with patch.object(W,"guard"),self.assertRaisesRegex(RuntimeError,"untracked source input"):
            W.source(led)

    def test_bad_source_never_published_and_temp_removed(self):
        for bad in ("hash","symlink","case","traversal"):
            with self.subTest(bad=bad):
                led=self.source_fixture(bad)
                with patch.object(W,"guard"),self.assertRaises((ValueError,RuntimeError)):
                    W.source(led)
                self.assertFalse((self.root/"vendor/llama.cpp").exists())
                self.assertFalse(list(led.cache.glob("source-extract-*")))


if __name__=="__main__":unittest.main()
"""Use the shared bounded range transport with an independent Writer sub-ledger.

The source/metadata/other failed reads remain billed in the primary ledger.
The subordinate cap is fixed at the unused Writer allocation minus the license;
a failed/interrupted range stays fully reserved, so a resume cannot reset budget.
"""
import json
import types
import urllib.request
import urllib.error

def receive(ledger, destination, size, digest):
    import listener_parallel as transport
    import writer_setup as setup
    relative = destination.relative_to(ledger.root).as_posix()
    sub_path = ledger.cache / "model-range-ledger.json"
    if sub_path.exists():
        sub = json.loads(sub_path.read_text(encoding="utf8"))
    else:
        sub = {"base_body_bytes": ledger.data["total_body_bytes"],
               "cap_bytes": setup.CAP - ledger.data["total_body_bytes"] - setup.LICENSE_BYTES,
               "charged_payload_upper_bound": 0, "received_payload_bytes": 0, "files": {},
               "model_revision": setup.REV, "model_sha256": digest, "model_bytes": size}
        setup.atomic_json(sub_path, sub)
    if (sub["model_revision"] != setup.REV or sub["model_sha256"] != digest or
        sub["model_bytes"] != size or sub["base_body_bytes"] + sub["cap_bytes"] + setup.LICENSE_BYTES != setup.CAP):
        raise RuntimeError("Writer range budget/provenance differs")
    module = types.SimpleNamespace()
    def project_path(name):
        if name.startswith("windows/cache/listener/segments/"):
            name = name.replace("windows/cache/listener/segments/", "windows/cache/writer/model-segments/", 1)
        return setup.contained(ledger.root, ledger.root / name)
    module.destination = project_path
    module.write_json = setup.atomic_json
    module.sha256 = setup.sha256
    module.CAP = sub["cap_bytes"]
    module.RANGE = 16 * 1024 ** 2
    module.CHUNK = 1024 ** 2
    module.disk_gate = lambda remaining, pending, other: setup.guard(ledger.root, pending, remaining + other)
    def remaining_bytes():
        part = destination.with_suffix(destination.suffix + ".part")
        prefix = part.stat().st_size if part.is_file() else 0
        staged = transport.staged_bytes(module, relative, prefix, size)
        # A copied range temporarily exists beside the growing contiguous prefix.
        return max(0, size - prefix - staged) + module.RANGE
    module.remaining_bytes = remaining_bytes
    def reuse(asset, opener, data, path, pending, other):
        setup.Ledger.validate(destination, size, digest)
    module.receive = reuse
    asset = ("Qwen/Qwen3-4B-GGUF", setup.REV, "Qwen3-4B-Q4_K_M.gguf", relative, size, digest)
    class HeadResolvedOpener:
        def __init__(self):
            self.direct = urllib.request.build_opener(urllib.request.ProxyHandler({}), setup.NoHeadRedirect())
        def open(self, request, timeout=45):
            # Resolve every signed Range URL with HEAD, preserving its Range policy.
            # No redirect body is automatically drained by urllib.
            headers = dict(request.header_items())
            url, _ = setup.final_https_url(request.full_url, headers=headers, timeout=timeout)
            direct = urllib.request.Request(url, headers=headers, method=request.get_method())
            try:
                return self.direct.open(direct, timeout=timeout)
            except urllib.error.HTTPError as error:
                code = error.code
                error.close()
                raise RuntimeError(f"Direct ranged GET HTTP {code}; no redirect followed; reservation retained")
    opener = HeadResolvedOpener()
    remaining_cap = setup.CAP - ledger.data["total_body_bytes"] - (
        0 if (ledger.root / "models/writer/LICENSE-Qwen3.txt").exists() else setup.LICENSE_BYTES)
    module.CAP = min(sub["cap_bytes"], sub["charged_payload_upper_bound"] + remaining_cap)
    if not destination.exists() and remaining_bytes() - module.RANGE > module.CAP - sub["charged_payload_upper_bound"]:
        raise RuntimeError("Pinned remaining model cannot fit the aggregate Writer cap; no request made")
    try:
        transport.receive(module, asset, opener, sub, sub_path, ledger.pending, 0, workers=6)
    finally:
        # Reconcile only the delta since earlier failed/resumed model attempts.
        previous = ledger.data.get("writer_model_ranges", {})
        old_charge = previous.get("charged_payload_upper_bound", 0)
        old_actual = previous.get("received_payload_bytes", 0)
        new_charge = sub["charged_payload_upper_bound"]
        new_actual = sub["received_payload_bytes"]
        if new_charge < old_charge or new_actual < old_actual:
            raise RuntimeError("Range counter decreased; primary ledger preserved")
        ledger.data["total_body_bytes"] += new_charge - old_charge
        ledger.data["transfers"].append({"file": relative, "transport": "bounded-HF-ranges",
            "body_bytes": new_actual - old_actual, "charged_payload_upper_bound": new_charge - old_charge,
            "subordinate_ledger": sub_path.relative_to(ledger.root).as_posix()})
        ledger.data["writer_model_ranges"] = {"charged_payload_upper_bound": new_charge,
            "received_payload_bytes": new_actual, "cap_bytes": sub["cap_bytes"],
            "subordinate_ledger": sub_path.relative_to(ledger.root).as_posix()}
        if ledger.data["total_body_bytes"] > setup.CAP:
            raise RuntimeError("Writer aggregate network cap violated")
        ledger.save()
    setup.Ledger.validate(destination, size, digest)
    ledger.data["artifacts"][relative] = {"size": size, "sha256": digest, "expected_sha256": digest,
                                        "counted_body_bytes": sub["received_payload_bytes"]}
    ledger.save()

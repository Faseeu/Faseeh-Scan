"""Sanity tests for crypto + vault — run with: python -m tests.test_core"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from medical_reports import crypto
from medical_reports.vault import Vault
from medical_reports.backends.local import LocalBackend


def test_report_roundtrip():
    key = b"0" * 32
    pt = b"%PDF-1.4 fake report contents \x00\x01\x02"
    ct = crypto.encrypt_report(key, pt)
    assert ct != pt
    assert crypto.decrypt_report(key, ct) == pt
    print("OK report roundtrip")


def test_wrong_password():
    _, wrapped = crypto.create_wrapped_master_key("correct horse")
    mk = crypto.unwrap_master_key(wrapped, "correct horse")
    assert len(mk) == 32
    try:
        crypto.unwrap_master_key(wrapped, "wrong")
        assert False, "should have raised"
    except crypto.WrongPasswordError:
        pass
    print("OK wrong password rejected")


def test_tamper_detection():
    key = b"1" * 32
    ct = bytearray(crypto.encrypt_report(key, b"hello"))
    ct[-1] ^= 0xFF  # flip a bit in the auth tag / ciphertext
    try:
        crypto.decrypt_report(key, bytes(ct))
        assert False
    except crypto.VaultCorruptedError:
        pass
    print("OK tamper detected")


def test_vault_lifecycle():
    with tempfile.TemporaryDirectory() as d:
        v = Vault(Path(d) / "vault")
        v.create("mypassword")
        v.add_report(b"report one bytes", "blood-test.pdf", "application/pdf")
        v.add_report(b"report two bytes", "xray.jpg", "image/jpeg", note="chest")
        reports = v.list_reports()
        assert len(reports) == 2
        v.lock()
        # wrong password
        try:
            v.unlock("nope")
            assert False
        except crypto.WrongPasswordError:
            pass
        # correct password
        v.unlock("mypassword")
        meta, data = v.get_report(reports[0].id)
        assert data in (b"report one bytes", b"report two bytes")
        # change password
        v.change_password("mypassword", "newpassword")
        v.lock()
        v.unlock("newpassword")
        assert len(v.list_reports()) == 2
        print("OK vault lifecycle (create/add/lock/unlock/change-password)")


def test_local_backend_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        v = Vault(d / "vault")
        v.create("pw")
        v.add_report(b"data123", "a.pdf")
        be = LocalBackend(d / "backup")
        n = be.backup_vault(v)
        assert n >= 2  # at least data file + key/meta
        # restore into a fresh vault dir
        v2 = Vault(d / "restored")
        v2.path.mkdir(parents=True)
        n2 = be.restore_vault(v2)
        assert n2 == n
        v2.unlock("pw")
        restored = v2.list_reports()
        assert len(restored) == 1
        _, data = v2.get_report(restored[0].id)
        assert data == b"data123"
        print("OK local backend backup/restore")


if __name__ == "__main__":
    test_report_roundtrip()
    test_wrong_password()
    test_tamper_detection()
    test_vault_lifecycle()
    test_local_backend_roundtrip()
    print("\nAll core tests passed.")

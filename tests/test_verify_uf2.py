#!/usr/bin/env python3
import sys, struct, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from verify_build import apply_codec_heap_audit, verify_uf2

def block(addr,index,count,family=0xe48bff59,flags=0x2000,data=bytes(256)):
    b=bytearray(512)
    struct.pack_into('<8I',b,0,0x0a324655,0x9e5d5157,flags,addr,256,index,count,family)
    b[32:288]=data
    struct.pack_into('<I',b,508,0x0ab16f30)
    return bytes(b)
class UF2(unittest.TestCase):
    def test_families_and_compatibility(self):
        for family in (0xe48bff56,0xe48bff59):
            data=block(0x10000000,0,2,family)+block(0x10000100,1,2,family)
            self.assertEqual(verify_uf2(data,bytes(512))[0],2)
            if family==0xe48bff59:
                compat=block(0x10ffff00,0,2,0xe48bff57,0xa000)
                self.assertEqual(verify_uf2(compat+data,bytes(512))[0],3)
    def test_reject_corruption(self):
        valid=block(0x10ffff00,0,2,0xe48bff57,0xa000)+block(0x10000000,0,2)+block(0x10000100,1,2)
        # Header, address, index, count, flags, family and main payload mutations.
        for offset in (0,8,12,16,20,24,28,512+8,512+12,512+20,512+24,512+28,512+32):
            corrupt=bytearray(valid); corrupt[offset]^=1
            with self.subTest(offset=offset), self.assertRaises(ValueError): verify_uf2(corrupt,bytes(512))
        for corrupt in (valid[:-1],valid[512:],valid+valid[-512:],valid[:1024]):
            if corrupt==valid[512:]: continue # compatibility block is optional
            with self.assertRaises(ValueError): verify_uf2(corrupt,bytes(512))
class CodecHeapAudit(unittest.TestCase):
    def test_valid_audit_sets_verified_flag(self):
        memory={}
        out=apply_codec_heap_audit(memory,5000,{"pointer_bytes":4,"codec_requested_peak":1000})
        self.assertIs(out,memory)
        self.assertTrue(memory["runtime_allocation_verified"])
        self.assertEqual(memory["host_codec_estimate"]["remaining_before_allocator_and_other_heap_users"],4000)
    def test_invalid_audits_are_rejected_and_never_verified(self):
        for region,audit in ((5000,{"pointer_bytes":8,"codec_requested_peak":1}),
                             (5000,{"pointer_bytes":4}),
                             (5000,{"pointer_bytes":4,"codec_requested_peak":-1}),
                             (100,{"pointer_bytes":4,"codec_requested_peak":100}),
                             (100,{"pointer_bytes":4,"codec_requested_peak":101})):
            memory={}
            with self.subTest(audit=audit), self.assertRaises(ValueError):
                apply_codec_heap_audit(memory,region,audit)
            self.assertFalse(memory.get("runtime_allocation_verified",False))
if __name__=='__main__': unittest.main()

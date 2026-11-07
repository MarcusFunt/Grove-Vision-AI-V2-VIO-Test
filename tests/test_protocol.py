import pathlib,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host'))
from protocol import PacketDecoder,parse_packet,crc16

class TestProtocol(unittest.TestCase):
    def test_known_crc(self):
        self.assertEqual(crc16(b'123456789'),0x29b1)
    def test_native_packets(self):
        f=ROOT/'tests/sample_stream.bin'
        self.assertTrue(f.exists(), 'Run: make test')
        dec=PacketDecoder()
        frames=[]
        data=f.read_bytes()
        for pos in range(0,len(data),7):frames+=dec.feed(data[pos:pos+7])
        self.assertEqual(len(frames),2)
        self.assertEqual(frames[0].sequence,20)
        self.assertEqual(frames[0].frame_ready_ticks,123456789)
        self.assertGreater(len(frames[0].features),20)
        self.assertEqual(dec.bad,0)
    def test_crc_failure(self):
        b=bytearray((ROOT/'tests/sample_stream.bin').read_bytes())
        b[35]^=9
        self.assertEqual(len(PacketDecoder().feed(bytes(b))),1)
if __name__=='__main__': unittest.main()

import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host'))
from metrics import Monitor, StationaryTest
from protocol import Frame,Track


def frame(seq,off_x=0,off_y=0,outlier=False):
    tracks=[]
    for i in range(20):
        x=30+(i%5)*45+off_x
        y=30+(i//5)*42+off_y
        if outlier and i==1:x+=10
        tracks.append(Track(i,x,y,90,seq+1))
    return Frame(seq,100000*seq,3000,20,0,1,tuple(tracks))


class TestMetrics(unittest.TestCase):
    def test_static(self):
        mon=Monitor();test=StationaryTest(seconds=10,started_at=0)
        for i in range(10):
            f=frame(i);m=mon.update(f,i/30);test.observe(f,m)
        self.assertEqual(mon.frames,10)
        self.assertEqual(mon.sequence_gaps,0)
        self.assertEqual(mon.last_metrics['matched'],20)
        self.assertEqual(mon.last_metrics['flow_px'],0)
        self.assertEqual(test.results()['median_feature_rms_px'],0)

    def test_coherent_translation(self):
        mon=Monitor()
        mon.update(frame(1),1)
        m=mon.update(frame(2,3,-2),2)
        self.assertEqual(m['flow_x'],3)
        self.assertEqual(m['flow_y'],-2)
        self.assertEqual(m['scatter_px'],0)
        self.assertEqual(m['matched'],20)

    def test_outlier_and_packet_gaps(self):
        mon=Monitor();mon.update(frame(5),1)
        m=mon.update(frame(8,2,1,True),2)
        self.assertEqual(mon.sequence_gaps,2)
        self.assertEqual(m['flow_x'],2)
        self.assertEqual(m['flow_y'],1)
        self.assertEqual(m['scatter_px'],0)
        self.assertGreater(m['p95_residual_px'],0)

    def test_static_drift_detected(self):
        mon=Monitor();test=StationaryTest(started_at=0)
        for i in range(15):
            f=frame(i,off_x=i)
            test.observe(f,mon.update(f,i/30))
        r=test.results()
        self.assertGreater(r['median_feature_rms_px'],3)
        self.assertGreater(r['median_first_last_shift_px'],12)

    def test_percentile_one_sample(self):
        from metrics import percentile
        self.assertEqual(percentile([3],.95),3)
        self.assertIsNone(percentile([],.5))

if __name__=='__main__':unittest.main()

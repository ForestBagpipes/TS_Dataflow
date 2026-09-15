"""Regression for recording a completed native call after manifest reuse."""
import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[2]/'scripts/v431_r5_chronos2_native_check.py'
spec=importlib.util.spec_from_file_location('c2_native_record',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class NativeRecordTest(unittest.TestCase):
    def test_repeated_bookkeeping_does_not_discard_prediction_record(self):
        original={'labels_read':False,'input_hash':'fixed-input','parent':'train-parent'}
        result=module.request_record(original,labels_read=False,prediction_hash='real-output',shape=[96])
        self.assertEqual(result['input_hash'],'fixed-input')
        self.assertEqual(result['prediction_hash'],'real-output')
        self.assertNotIn('prediction_hash',original)
    def test_labels_read_cannot_be_marked_as_legal_execution(self):
        with self.assertRaises(AssertionError):
            module.request_record({'labels_read':False},labels_read=True)

if __name__=='__main__':unittest.main()

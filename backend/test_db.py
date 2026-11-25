import unittest,tempfile
from pathlib import Path
import db
class BookingTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.old=db.DB; db.DB=Path(self.tmp.name)/'test.db'; db.init()
    def tearDown(self):
        db.DB=self.old; self.tmp.cleanup()
    def test_flow(self):
        slot=db.availability('Cardiology')[0]['slot_id']; a=db.book(slot,'9876543210'); self.assertEqual(a['status'],'confirmed'); self.assertIn('error',db.book(slot,'9876543211')); self.assertEqual(db.cancel('9876543211',a['appointment_id'])['status'],'not_found'); self.assertEqual(db.cancel('9876543210',a['appointment_id'])['status'],'cancelled'); self.assertIn(slot,[s['slot_id'] for s in db.availability('Cardiology')])
    def test_validation(self):
        with self.assertRaises(ValueError): db.phone_number('123')
        self.assertEqual(db.phone_number('+91 9876543210'),'9876543210')
if __name__=='__main__': unittest.main()

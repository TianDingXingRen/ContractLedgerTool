# -*- coding: utf-8 -*-
import os,sqlite3,tempfile,unittest
from datetime import date,timedelta
import ledger_store
class T1(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.od,self.odb=ledger_store.DATA_DIR,ledger_store.DB_PATH
        ledger_store.DATA_DIR=self.t.name
        ledger_store.DB_PATH=os.path.join(self.t.name,'t.db')
        ledger_store.init_db();ledger_store.run_migrations()
    def tearDown(self):
        ledger_store.close_connections()
        ledger_store.DATA_DIR,ledger_store.DB_PATH=self.od,self.odb
        self.t.cleanup()
    def test_create_get(self):
        cid=ledger_store.create_contract({'title':'Test'},{},'/f.docx')
        c=ledger_store.get_contract(cid)
        self.assertEqual(c['title'],'Test');self.assertEqual(c['status'],'draft')
class T2(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.od,self.odb=ledger_store.DATA_DIR,ledger_store.DB_PATH
        ledger_store.DATA_DIR=self.t.name
        ledger_store.DB_PATH=os.path.join(self.t.name,'t.db')
        ledger_store.init_db();ledger_store.run_migrations()
    def tearDown(self):
        ledger_store.close_connections()
        ledger_store.DATA_DIR,ledger_store.DB_PATH=self.od,self.odb
        self.t.cleanup()
    def test_soft_delete(self):
        cid=ledger_store.create_contract({'title':'T'},{},'/p.docx')
        self.assertEqual(ledger_store.list_contracts()['total'],1)
        ledger_store.soft_delete_contract(cid)
        self.assertEqual(ledger_store.list_contracts()['total'],0)
    def test_restore(self):
        cid=ledger_store.create_contract({'title':'T'},{},'/p.docx')
        ledger_store.soft_delete_contract(cid)
        self.assertEqual(ledger_store.restore_contract(cid),1)
    def test_permanent(self):
        cid=ledger_store.create_contract({'title':'T'},{},'/p.docx')
        ledger_store.soft_delete_contract(cid)
        self.assertEqual(ledger_store.permanently_delete_contract(cid),1)
        self.assertIsNone(ledger_store.get_contract(cid))
    def test_batch(self):
        ids=[ledger_store.create_contract({'title':'C%d'%i},{},'/p%d.docx'%i) for i in range(3)]
        self.assertEqual(ledger_store.batch_delete_contracts(ids),3)
    def test_expiring(self):
        t=date.today();soon=t+timedelta(days=10);later=t+timedelta(days=60)
        c1=ledger_store.create_contract({'title':'S','status':'signed','expiry_date':soon.strftime('%Y-%m-%d')},{},'/p1.docx')
        c2=ledger_store.create_contract({'title':'L','status':'signed','expiry_date':later.strftime('%Y-%m-%d')},{},'/p2.docx')
        ids=[c['id'] for c in ledger_store.get_expiring_contracts(days=30)]
        self.assertIn(c1,ids);self.assertNotIn(c2,ids)
class T3(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.od,self.odb=ledger_store.DATA_DIR,ledger_store.DB_PATH
        ledger_store.DATA_DIR=self.t.name
        ledger_store.DB_PATH=os.path.join(self.t.name,'t.db')
        ledger_store.init_db();ledger_store.run_migrations()
        self.cid=ledger_store.create_contract({'title':'T','amount':100000},{},'/p.docx')
    def tearDown(self):
        ledger_store.close_connections()
        ledger_store.DATA_DIR,ledger_store.DB_PATH=self.od,self.odb
        self.t.cleanup()
    def test_plan_crud(self):
        pid=ledger_store.insert_payment_plan(self.cid,{'phase_name':'test','due_amount':50000})
        plans=ledger_store.list_payment_plans(contract_id=self.cid)
        self.assertEqual(len(plans),1);self.assertEqual(plans[0]['phase_name'],'test')
    def test_create_with_plans(self):
        plans=[{'phase_name':'P1','due_amount':30000},{'phase_name':'P2','due_amount':70000}]
        cid,count=ledger_store.create_contract_with_plans({'title':'T2'},{},'/p2.docx',plans)
        self.assertEqual(count,2)
    def test_stats(self):
        ledger_store.insert_payment_plan(self.cid,{'phase_name':'P1','due_amount':100,'paid_amount':30,'confirm_status':'confirmed','payment_status':'partial','due_date':'2026-06-15'})
        s=ledger_store.get_payment_stats()
        self.assertEqual(s['total_due'],100);self.assertEqual(s['total_unpaid'],70)
if __name__=='__main__':unittest.main()

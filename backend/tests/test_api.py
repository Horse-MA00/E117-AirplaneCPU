import tempfile,unittest,concurrent.futures
from pathlib import Path
from backend.store import Store
from backend.server import number,ident
from llm_agent.runner import run,validate,scenario
from llm_agent.population import population,coverage
class StoreTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'demo.db')
 def tearDown(self):self.temp.cleanup()
 def test_concurrent_inventory_and_duplicate(self):
  s=self.store;o=s.offer('SYN-1',28,2,30,250,2)
  for i in range(8):s.member(f'c{i}',399)
  def buy(i):
   try:return s.book(o['id'],f'c{i}')
   except ValueError:return None
  with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:r=list(pool.map(buy,range(8)))
  self.assertEqual(sum(x is not None for x in r),2);self.assertEqual(s.offers()[0]['remaining'],0)
  with self.assertRaises(ValueError):s.offer('SYN-1',28,1,0,250,2)
 def test_membership_once_and_protected_supply(self):
  s=self.store;self.assertEqual(s.member('c',399),s.member('c',799))
  with self.assertRaises(ValueError):s.offer('f',28,3,0,250,2)
  o=s.offer('f',28,1,0,250,2);s.book(o['id'],'c');o2=s.offer('f',28,1,0,250,2)
  with self.assertRaises(ValueError):s.book(o2['id'],'c')
  with self.assertRaises(ValueError):s.offer('f',7,1,0,250,2)
 def test_agent_coverage_and_constraints(self):
  p=population(100);self.assertEqual(len({x['segment'] for x in p}),len(coverage()['segments']))
  a=run();self.assertEqual(a,run());self.assertEqual(a['source'],'deterministic_assumption')
  ctx=scenario(p[0]);
  with self.assertRaises(ValueError):validate({'action':'BUY_ILLEGAL'},ctx)
  with self.assertRaises(ValueError):run(count=10000)
 def test_commitments_expiry_and_membership_expiration(self):
  from unittest.mock import patch
  s=self.store
  with patch('backend.store.time.time',return_value=1000):
   o=s.offer('f',1,2,30,250,3);s.member('c',399)
   self.assertEqual(o['expires'],1000+22*3600)
   self.assertEqual(s.committed('f',1),2)
   self.assertIsNone(s.committed('f',7))
   s.book(o['id'],'c');self.assertEqual(s.committed('f',1),2)
  with patch('backend.store.time.time',return_value=1000+23*3600):
   self.assertEqual(s.committed('f',1),1)
  with patch('backend.store.time.time',return_value=1000+366*86400):
   with self.assertRaisesRegex(ValueError,'expired'):s.member('c',399)
 def test_numeric_validation(self):
  for x in (float('nan'),float('inf'),True,-1):
   with self.assertRaises(ValueError):number(x,'quantity',0,10)
  with self.assertRaises(ValueError):ident('../secret')
if __name__=='__main__':unittest.main()

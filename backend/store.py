"""Transactional demo inventory; no real payments or tickets."""
import sqlite3,time,uuid
from contextlib import contextmanager
from pathlib import Path

class Store:
 def __init__(self,path):
    self.path=str(path);Path(path).parent.mkdir(parents=True,exist_ok=True)
    with self.connect() as c:
      c.executescript('''CREATE TABLE IF NOT EXISTS offers(id TEXT PRIMARY KEY,flight_id TEXT,day INTEGER,quantity INTEGER,remaining INTEGER,base_fare REAL,fees REAL,created REAL,expires REAL);
      CREATE TABLE IF NOT EXISTS members(customer_id TEXT PRIMARY KEY,fee REAL,created REAL,expires REAL);
      CREATE TABLE IF NOT EXISTS bookings(id TEXT PRIMARY KEY,offer_id TEXT,flight_id TEXT,customer_id TEXT,total REAL,created REAL,UNIQUE(flight_id,customer_id));''')
 @contextmanager
 def connect(self):
    c=sqlite3.connect(self.path,timeout=10);c.row_factory=sqlite3.Row
    try:
      with c:yield c
    finally:c.close()
 def offers(self):
    with self.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM offers WHERE expires>? ORDER BY created DESC',(time.time(),))]
 def committed(self,flight,day):
    with self.connect() as c:
      rows=c.execute('SELECT * FROM offers WHERE flight_id=?',(flight,)).fetchall()
      if any(r['day']!=day for r in rows):return None
      return sum(r['quantity']-r['remaining']+(r['remaining'] if r['expires']>time.time() else 0) for r in rows)
 def offer(self,flight,day,quantity,fare,fees,max_release):
    now=time.time()
    with self.connect() as c:
      c.execute('BEGIN IMMEDIATE')
      existing=c.execute('SELECT * FROM offers WHERE flight_id=?',(flight,)).fetchall()
      if existing and any(r['day']!=day for r in existing):raise ValueError('This flight already has a different simulation day. Use another flight or a fresh demo database.')
      committed=sum(r['quantity']-r['remaining']+(r['remaining'] if r['expires']>now else 0) for r in existing)
      if quantity>max_release-committed:raise ValueError('Quantity exceeds uncommitted protected inventory')
      id=str(uuid.uuid4());c.execute('INSERT INTO offers VALUES(?,?,?,?,?,?,?,?,?)',(id,flight,day,quantity,quantity,fare,fees,now,now+min(86400,max(0,day*86400-7200))))
      return dict(c.execute('SELECT * FROM offers WHERE id=?',(id,)).fetchone())
 def member(self,customer_id,fee):
    now=time.time()
    with self.connect() as c:
      c.execute('BEGIN IMMEDIATE');row=c.execute('SELECT * FROM members WHERE customer_id=?',(customer_id,)).fetchone()
      if row:
       if row['expires']<=now:raise ValueError('Membership expired; renewal is not implemented in this demo')
       return dict(row)
      c.execute('INSERT INTO members VALUES(?,?,?,?)',(customer_id,fee,now,now+365*86400))
      return dict(c.execute('SELECT * FROM members WHERE customer_id=?',(customer_id,)).fetchone())
 def book(self,offer_id,customer_id):
    with self.connect() as c:
      c.execute('BEGIN IMMEDIATE')
      member=c.execute('SELECT * FROM members WHERE customer_id=? AND expires>?',(customer_id,time.time())).fetchone()
      if not member:raise ValueError('An active demo membership is required')
      offer=c.execute('SELECT * FROM offers WHERE id=? AND expires>?',(offer_id,time.time())).fetchone()
      if not offer or offer['remaining']<1:raise ValueError('Offer unavailable or sold out')
      if c.execute('SELECT 1 FROM bookings WHERE flight_id=? AND customer_id=?',(offer['flight_id'],customer_id)).fetchone():raise ValueError('This customer already booked this flight')
      id=str(uuid.uuid4());total=offer['base_fare']+offer['fees']
      c.execute('UPDATE offers SET remaining=remaining-1 WHERE id=? AND remaining>0',(offer_id,))
      c.execute('INSERT INTO bookings VALUES(?,?,?,?,?,?)',(id,offer_id,offer['flight_id'],customer_id,total,time.time()))
      return {'booking':dict(c.execute('SELECT * FROM bookings WHERE id=?',(id,)).fetchone()),'remaining':offer['remaining']-1,'simulated':True}

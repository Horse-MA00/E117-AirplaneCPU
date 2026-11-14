"""Coverage scenarios, NOT an estimated HK Express demographic distribution."""
import random

SEGMENTS = [
 ('flexible_budget','Flexible budget traveller',.13,3,600,5),
 ('student','Student on term breaks',.09,2,500,3),
 ('fixed_holiday','Fixed-leave employee',.14,2,1000,0),
 ('frequent_leisure','Frequent leisure traveller',.10,6,900,4),
 ('family','Family on school holidays',.12,2,1200,1),
 ('couple','Couple on a short break',.10,3,1000,2),
 ('visiting_friends','Visiting friends and relatives',.08,4,1100,2),
 ('urgent_trip','Urgent essential traveller',.04,2,1600,0),
 ('small_business','Self-funded business traveller',.04,5,1500,1),
 ('inbound','Inbound and cross-market traveller',.05,2,1000,2),
 ('group','Small travel group',.03,2,900,1),
 ('access_needs','Traveller needing assistance',.02,2,1100,1),
 ('infrequent','Infrequent or first-time traveller',.04,1,650,1),
 ('no_match','No matching route or dates',.02,2,700,0),
]

def population(count=100, seed=117):
    if not isinstance(count,int) or not 1 <= count <= 10000: raise ValueError('count must be 1..10000')
    rng=random.Random(seed); people=[]
    # Coverage first, then illustrative mixture; weights remain explicit assumptions.
    for i in range(count):
        seg=SEGMENTS[i] if i<len(SEGMENTS) else rng.choices(SEGMENTS,weights=[s[2] for s in SEGMENTS])[0]
        key,label,weight,trips,budget,flex=seg
        people.append(dict(customer_id=f'SYN-{seed}-{i+1:05d}',segment=key,segment_label=label,
          source='assumed_customer_scenario',expected_trips=trips,total_budget=round(budget*rng.uniform(.8,1.2)),
          flexibility_days=flex,party_size=3 if key in ('family','group') else 1,
          minimum_notice_days=21 if key in ('family','access_needs') else 3,
          route_match=key!='no_match',language=rng.choice(['zh-HK','en','ja']),
          perceived_availability=round(rng.uniform(.15,.65),3),membership_active=False))
    return people

def coverage():
    return dict(source='hypothetical_coverage_not_market_shares',segments=[dict(id=s[0],name=s[1],assumed_weight=s[2]) for s in SEGMENTS],
      dimensions=['Travel purpose','Frequency','Date flexibility','Budget','Party size','Minimum notice','Inbound or outbound','Background language','Route match','Membership status'],
      limitations=['No observed HK Express segment weights or payment data.','Coverage scenarios do not establish representation of the actual market.','Full payable prices and uncertain member availability must be shown.'])

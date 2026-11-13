"""Coverage scenarios, NOT an estimated HK Express demographic distribution."""
import random

SEGMENTS = [
 ('flexible_budget','彈性低預算旅客',.13,3,600,5),
 ('student','學生與學期假期',.09,2,500,3),
 ('fixed_holiday','固定假期上班族',.14,2,1000,0),
 ('frequent_leisure','高頻休閒旅客',.10,6,900,4),
 ('family','家庭及學校假期',.12,2,1200,1),
 ('couple','雙人短途旅行',.10,3,1000,2),
 ('visiting_friends','探親訪友',.08,4,1100,2),
 ('urgent_trip','臨時必要出行',.04,2,1600,0),
 ('small_business','自費商務出行',.04,5,1500,1),
 ('inbound','入境及跨市場旅客',.05,2,1000,2),
 ('group','同行小組',.03,2,900,1),
 ('access_needs','有協助與安排需求',.02,2,1100,1),
 ('infrequent','低頻及首次旅行',.04,1,650,1),
 ('no_match','無合適航線或日期',.02,2,700,0),
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
      dimensions=['出行目的','頻次','日期彈性','預算','同行人數','提前安排時間','入境或出境','語言','航線匹配','會員狀態'],
      limitations=['沒有真實 HK Express 客群權重或支付資料','群體情境不能證明代表整個實際市場','機票稅費與會員可用性均需展示'])

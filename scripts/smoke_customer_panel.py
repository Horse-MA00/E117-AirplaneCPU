"""Exercise the real background HTTP panel at scale without any LLM calls."""
import argparse
import json
from pathlib import Path
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=1000)
    parser.add_argument('--origin', default='http://127.0.0.1:8000')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if not 1 <= args.count <= 1000:
        parser.error('count must be 1..1000')

    def request(path, body=None):
        req = urllib.request.Request(args.origin+path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Content-Type':'application/json', 'Origin':args.origin})
        with urllib.request.urlopen(req,timeout=30) as response:
            return json.load(response)

    started = time.monotonic()
    run = request('/api/agents/panels', {'mode':'deterministic','count':args.count,'max_calls':0,
                                       'member_fare':70,'membership_fee':399,'seed':117})
    print(f"Started {args.count}-traveller rules panel {run['run_id']}",flush=True)
    while True:
        result = request('/api/agents/panels/'+run['run_id'])
        if result['status'] not in ('queued','running'):
            break
        if time.monotonic()-started > 120:
            raise AssertionError('Panel timed out; inspect its saved checkpoint')
        time.sleep(.5)
    assert result['status']=='completed', result.get('error',result['status'])
    assert result['progress']['completed_stages']==6*args.count
    assert result['summary']['completed_customers']==args.count
    assert result['runtime']['provider_calls']==result['runtime']['failures']==0
    assert result['runtime']['forced_actions']+result['runtime']['rule_decisions']==6*args.count
    for row in result['results']:
        person,state=row['person'],row['final_state']
        assert abs(state['remaining_budget']-(person['total_budget']-state['membership_fee_paid']-state['ticket_spend']+state['refund_received']))<1e-8
        assert state['remaining_budget']>=0
    detail=request('/api/agents/panels/'+run['run_id']+'/people/'+result['results'][0]['person']['customer_id'])
    assert len(detail['events'])==6
    report={key:result[key] for key in ('run_id','audit_run_id','prompt_version','mode','count','progress','runtime','summary','segments','provenance')}
    report.update(status='passed',elapsed_seconds=round(time.monotonic()-started,2),
                  checks={'all_stages':True,'all_person_budgets':True,'zero_provider_calls':True,'detail_endpoint':True},
                  scope='Synthetic independent journey scale test; not customer conversion ground truth.')
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2))
    print(json.dumps({key:report[key] for key in ('status','count','progress','runtime','elapsed_seconds')},indent=2))


if __name__=='__main__':
    main()

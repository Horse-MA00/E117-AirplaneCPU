"""Export one reproducible pricing experiment without running the web UI."""
import argparse,json
from pathlib import Path
from .data import history
from .nhpp import forecast
from .pricing import optimize

def main():
 p=argparse.ArgumentParser();p.add_argument('--flight',default='SYN-00001');p.add_argument('--day',type=int,default=28);p.add_argument('--output',default='.runtime/pricing_experiment.json');a=p.parse_args()
 prediction=forecast(history(a.flight),a.day);result=optimize(prediction,{})
 target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps({'forecast':prediction,'pricing':result},ensure_ascii=False,indent=2))
 print(json.dumps({'output':str(target),'candidate_count':len(result['candidates']),'decision':result['best']['decision'],'source':'synthetic'},ensure_ascii=False))
if __name__=='__main__':main()

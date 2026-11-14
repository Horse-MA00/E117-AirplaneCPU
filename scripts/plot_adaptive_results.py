"""Render the saved offline and live evidence without re-running any market."""
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('MPLCONFIGDIR',str(Path(__file__).resolve().parents[1]/'.runtime/matplotlib'))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]


def main():
    evidence = ROOT/'llm_agent/experiments'
    benchmark = json.loads((evidence/'thompson_math_benchmark_20261114_v2/report.json').read_text())
    live = json.loads((evidence/'thompson_live_20261114_v2/report.json').read_text())
    fig, axes = plt.subplots(1,2,figsize=(12,5.4))
    fig.patch.set_facecolor('white')
    groups = [r for r in benchmark['summary']['groups'] if r['family']=='all']
    groups.sort(key=lambda row:row['method']=='thompson')
    left = [r['mean_member_revenue'] for r in groups]
    axes[0].bar(['Greedy MAP','Thompson Sampling'],left,color=['#a6a2ad','#6F2C91'],width=.55)
    axes[0].set_title('Offline: same model, different exploration',fontsize=12,loc='left',pad=18)
    axes[0].set_ylabel('Mean expected member base receipts (HK$)')
    axes[0].set_ylim(0,max(left)*1.23)
    fig.text(.065, .025,'80 matched cases / 20 seeds\nSynthetic demand, independent analytic holdout',fontsize=9,color='#55515b')
    comparison = live['validation']['comparisons']
    right = [r['mean_weighted_revenue'] for r in comparison]
    labels = ['Initial\nHK$328','Selected test\nHK$251.98','No member offer']
    axes[1].bar(labels,right,color=['#a6a2ad','#6F2C91','#24BCDC'],width=.55)
    axes[1].set_title('Live LLM: selected price failed validation',fontsize=12,loc='left',pad=18)
    axes[1].set_ylabel('Weighted mean total base receipts (HK$)')
    axes[1].set_ylim(0,max(right)*1.23)
    fig.text(.555,.025,'2 independent panels / 20 existing members each\nAssumed segment weights; revenue excludes all costs',fontsize=9,color='#55515b')
    for axis, values in zip(axes,(left,right)):
        for x,value in enumerate(values):
            axis.text(x,value+max(values)*.025,f'{value:,.2f}',ha='center',fontsize=10)
        axis.spines[['top','right']].set_visible(False)
        axis.grid(axis='y',alpha=.15)
        axis.set_axisbelow(True)
    fig.suptitle('Thompson pricing: gains in synthetic benchmarks, no live revenue gain yet',fontsize=14,y=.98)
    fig.tight_layout(rect=(0,.14,1,.93),w_pad=3)
    output = ROOT/'docs/assets/thompson-pricing-comparison.png'
    output.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(output,dpi=180,bbox_inches='tight')
    print(output.relative_to(ROOT))


if __name__ == '__main__':
    main()

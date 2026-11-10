"""Έλεγχος προτεινόμενης ποσότητας έναντι της πραγματικής επόμενης αγοράς (επιπλέον proxy, όχι επίσημη βαθμολογία).

    uv run python experiments/validate_quantity.py --output experiments/results/quantity_v5.csv
"""
import argparse
from pathlib import Path
import pandas as pd
from forecast.ingest import load
from forecast.models import components, with_cfg
from forecast.backtest import history, targets
from forecast.suggest import quantity

CUTS = ['2025-10-31','2025-11-29','2025-10-04','2025-09-20','2025-11-22','2025-12-06','2026-04-04','2026-06-06','2026-07-04']

def evaluate():
    d=load(); rows=[]
    for cut in CUTS:
        c=pd.Timestamp(cut); h,tg=history(d,c),targets(d,c)
        future=d.daily[(d.daily.DATE>c)&(d.daily.DATE<=c+pd.Timedelta(days=90))&(d.daily.gross>0)]
        actual=future.sort_values('DATE').groupby(['TRDR','MTRL']).first().gross
        for name,days in [('hybrid_v4',180),('hybrid_v5',365)]:
            x=with_cfg(components,name,cadence_days=days,adaptive_promo=True)(d,h,tg,c)
            x['q']=[quantity(r)[0] for r in x.itertuples()]
            x['actual']=pd.MultiIndex.from_frame(x[['TRDR','MTRL']]).map(actual).to_numpy()
            eligible=x.actual.notna()&x.DATE.notna()
            rows.append({'cutoff':cut,'model':name,'n':int(eligible.sum()),'mae_qty':(x.loc[eligible,'q']-x.loc[eligible,'actual']).abs().mean()})
    return pd.DataFrame(rows)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);a=p.parse_args()
    r=evaluate()
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True);r.to_csv(a.output,index=False)
    print(r.pivot(index='cutoff',columns='model',values='mae_qty').round(4).to_string())
    print(r.groupby('model').mae_qty.mean().to_string())

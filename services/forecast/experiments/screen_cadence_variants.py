"""Περιορισμένο screening δεύτερου γύρου, πάνω στις 17 ήδη εξετασμένες ημερομηνίες.

Ακολουθεί χωριστό confirmation_v5 στο validate_adaptive_promo.py.
    uv run python experiments/screen_cadence_variants.py --output experiments/results/cadence_screening.csv
Δεν γράφει submission/runtime δεδομένα.
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from forecast.ingest import load
from forecast.backtest import history,targets,CALIBRATED_FAMILY,truth_next_purchase
from forecast.models import components,REGISTRY,_pair_intervals,with_cfg
from forecast.score import score,pair_errors
from forecast.promo import adaptive_promo_multiplier
from forecast import promo as P
DEV=['2025-10-31','2025-11-29','2025-10-04','2025-09-13','2025-10-18','2025-11-15','2025-12-13','2026-03-14','2026-05-16','2026-07-18','2026-08-01','2025-09-27','2025-11-08','2025-12-20','2026-04-18','2026-06-20','2026-08-02']
FAMILY={'calibrated':(2,.1),'proxy':(0,0),**CALIBRATED_FAMILY}
D=load()
def factor(h,tg,c,profile):
    iv=_pair_intervals(h,c,days=365 if profile=='normal365' else 180)
    if profile!='promo_type':
        old=(P.CATEGORY_PRIOR,P.PAIR_PRIOR,P.LOOKBACK_DAYS)
        try:
            P.CATEGORY_PRIOR=10 if profile=='less_shrinkage' else 30
            P.PAIR_PRIOR=2 if profile=='less_shrinkage' else 5
            P.LOOKBACK_DAYS={'promo_long':730,'promo_recent':180}.get(profile,365)
            mult=adaptive_promo_multiplier(h,D.items,iv,tg,c)
        finally:P.CATEGORY_PRIOR,P.PAIR_PRIOR,P.LOOKBACK_DAYS=old
        return mult,iv
    b=h[h.gross>0].sort_values('DATE').copy();b['gap']=b.groupby(['TRDR','MTRL']).DATE.shift(-1).sub(b.DATE).dt.days
    b=b.merge(iv,on=['TRDR','MTRL']).merge(D.items[['MTRL','MTRCATEGORY']],on='MTRL').merge(D.customers[['TRDR','TRDCATEGORY']],on='TRDR')
    b['ratio']=b.gap/b.interval
    b=b[b.in_promo&b.gap.notna()&b.ratio.between(.5,4)&(b.DATE>c-pd.Timedelta(days=365))]
    cat=b.groupby('MTRCATEGORY').ratio.agg(['median','count']);cat['mult']=(cat['median']*cat['count']+30*1.8)/(cat['count']+30)
    types=b.groupby(['MTRCATEGORY','TRDCATEGORY']).ratio.agg(['median','count']);cp=types.index.get_level_values(0).map(cat.mult).to_numpy(float)
    types['mult']=(types['median']*types['count']+15*cp)/(types['count']+15)
    x=tg.merge(D.items[['MTRL','MTRCATEGORY']],on='MTRL').merge(D.customers[['TRDR','TRDCATEGORY']],on='TRDR')
    ix=pd.MultiIndex.from_frame(x[['MTRCATEGORY','TRDCATEGORY']]);prior=ix.map(types.mult).to_numpy(float);cp=x.MTRCATEGORY.map(cat.mult).fillna(1.8).to_numpy(float);prior=np.where(np.isfinite(prior),prior,cp)
    pairs=b.groupby(['TRDR','MTRL']).ratio.agg(['median','count']);ix=pd.MultiIndex.from_frame(x[['TRDR','MTRL']])
    n=ix.map(pairs['count']).fillna(0).to_numpy(float);med=ix.map(pairs['median']).fillna(1.8).to_numpy(float)
    return np.clip((n*med+5*prior)/(n+5),1,3),iv

def predict(x,h,tg,c,profile):
    if profile=='v4':return REGISTRY['hybrid_v4'](D,h,tg,c)
    mult,iv=factor(h,tg,c,profile);interval=x.interval.copy()
    if profile=='normal365':
        vals=pd.MultiIndex.from_frame(x[['TRDR','MTRL']]).map(iv.set_index(['TRDR','MTRL']).interval)
        interval=pd.Series(vals,index=x.index).fillna(interval)
    kd=(np.ceil(interval*np.where(x.last_in_promo,mult,1))-(c-x.last_date).dt.days).clip(lower=3);yd=(x.date_yoy-c).dt.days
    days=(.9*kd+(1-.9)*yd+3).round().clip(lower=1)
    return x[['TRDR','MTRL']].assign(DATE=(c+pd.to_timedelta(days,unit='D')).where(x.date_yoy.notna()))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);args=parser.parse_args()
    rows=[]
    for cut in DEV:
        c=pd.Timestamp(cut);h,tg=history(D,c),targets(D,c);x=with_cfg(components,'v4_frame',cadence_days=180)(D,h,tg,c)
        predictions={n:predict(x,h,tg,c,n) for n in ['v4','promo_long','promo_recent','less_shrinkage','promo_type','normal365']}
        for truth,ab in FAMILY.items():
            t=truth_next_purchase(D,c,tg,*ab)
            for n,p in predictions.items():rows.append({'cutoff':cut,'truth':truth,'model':n,**score(p,t,c)})
        print(cut,flush=True)
    r=pd.DataFrame(rows)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);r.to_csv(args.output,index=False)
    print(r.pivot_table(index='model',columns='truth',values='mae').round(4).to_string())
    print(r[r.truth.eq('calibrated')].pivot(index='cutoff',columns='model',values='mae').to_string())

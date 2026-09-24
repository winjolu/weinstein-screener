"""GP1: is a large gap followed by a fade?

Registered in docs/preregistered-tests.md on 2026-09-18, before this ran.
The file itself was lost with the registration when the synced folder it
lived in failed, and is restored from the working record of that day.
Two lines differ from what ran: the archive is opened through the shared
read-only helper instead of a literal path, and the event table is no
longer pickled to /tmp. The arithmetic is untouched.

It runs at import, as the original did, so it is not imported from
anywhere: run it as `python -m screener.gap_study`, about four minutes.

### Where the run departs from the registration

Recorded rather than fixed, because fixing them now would be a second
run chosen after seeing the first. All four make |t| look larger than it
is, so none of them can rescue a refuted hypothesis; they only mean the
reported t-values are upper bounds.

- **The t-value is on the raw mean, not the costed excess.** The
  registration judges H1 "after 8% borrow and 0.25% slippage per side",
  but `nw` tests the uncosted long-side mean against zero. Costs and the
  baseline shift the mean toward zero without being in the test.
- **Ten Newey-West lags against 21- and 63-day overlap.** The
  registration fixed 10 lags. Consecutive event days share up to 62
  days of forward return, so the standard errors at the two longer
  horizons are too small.
- **An event that delists inside its horizon is dropped.** There is no
  delisting return, so a short that would have ridden a failure to zero
  and one caught in a takeover are both removed.
- **Breakeven slippage is not reported by size bucket**, though the
  registration asks for it. Only the pooled gap bands carry it.
"""
import sqlite3, time
import numpy as np, pandas as pd, statsmodels.api as sm
t0=time.time()
def log(m): print(f"{m} ({time.time()-t0:.0f}s)", flush=True)
from market_core import sharadar
c=sharadar.connect_ro()
HOR=(5,21,63); DAY_BASIS=360.0; CAL_PER_TD=365/252
tk=pd.read_sql("SELECT ticker,exchange,category FROM tickers WHERE tbl='SEP'",c)
keep=set(tk[tk.exchange.isin(["NYSE","NASDAQ","NYSEARCA","NYSEMKT","BATS"])
 & tk.category.str.startswith("Domestic Common Stock",na=False)].ticker)
b=pd.read_sql("SELECT date,open,close,closeadj FROM fundprices WHERE ticker='IWM' ORDER BY date",c)
bd=b.date.to_numpy(); bo=b.open.to_numpy(float); bcl=b.close.to_numpy(float); bca=b.closeadj.to_numpy(float)
mgap=np.full(len(bd),np.nan); mgap[1:]=bo[1:]/bcl[:-1]-1.0
mgap_by_date=dict(zip(bd,mgap))
log("benchmark loaded")
cap=pd.read_sql("SELECT ticker,date,marketcap FROM dailyfundamentals WHERE marketcap!='' ORDER BY ticker,date",c)
cap["marketcap"]=pd.to_numeric(cap.marketcap,errors="coerce")*1e6
capmap={t:(g.date.to_numpy(),g.marketcap.to_numpy(float)) for t,g in cap.groupby("ticker",sort=False)}
del cap; log("market caps loaded")
px=pd.read_sql("SELECT ticker,date,open,close,closeadj,volume FROM prices WHERE date>='2007-06-01' ORDER BY ticker,date",c)
log(f"price rows {len(px):,}")
rows=[]
for t,g in px.groupby("ticker",sort=False):
    if t not in keep or len(g)<80: continue
    d=g.date.to_numpy(); o=g.open.to_numpy(float); cl=g.close.to_numpy(float)
    ca=g.closeadj.to_numpy(float); v=g.volume.to_numpy(float)
    gap=np.full(len(d),np.nan); gap[1:]=o[1:]/cl[:-1]-1.0
    dv=pd.Series(cl*v).rolling(20).median().to_numpy()
    mk=np.array([mgap_by_date.get(x,np.nan) for x in d])
    ok=np.isfinite(gap)&np.isfinite(mk)&(cl>=5)&np.isfinite(dv)&(dv>=1e6)
    idx=np.flatnonzero(ok)
    if idx.size==0: continue
    caps=np.full(idx.size,np.nan)
    if t in capmap:
        cd,cv=capmap[t]; ci=np.searchsorted(cd,d[idx],side="right")-1
        caps=np.where(ci>=0,cv[np.clip(ci,0,None)],np.nan)
    rec={"ticker":t,"date":d[idx],"xgap":(gap[idx]-mk[idx])*100,"cap":caps}
    for h in HOR:
        j=idx+h; val=j<len(d); r=np.full(idx.size,np.nan)
        r[val]=(ca[j[val]]/ca[idx[val]]-1.0)*100
        rec[f"f{h}"]=r
    rows.append(pd.DataFrame(rec))
e=pd.concat(rows,ignore_index=True); del rows,px
bi=np.searchsorted(bd,e.date.to_numpy(),side="right")-1
for h in HOR:
    j=np.minimum(bi+h,len(bca)-1)
    e[f"a{h}"]=e[f"f{h}"]-(np.where(bi>=0,bca[j]/bca[np.maximum(bi,0)]-1.0,np.nan))*100
log(f"events {len(e):,}")

def nw(y):
    y=np.asarray(y,float); y=y[np.isfinite(y)]
    if len(y)<30: return np.nan,np.nan,0
    f=sm.OLS(y,np.ones((len(y),1))).fit(cov_type="HAC",cov_kwds={"maxlags":10})
    return float(f.params[0]),float(f.tvalues[0]),len(y)

BUCKETS=[("micro <$300M",0,3e8),("small $300M-2B",3e8,2e9),("mid $2-10B",2e9,1e10),("large >$10B",1e10,1e15)]
WINDOWS=[("pooled 2007-2026","0000","9999"),("recent 2023-2025","2023-01-01","2025-12-31")]
for wname,lo,hi in WINDOWS:
    w=e[(e.date>=lo)&(e.date<=hi)]
    print(f"\n########## {wname}: {len(w):,} observations ##########")
    for h in HOR:
        base_m,_,_=nw(w.groupby("date")[f"a{h}"].mean())
        borrow={"GC":1.0,"HTB":8.0}
        print(f"\n--- {h} trading days (baseline: average stock {base_m:+.2f}% vs IWM) ---")
        for glab,glo,ghi in [("xgap +5 to 10%",5,10),("xgap > +10%",10,1e9),("xgap < -10%",-1e9,-10)]:
            sel=w[(w.xgap>glo)&(w.xgap<=ghi)]
            if len(sel)<200: continue
            m,t,n=nw(sel.groupby("date")[f"a{h}"].mean())
            adj=m-base_m
            days=h*CAL_PER_TD
            gc=-adj-(borrow["GC"]/100*days/DAY_BASIS*100)
            htb=-adj-(borrow["HTB"]/100*days/DAY_BASIS*100)
            be=(htb/2)
            print(f"  {glab:16s} n={len(sel):>7,} long-side {m:+.2f}% (vs base {adj:+.2f}%) t={t:+.2f} "
                  f"| short net GC {gc:+.2f}% HTB {htb:+.2f}% | breakeven slippage/side {be:+.3f}%")
            for slip in (0.10,0.25,0.50):
                print(f"      after {slip:.2f}%/side slippage: GC {gc-2*slip:+.2f}%  HTB {htb-2*slip:+.2f}%")
        print("   by size (xgap > +10%):")
        big=w[w.xgap>10]
        for blab,blo,bhi in BUCKETS:
            sb=big[(big.cap>blo)&(big.cap<=bhi)]
            if len(sb)<200: print(f"     {blab:16s} too few ({len(sb)})"); continue
            bb=w[(w.cap>blo)&(w.cap<=bhi)]
            base_b,_,_=nw(bb.groupby("date")[f"a{h}"].mean())
            m,t,n=nw(sb.groupby("date")[f"a{h}"].mean())
            days=h*CAL_PER_TD
            htb=-(m-base_b)-(8.0/100*days/DAY_BASIS*100)
            print(f"     {blab:16s} n={len(sb):>6,} {m:+.2f}% (vs base {m-base_b:+.2f}%) t={t:+.2f} | short net HTB {htb:+.2f}%")
log("done")
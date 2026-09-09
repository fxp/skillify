# -*- coding: utf-8 -*-
"""弱执行器轮（glm-4.5-flash）v1 vs v2：准确率与 token。"""
import json, pathlib, statistics, math
from math import comb

HERE = pathlib.Path(__file__).resolve().parent
def fisher(a,b,c,d):
    n=a+b+c+d; r1=a+b; c1=a+c
    p=lambda x: comb(r1,x)*comb(n-r1,c1-x)/comb(n,c1)
    o=p(a); lo=max(0,c1-(n-r1)); hi=min(r1,c1)
    return sum(p(x) for x in range(lo,hi+1) if p(x)<=o+1e-12)

def mw(a,b):
    n1,n2=len(a),len(b); al=sorted([(v,0) for v in a]+[(v,1) for v in b])
    vals=[v for v,_ in al]; r=[0.0]*len(vals); i=0
    while i<len(vals):
        j=i
        while j+1<len(vals) and vals[j+1]==vals[i]: j+=1
        for k in range(i,j+1): r[k]=(i+j)/2+1
        i=j+1
    r1=sum(r[k] for k in range(len(al)) if al[k][1]==0)
    u1=r1-n1*(n1+1)/2; mu=n1*n2/2; sd=(n1*n2*(n1+n2+1)/12)**.5
    if sd==0: return 1.0
    return 2*(1-0.5*(1+math.erf(abs((u1-mu)/sd)/math.sqrt(2))))

VERS = ("v1", "v2", "v4")
S = {v: json.loads((HERE/f"summary-{v}.json").read_text(encoding="utf-8")) for v in ("v1","v2","v4")}

print("="*84); print("一、准确率（执行 Agent = glm-4.5-flash，n=5）"); print("="*84)
print(f"{'场景':30s}" + "".join(f"{v+' 满分':>9s}" for v in VERS) + "".join(f"{v+' 均分':>9s}" for v in VERS))
F={v:0 for v in VERS}; A={v:[] for v in VERS}
for k in S["v1"]:
    cs={}
    for v in VERS:
        s=S[v][k]["scores"]; cs[v]=sum(1 for x in s if x>=0.999); F[v]+=cs[v]; A[v]+=s
    flag=" ↑" if cs["v4"]>cs["v1"] else (" ↓" if cs["v4"]<cs["v1"] else "")
    print(f"{k:30s}" + "".join(f"{cs[v]:>7d}/5" for v in VERS)
          + "".join(f"{statistics.mean(S[v][k]['scores']):>9.3f}" for v in VERS) + flag)
print("-"*84)
print(f"{'合计':30s}" + "".join(f"{F[v]:>6d}/40" for v in VERS)
      + "".join(f"{statistics.mean(A[v]):>9.3f}" for v in VERS))
print()
for v in ("v2","v4"):
    pf=fisher(F[v],40-F[v],F["v1"],40-F["v1"]); pm=mw(A[v],A["v1"])
    print(f"{v} vs v1： 满分率 {F[v]}/40 vs {F['v1']}/40  Fisher p={pf:.4f}"
          f"{'  ← 显著' if pf<0.05 else ''}   逐次得分 MW p={pm:.4f}{'  ← 显著' if pm<0.05 else ''}")

# ---- token ----
src=(HERE.parent.parent/"token-cost"/"aggregate_tokens.py").read_text(encoding="utf-8")
ns={"__name__":"c"}; exec(src.split('print(f"采集到')[0], ns)
usage_of=ns["usage_of"]
P="-Users-chopinfeng-Workspace-Skillify-bigmodel-cn-workspace-weak-exec-"
print("\n"+"="*84); print("二、token"); print("="*84)
tok={}
for v in ("v1","v2","v4"):
    rows=[]
    for sc in S["v1"]:
        for r in range(1,6):
            u=usage_of(f"{P}{v}-{sc}-run-{r}")
            if u: rows.append(u)
    tok[v]=rows
    print(f"{v}: n={len(rows):>2d}  wire={statistics.mean(x['wire'] for x in rows):>10,.0f}  "
          f"计费当量={statistics.mean(x['billable'] for x in rows):>9,.0f}  "
          f"Read={statistics.mean(x['reads'] for x in rows):.1f}  轮数={statistics.mean(x['turns'] for x in rows):.1f}")
for v in ("v2","v4"):
    for key,name in (("wire","线上总 token"),("billable","计费当量")):
        a=[x[key] for x in tok[v]]; b=[x[key] for x in tok["v1"]]
        d=(statistics.mean(a)-statistics.mean(b))/statistics.mean(b)*100
        print(f"  {v} 的{name}： 相对 v1 {d:+.1f}%   MW p={mw(a,b):.4f}")

print("\n"+"="*84); print("三、每做对一次的计费当量"); print("="*84)
cps={}
for v in VERS:
    tot=sum(x["billable"] for x in tok[v]); cps[v]=tot/F[v]
    print(f"{v}: {cps[v]:>10,.0f}   (总花费 {tot:,} ÷ 成功 {F[v]} 次)")
for v in ("v2","v4"):
    print(f"  {v} 相对 v1： {cps[v]/cps['v1']-1:+.1%}")
print()
ok_acc = F["v4"] > F["v1"]
ok_tok = statistics.mean(x["billable"] for x in tok["v4"]) <= statistics.mean(x["billable"] for x in tok["v1"])
print("="*84); print("四、对照冻结的达成标准"); print("="*84)
print(f"  准确率 v4 满分率 > v1 的 {F['v1']}/40 ： {F['v4']}/40  → {'✅ 满足' if ok_acc else '❌ 不满足'}")
print(f"  token  v4 计费当量 ≤ v1        ： {statistics.mean(x['billable'] for x in tok['v4']):,.0f} vs {statistics.mean(x['billable'] for x in tok['v1']):,.0f}  → {'✅ 满足' if ok_tok else '❌ 不满足'}")
print(f"\n  两条同时满足 → {'✅ 达成' if (ok_acc and ok_tok) else '❌ 未达成'}")

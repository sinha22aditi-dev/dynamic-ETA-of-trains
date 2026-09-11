import os, json, random
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
import torch
from torch.utils.data import TensorDataset, DataLoader
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, accuracy_score, f1_score
from sklearn.pipeline import Pipeline
from xgboost import XGBRegressor, XGBClassifier

from config import *
from preprocess import build_xgb_features, add_time_features
from models import GRURegressor, HybridGNNGRU

random.seed(RANDOM_STATE); np.random.seed(RANDOM_STATE); torch.manual_seed(RANDOM_STATE)

def rmse(y,p): return float(np.sqrt(mean_squared_error(y,p)))

def split_groups(df):
    groups=df["sequence_id"].values
    gss=GroupShuffleSplit(n_splits=1,test_size=.20,random_state=RANDOM_STATE)
    tr,te=next(gss.split(df,groups=groups))
    train=df.iloc[tr].copy(); test=df.iloc[te].copy()
    gss2=GroupShuffleSplit(n_splits=1,test_size=.1875,random_state=RANDOM_STATE+1)
    tr2,val=next(gss2.split(train,groups=train["sequence_id"].values))
    return train.iloc[tr2].copy(),train.iloc[val].copy(),test

def make_tabular_target(df):
    # 20-minute target from the same sequence, never from another train.
    d=df.sort_values(["sequence_id","timestamp"]).copy()
    d["future_delay_target"] = d.groupby("sequence_id")["current_delay_mins"].shift(-HORIZON_STEPS) - d["current_delay_mins"]
    return d

def train_xgb(df_train, df_test):
    a=df_train.dropna(subset=["future_delay_target"]).copy(); b=df_test.dropna(subset=["future_delay_target"]).copy()
    Xtr,prep,features=build_xgb_features(a); Xte=add_time_features(b)[features].copy()
    ytr=a["future_delay_target"].astype(float); yte=b["future_delay_target"].astype(float)
    model=XGBRegressor(n_estimators=500,max_depth=4,learning_rate=.035,subsample=.85,
                       colsample_bytree=.85,min_child_weight=5,reg_lambda=2,
                       objective="reg:squarederror",random_state=RANDOM_STATE,n_jobs=-1)
    pipe=Pipeline([("prep",prep),("model",model)])
    pipe.fit(Xtr,ytr); p=pipe.predict(Xte)
    metrics={"mae":float(mean_absolute_error(yte,p)),"rmse":rmse(yte,p),"r2":float(r2_score(yte,p))}
    joblib.dump(pipe,MODEL_DIR/"xgb_delay.joblib")
    return metrics,features

def seq_samples(df):
    # Windows are built within each sequence; target is current_delay at t+20m minus delay at t.
    d=df.sort_values(["sequence_id","timestamp"]).copy()
    for c in NEURAL_NUMERIC_FEATURES:
        d[c]=pd.to_numeric(d[c],errors="coerce").fillna(d[c].median())
    scale=d[NEURAL_NUMERIC_FEATURES].copy()
    return d, scale

def make_windows(df, eligible_ids, normalizer):
    Xs=[]; ys=[]; stations=[]; seqids=[]
    for sid,g in df[df.sequence_id.isin(eligible_ids)].groupby("sequence_id",sort=False):
        g=g.sort_values("timestamp")
        arr=g[NEURAL_NUMERIC_FEATURES].to_numpy(float)
        y=g["future_delay_target"].to_numpy(float)
        st=g["current_station"].astype(str).to_numpy()
        # Need t+WINDOW-1 as final input and t+WINDOW-1+HORIZON as target -> 8 points.
        for end in range(WINDOW-1, len(g)-HORIZON_STEPS):
            target=y[end]
            if not np.isfinite(target): continue
            Xs.append(normalizer(arr[end-WINDOW+1:end+1]))
            ys.append(target); stations.append(st[end]); seqids.append(sid)
    return np.stack(Xs), np.array(ys,float), np.array(stations), np.array(seqids)

class Scaler:
    def __init__(self, mean, std): self.mean=mean; self.std=np.where(std<1e-6,1,std)
    def __call__(self,x): return (x-self.mean)/self.std
    def save(self,path): np.savez(path,mean=self.mean,std=self.std)
    @staticmethod
    def load(path):
        a=np.load(path); return Scaler(a['mean'],a['std'])

def train_gru_and_hybrid(df_train, df_val, df_test, graph_nodes, graph_edges):
    # Fit scaler on training sequences only.
    trvals=df_train[NEURAL_NUMERIC_FEATURES].apply(pd.to_numeric,errors="coerce")
    mean=trvals.median().to_numpy(float); std=trvals.std().to_numpy(float)
    scaler=Scaler(mean,std); scaler.save(MODEL_DIR/"neural_scaler.npz")

    dtrain=make_tab(df_train); dval=make_tab(df_val); dtest=make_tab(df_test)
    # Only complete target rows are used.
    train_ids=dtrain.sequence_id.unique(); val_ids=dval.sequence_id.unique(); test_ids=dtest.sequence_id.unique()
    Xtr,ytr,strt,_,=make_windows(dtrain,train_ids,scaler)
    Xv,yv,sv,_=make_windows(dval,val_ids,scaler)
    Xt,yt,st,_=make_windows(dtest,test_ids,scaler)

    # Node graph / static features built from training only.
    stations=sorted(set(graph_nodes.station.astype(str)))
    idx={s:i for i,s in enumerate(stations)}
    gtrain=dtrain.copy()
    static=gtrain.groupby("current_station")[NEURAL_NUMERIC_FEATURES].mean().reindex(stations).fillna(gtrain[NEURAL_NUMERIC_FEATURES].mean())
    node_x=static.to_numpy(float); nmean=node_x.mean(0); nstd=node_x.std(0); nstd[nstd<1e-6]=1; node_x=(node_x-nmean)/nstd
    n=len(stations); A=np.eye(n,dtype=np.float32)
    for r in graph_edges.itertuples(index=False):
        a=str(r.current_station); b=str(r.next_station)
        if a in idx and b in idx:
            A[idx[a],idx[b]]=1; A[idx[b],idx[a]]=1
    deg=A.sum(1,keepdims=True); A=A/np.sqrt(deg@deg.T)
    node_x=torch.tensor(node_x,dtype=torch.float32); adj=torch.tensor(A,dtype=torch.float32)
    node_idx_tr=np.array([idx.get(s,0) for s in strt]); node_idx_v=np.array([idx.get(s,0) for s in sv]); node_idx_t=np.array([idx.get(s,0) for s in st])

    device="cuda" if torch.cuda.is_available() else "cpu"; node_x=node_x.to(device); adj=adj.to(device)
    def fit_model(hybrid=False):
        if hybrid: model=HybridGNNGRU(len(NEURAL_NUMERIC_FEATURES),len(NEURAL_NUMERIC_FEATURES), gru_hidden=32, gnn_hidden=16, dropout=0.15).to(device)
        else: model=GRURegressor(len(NEURAL_NUMERIC_FEATURES), hidden=32, layers=1, dropout=0.15).to(device)
        opt=torch.optim.AdamW(model.parameters(),lr=2e-3,weight_decay=1e-4)
        lossfn=torch.nn.HuberLoss(delta=2.0)
        dl=DataLoader(TensorDataset(torch.tensor(Xtr,dtype=torch.float32),torch.tensor(ytr,dtype=torch.float32),torch.tensor(node_idx_tr)),batch_size=512,shuffle=True)
        best=np.inf; best_state=None; patience=0
        for epoch in range(1,26):
            model.train()
            for xb,yb,ib in dl:
                xb=xb.to(device); yb=yb.to(device); ib=ib.to(device)
                opt.zero_grad()
                pred=model(xb,node_x,adj,ib) if hybrid else model(xb)
                loss=lossfn(pred,yb); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(),1.0); opt.step()
            model.eval()
            with torch.no_grad():
                xv=torch.tensor(Xv,dtype=torch.float32).to(device); iv=torch.tensor(node_idx_v).to(device)
                pv=model(xv,node_x,adj,iv) if hybrid else model(xv)
                val=mean_absolute_error(yv,pv.cpu().numpy())
            if val<best-1e-4:
                best=val; patience=0; best_state={k:v.detach().cpu().clone() for k,v in model.state_dict().items()}
            else: patience+=1
            if patience>=4: break
        model.load_state_dict(best_state); return model,epoch
    gru,ge=fit_model(False); hybrid,he=fit_model(True)

    out={"gru":{},"hybrid":{}}
    for name,model,ni in [("gru",gru,node_idx_t),("hybrid",hybrid,node_idx_t)]:
        model.eval()
        with torch.no_grad():
            xx=torch.tensor(Xt,dtype=torch.float32).to(device); ii=torch.tensor(ni).to(device)
            pp=model(xx,node_x,adj,ii) if name=="hybrid" else model(xx)
        p=pp.cpu().numpy(); out[name]={"mae":float(mean_absolute_error(yt,p)),"rmse":rmse(yt,p),"r2":float(r2_score(yt,p))}
    torch.save(gru.state_dict(),MODEL_DIR/"gru_delay.pt")
    torch.save(hybrid.state_dict(),MODEL_DIR/"hybrid_gnn_gru_delay.pt")
    np.savez(MODEL_DIR/"graph_features.npz",node_x=node_x.cpu().numpy(),adj=adj.cpu().numpy(),stations=np.array(stations),node_mean=nmean,node_std=nstd)
    meta={"stations":stations,"numeric_features":NEURAL_NUMERIC_FEATURES,"window":WINDOW,"horizon_steps":HORIZON_STEPS,"gru_epochs":ge,"hybrid_epochs":he}
    (MODEL_DIR/"neural_meta.json").write_text(json.dumps(meta,indent=2))
    return out

def make_tab(df):
    d=df.copy(); d=d.sort_values(["sequence_id","timestamp"])
    d["future_delay_target"]=d.groupby("sequence_id")["current_delay_mins"].shift(-HORIZON_STEPS)-d["current_delay_mins"]
    return d

def train_prop(df_train, df_test):
    a=df_train.dropna(subset=["propagation_occurred"]).copy(); b=df_test.dropna(subset=["propagation_occurred"]).copy()
    Xtr,prep,features=build_xgb_features(a); Xte=add_time_features(b)[features].copy(); ytr=a.propagation_occurred.astype(int); yte=b.propagation_occurred.astype(int)
    model=XGBClassifier(n_estimators=350,max_depth=4,learning_rate=.04,subsample=.85,colsample_bytree=.85,
                        min_child_weight=5,reg_lambda=2,eval_metric="logloss",random_state=RANDOM_STATE,n_jobs=-1)
    pipe=Pipeline([("prep",prep),("model",model)]); pipe.fit(Xtr,ytr); p=pipe.predict(Xte); prob=pipe.predict_proba(Xte)[:,1]
    metrics={"accuracy":float(accuracy_score(yte,p)),"f1":float(f1_score(yte,p)),"positive_rate":float(yte.mean())}
    joblib.dump(pipe,MODEL_DIR/"propagation_xgb.joblib")
    return metrics

def main():
    df=pd.read_csv(SEQ_PATH)
    df=df.drop_duplicates().copy()
    df=make_tab(df)
    tr,va,te=split_groups(df)
    # Save split IDs for reproducibility.
    split_map=pd.concat([pd.DataFrame({"sequence_id":tr.sequence_id.unique(),"split":"train"}),pd.DataFrame({"sequence_id":va.sequence_id.unique(),"split":"val"}),pd.DataFrame({"sequence_id":te.sequence_id.unique(),"split":"test"})])
    split_map.to_csv(MODEL_DIR/"sequence_splits.csv",index=False)
    xgb_m,_=train_xgb(tr,te)
    prop_m=train_prop(tr,te)
    nodes=pd.read_csv(GRAPH_NODES_PATH); edges=pd.read_csv(GRAPH_EDGES_PATH)
    nn=train_gru_and_hybrid(tr,va,te,nodes,edges)
    metrics={"xgboost_delay":xgb_m,"propagation_xgb":prop_m,**nn}
    (MODEL_DIR/"metrics.json").write_text(json.dumps(metrics,indent=2))
    print(json.dumps(metrics,indent=2))

if __name__=="__main__": main()

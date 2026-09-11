import time, json
import pandas as pd

def replay_train(train_id, csv_path="data/dynamicrail_sequential_simulation.csv", seconds_per_step=0.5):
    df=pd.read_csv(csv_path)
    g=df[df.train_id.astype(str)==str(train_id)].sort_values("timestamp")
    if g.empty: raise ValueError("Train ID not found")
    for _,row in g.iterrows():
        yield row.to_dict()
        time.sleep(seconds_per_step)

if __name__=="__main__":
    for item in replay_train(10394):
        print(json.dumps(item,default=str))

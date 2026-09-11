import torch
from torch import nn

class GRURegressor(nn.Module):
    def __init__(self, input_dim, hidden=64, layers=2, dropout=0.2):
        super().__init__()
        self.gru=nn.GRU(input_dim, hidden, num_layers=layers, batch_first=True,
                        dropout=dropout if layers>1 else 0.0)
        self.head=nn.Sequential(nn.LayerNorm(hidden), nn.Dropout(dropout),
                                nn.Linear(hidden, 32), nn.ReLU(), nn.Linear(32,1))
    def forward(self,x):
        out,_=self.gru(x)
        return self.head(out[:,-1,:]).squeeze(-1)

class GCNLayer(nn.Module):
    def __init__(self, in_dim, out_dim):
        super().__init__()
        self.lin=nn.Linear(in_dim,out_dim)
    def forward(self,x,adj):
        return torch.relu(self.lin(adj @ x))

class GNNEncoder(nn.Module):
    def __init__(self,in_dim, hidden=32, out_dim=32, dropout=0.15):
        super().__init__()
        self.g1=GCNLayer(in_dim,hidden)
        self.g2=GCNLayer(hidden,out_dim)
        self.drop=nn.Dropout(dropout)
    def forward(self,x,adj):
        h=self.drop(self.g1(x,adj))
        return self.g2(h,adj)

class HybridGNNGRU(nn.Module):
    def __init__(self, seq_dim, node_dim, gru_hidden=64, gnn_hidden=32, dropout=0.2):
        super().__init__()
        self.gru=nn.GRU(seq_dim,gru_hidden,num_layers=2,batch_first=True,dropout=dropout)
        self.gnn=GNNEncoder(node_dim,hidden=gnn_hidden,out_dim=gnn_hidden,dropout=dropout)
        self.head=nn.Sequential(
            nn.LayerNorm(gru_hidden+gnn_hidden), nn.Dropout(dropout),
            nn.Linear(gru_hidden+gnn_hidden,64), nn.ReLU(), nn.Dropout(dropout), nn.Linear(64,1)
        )
    def forward(self,seq, node_x, adj, node_idx):
        h,_=self.gru(seq)
        ht=h[:,-1,:]
        z=self.gnn(node_x,adj)[node_idx]
        return self.head(torch.cat([ht,z],dim=1)).squeeze(-1)

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

from dataloader import OBS_KEYS, SegmentDataset, collate_sequences, compute_stats, make_splits


class BCRNN(nn.Module):
    # 저차원 observation sequence를 받아 각 step의 action을 예측하는 간단한 LSTM 기반 BC-RNN이다.
    def __init__(self, obs_dim, action_dim, hidden_dim=128, num_layers=2, dropout=0.1):
        super().__init__()
        self.rnn = nn.LSTM(
            input_size=obs_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            dropout=dropout if num_layers > 1 else 0.0,
            batch_first=True,
            bidirectional=True,
        )
        self.head = nn.Sequential(nn.LayerNorm(hidden_dim * 2), nn.Linear(hidden_dim * 2, action_dim))

    def forward(self, obs):
        features, _ = self.rnn(obs)
        return self.head(features)


def masked_mse(pred, target, mask):
    # padding 된 step은 loss에서 제외하고 실제 trajectory 구간만 평균낸다.
    loss = ((pred - target) ** 2).mean(dim=-1)
    return (loss * mask).sum() / mask.sum().clamp_min(1.0)


def run_epoch(model, loader, optimizer, device):
    # optimizer가 있으면 train, 없으면 validation으로 동작한다.
    is_train = optimizer is not None
    model.train(is_train)
    total_loss, total_steps = 0.0, 0
    for obs, actions, mask, _ in loader:
        obs, actions, mask = obs.to(device), actions.to(device), mask.to(device)
        with torch.set_grad_enabled(is_train):
            pred = model(obs)
            loss = masked_mse(pred, actions, mask)
            if is_train:
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 5.0)
                optimizer.step()
        steps = int(mask.sum().item())
        total_loss += float(loss.item()) * steps
        total_steps += steps
    return total_loss / max(total_steps, 1)


def train_task(args):
    # 한 segment task 폴더를 읽어 BC-RNN을 학습하고 체크포인트/로그를 저장한다.
    data_dir = Path(args.data_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    train_files, val_files = make_splits(data_dir, args.val_ratio, args.seed)
    stats = compute_stats(train_files, OBS_KEYS)
    train_ds = SegmentDataset(train_files, OBS_KEYS, stats)
    val_ds = SegmentDataset(val_files, OBS_KEYS, stats)
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, collate_fn=collate_sequences)
    val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False, collate_fn=collate_sequences)

    sample_obs, sample_act = train_ds[0]
    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    model = BCRNN(sample_obs.shape[-1], sample_act.shape[-1], args.hidden_dim, args.num_layers, 0.0).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr * 2.25, weight_decay=args.weight_decay * 0.1)

    config = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()} | {
        "obs_keys": OBS_KEYS,
        "obs_dim": int(sample_obs.shape[-1]),
        "action_dim": int(sample_act.shape[-1]),
        "train_files": len(train_files),
        "val_files": len(val_files),
        "device": str(device),
    }
    (out_dir / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    np.savez(out_dir / "normalization.npz", **stats)

    best_val = float("inf")
    with (out_dir / "train_log.csv").open("w", newline="", encoding="utf-8") as log_file:
        writer = csv.DictWriter(log_file, fieldnames=["epoch", "train_loss", "val_loss"])
        writer.writeheader()
        for epoch in range(1, args.epochs + 1):
            train_loss = run_epoch(model, train_loader, optimizer, device)
            val_loss = run_epoch(model, val_loader, None, device)
            writer.writerow({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})
            log_file.flush()
            print(f"epoch={epoch:03d} train_loss={train_loss:.6f} val_loss={val_loss:.6f}")

            state = {
                "model": model.state_dict(),
                "config": config,
                "stats": {key: value.tolist() for key, value in stats.items()},
                "epoch": epoch,
                "val_loss": val_loss,
            }
            torch.save(state, out_dir / "last.pt")
            if val_loss < best_val:
                best_val = val_loss
                torch.save(state, out_dir / "best.pt")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--hidden-dim", type=int, default=128)
    parser.add_argument("--num-layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--cpu", action="store_true")
    args = parser.parse_args()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    train_task(args)


if __name__ == "__main__":
    main()

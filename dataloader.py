from pathlib import Path

import h5py
import numpy as np
import torch
from torch.utils.data import Dataset
from torch.nn.utils.rnn import pad_sequence


OBS_KEYS = (
    "robot0_eef_pos",
    "robot0_eef_quat",
    "robot0_gripper_qpos",
    "Bread_pos",
    "Bread_quat",
    "Bread_to_robot0_eef_pos",
    "dynamic_obs_pos",
    "dynamic_obs_vel",
)


class SegmentDataset(Dataset):
    # 세그먼트 HDF5 파일들을 BC-RNN 학습용 (obs sequence, action sequence)로 읽는 Dataset이다.
    def __init__(self, files, obs_keys=OBS_KEYS, stats=None):
        self.files = [Path(file) for file in files]
        self.obs_keys = tuple(obs_keys)
        self.stats = stats

    def __len__(self):
        return len(self.files)

    def __getitem__(self, idx):
        obs, actions = load_sequence(self.files[idx], self.obs_keys)
        if self.stats is not None:
            obs = (obs - self.stats["obs_mean"]) / self.stats["obs_std"]
            actions = (actions - self.stats["act_mean"]) / self.stats["act_std"]
        return torch.from_numpy(obs).float(), torch.from_numpy(actions).float()


def load_sequence(path, obs_keys=OBS_KEYS):
    # 선택한 observation key들을 concat하고, 모든 배열이 공유하는 최소 길이에 맞춰 정렬한다.
    with h5py.File(path, "r") as h5:
        obs_arrays = [h5[f"obs/{key}"][:] for key in obs_keys]
        actions = h5["actions"][:]

    min_len = min([len(actions), *[len(arr) for arr in obs_arrays]])
    obs = np.concatenate([arr[:min_len].reshape(min_len, -1) for arr in obs_arrays], axis=1)
    actions = actions[:min_len].reshape(min_len, -1)
    return obs.astype(np.float32), actions.astype(np.float32)


def make_splits(data_dir, val_ratio=0.15, seed=0):
    # 원본 파일 단위로 train/val을 나눠 같은 segment가 양쪽에 섞이는 것을 피한다.
    files = sorted(Path(data_dir).glob("*.hdf5"))
    if len(files) < 2:
        raise ValueError(f"Need at least 2 segment files in {data_dir}")
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(files))
    val_count = max(1, int(round(len(files) * val_ratio)))
    val_ids = set(order[:val_count])
    train_files = [file for i, file in enumerate(files) if i not in val_ids]
    val_files = [file for i, file in enumerate(files) if i in val_ids]
    return train_files, val_files


def compute_stats(files, obs_keys=OBS_KEYS):
    # train split에서만 평균/표준편차를 계산해 validation leakage를 막는다.
    obs_parts, act_parts = [], []
    for file in files:
        obs, actions = load_sequence(file, obs_keys)
        obs_parts.append(obs)
        act_parts.append(actions)
    obs_all = np.concatenate(obs_parts, axis=0)
    act_all = np.concatenate(act_parts, axis=0)
    return {
        "obs_mean": obs_all.mean(axis=0).astype(np.float32),
        "obs_std": np.maximum(obs_all.std(axis=0), 1e-6).astype(np.float32),
        "act_mean": act_all.mean(axis=0).astype(np.float32),
        "act_std": np.maximum(act_all.std(axis=0), 1e-6).astype(np.float32),
    }


def collate_sequences(batch):
    # 길이가 다른 trajectory를 padding하고, loss 계산용 mask를 함께 만든다.
    obs, actions = zip(*batch)
    lengths = torch.tensor([len(x) for x in obs], dtype=torch.long)
    obs_pad = pad_sequence(obs, batch_first=True)
    act_pad = pad_sequence(actions, batch_first=True)
    mask = torch.arange(obs_pad.shape[1]).unsqueeze(0) < lengths.unsqueeze(1)
    return obs_pad, act_pad, mask.float(), lengths

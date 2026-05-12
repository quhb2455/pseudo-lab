import argparse
import json
from pathlib import Path

import h5py
import numpy as np


TASKS = ("approach", "pick_lift", "place_release")


def _first_index(mask, default):
    # True가 처음 나오는 index를 반환하고, 없으면 fallback을 사용한다.
    found = np.flatnonzero(mask)
    return int(found[0]) if len(found) else int(default)


def find_segment_bounds(h5, object_key="Bread", lift_height=0.03):
    # 한 episode에서 gripper 명령, 물체 높이, 성공 신호를 조합해 3개 하위 동작 경계를 추정한다.
    actions_len = len(h5["actions"])
    obj_pos = h5[f"obs/{object_key}_pos"][:actions_len]
    eef_pos = h5["obs/robot0_eef_pos"][:actions_len]
    gripper = h5["raw_actions/right_gripper"][:actions_len].reshape(-1)
    partial_success = h5["partial_success"][:actions_len]

    success_idx = _first_index(partial_success.astype(bool), actions_len - 1)
    close_changes = np.flatnonzero((gripper[1:] == 1) & (gripper[:-1] != 1)) + 1

    # 보통 right_gripper==1 전환이 집는 시점이다. 없으면 eef-object 최단거리 시점을 사용한다.
    if len(close_changes):
        grasp_idx = int(close_changes[0])
    else:
        grasp_idx = int(np.argmin(np.linalg.norm(eef_pos - obj_pos, axis=1)))

    lift_mask = obj_pos[:, 2] > obj_pos[0, 2] + lift_height
    lift_idx = _first_index(lift_mask & (np.arange(actions_len) >= grasp_idx), min(success_idx, actions_len - 1))

    # 경계가 역전되면 최소한의 순서를 보장한다. 너무 짧은 구간은 저장 단계에서 제외한다.
    grasp_idx = max(1, min(grasp_idx, actions_len - 2))
    lift_idx = max(grasp_idx + 1, min(lift_idx, actions_len - 1))
    success_idx = max(lift_idx + 1, min(success_idx, actions_len - 1))

    return {
        "approach": (0, grasp_idx + 1),
        "pick_lift": (grasp_idx, lift_idx + 1),
        "place_release": (lift_idx, success_idx + 1),
    }


def write_segment(src_path, dst_path, start, end, task):
    # 원본 HDF5 구조를 유지하되 각 dataset만 [start:end] 범위로 잘라 새 파일에 저장한다.
    with h5py.File(src_path, "r") as src, h5py.File(dst_path, "w") as dst:
        meta = dst.create_group("metadata")
        for key, value in src["metadata"].attrs.items():
            meta.attrs[key] = value
        meta.attrs["source_file"] = src_path.name
        meta.attrs["segment_task"] = task
        meta.attrs["source_start"] = int(start)
        meta.attrs["source_end"] = int(end)
        meta.attrs["num_steps"] = int(end - start)

        def copy_item(name, obj):
            if name == "metadata":
                return
            if isinstance(obj, h5py.Group):
                dst.require_group(name)
                return
            stop = min(end, obj.shape[0])
            begin = min(start, stop)
            dst.create_dataset(name, data=obj[begin:stop])

        src.visititems(copy_item)


def segment_dataset(data_dir, object_key="Bread", min_steps=8, lift_height=0.03):
    # bread 폴더의 원본 demo만 읽고, task 하위 폴더에는 세그먼트 HDF5를 저장한다.
    data_dir = Path(data_dir)
    for task in TASKS:
        (data_dir / task).mkdir(parents=True, exist_ok=True)

    summary = {task: 0 for task in TASKS}
    for src_path in sorted(data_dir.glob("*.hdf5")):
        with h5py.File(src_path, "r") as h5:
            bounds = find_segment_bounds(h5, object_key=object_key, lift_height=lift_height)

        for task, (start, end) in bounds.items():
            if end - start < min_steps:
                continue
            dst_path = data_dir / task / f"{src_path.stem}_{task}.hdf5"
            write_segment(src_path, dst_path, start, end, task)
            summary[task] += 1

    summary_path = data_dir / "segment_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


def main():
    # CLI entry point: conda run -n RL python utils.py segment --data-dir data/teleop_demos/bread
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    segment = subparsers.add_parser("segment")
    segment.add_argument("--data-dir", type=Path, default=Path("data/teleop_demos/bread"))
    segment.add_argument("--object-key", type=str, default="Bread")
    segment.add_argument("--min-steps", type=int, default=8)
    segment.add_argument("--lift-height", type=float, default=0.03)
    args = parser.parse_args()

    if args.command == "segment":
        segment_dataset(args.data_dir, args.object_key, args.min_steps, args.lift_height)


if __name__ == "__main__":
    main()

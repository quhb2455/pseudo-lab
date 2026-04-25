import argparse
import json
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path

import h5py
import numpy as np

from custom_env import DynamicObstacleEnv
from pynput.keyboard import Key
from robosuite import load_composite_controller_config
from robosuite.controllers.composite.composite_controller import WholeBody
from robosuite.devices import Keyboard
from robosuite.wrappers import VisualizationWrapper


SAVE_DIR = Path(__file__).parent / "data" / "teleop_demos"
ROBOT_NAME = "Panda"


class SimpleKeyboard(Keyboard):
    @staticmethod
    def _display_controls():
        print("")
        print("Keys                          Command")
        print("Ctrl+q / q                    reset simulation")
        print("space                         toggle gripper")
        print("left / right                  move in x")
        print("up / down                     move in y")
        print("z / x                         move in z")
        print("o / p, y / h, e / r           rotate gripper")
        print("")

    def on_press(self, key):
        try:
            # 위치 이동 키는 x, y, z 세 축만 간단히 직접 매핑한다.
            if key == Key.up:
                self.pos[0] += self._pos_step * self.pos_sensitivity
            elif key == Key.down:
                self.pos[0] -= self._pos_step * self.pos_sensitivity
            elif key == Key.left:
                self.pos[1] -= self._pos_step * self.pos_sensitivity
            elif key == Key.right:
                self.pos[1] += self._pos_step * self.pos_sensitivity
            elif key.char == "z":
                self.pos[2] += self._pos_step * self.pos_sensitivity
            elif key.char == "x":
                self.pos[2] -= self._pos_step * self.pos_sensitivity
            elif key.char in {"e", "r", "y", "h", "o", "p"}:
                super().on_press(key)
        except AttributeError:
            pass


def make_env(single_object_mode=0, object_type=None, wide_obstacle=False, obstacle_speed=None):
    # Panda 기본 controller 설정을 불러와 teleop action 변환에 사용한다.
    controller_config = load_composite_controller_config(
        controller=None,
        robot=ROBOT_NAME,
    )

    # free camera와 gripper 가이드를 함께 쓰는 현재 실행 환경이다.
    # single_object_mode=2: 매 에피소드 동일 물체 고정 (object_type 지정 시 자동 적용)
    env_kwargs = dict(
        robots=ROBOT_NAME,
        controller_configs=controller_config,
        has_renderer=True,
        has_offscreen_renderer=False,
        use_camera_obs=False,
        render_camera=None,
        control_freq=20,
        ignore_done=True,
        hard_reset=False,
        single_object_mode=single_object_mode,
        object_type=object_type,
    )
    # --wide-obstacle: 장애물 이동 범위를 pick 영역까지 확장
    # bin 중심 기준으로 양쪽에 여유를 추가해 실제 pick/place 영역을 커버한다
    if wide_obstacle:
        bin1_y, bin2_y = -0.35, 0.38
        env_kwargs["obstacle_y_center"] = (bin1_y + bin2_y) / 2
        env_kwargs["obstacle_y_amplitude"] = (bin2_y - bin1_y) / 2
    # --obstacle-speed: 기본값(1.1)보다 크면 빠르고, 작으면 느리다
    if obstacle_speed is not None:
        env_kwargs["obstacle_speed"] = obstacle_speed
    env = DynamicObstacleEnv(**env_kwargs)
    env = VisualizationWrapper(env, indicator_configs=None)
    return env, controller_config


def make_keyboard(env):
    # 키보드는 별도 listener thread에서 입력을 계속 읽는다.
    device = SimpleKeyboard(
        env=env,
        pos_sensitivity=1.0,
        rot_sensitivity=1.0,
    )
    if env.viewer is not None:
        env.viewer.add_keypress_callback(device.on_press)
    return device


def build_env_action(env, device, prev_gripper_actions):
    # Keyboard 상태를 robosuite action dict로 바꾼 뒤,
    # 최종 env.step()에 넣을 1차원 action vector를 만든다.
    active_robot = env.robots[device.active_robot]
    input_ac_dict = device.input2action()
    if input_ac_dict is None:
        return None, None

    action_dict = deepcopy(input_ac_dict)
    for arm in active_robot.arms:
        if isinstance(active_robot.composite_controller, WholeBody):
            controller_input_type = active_robot.composite_controller.joint_action_policy.input_type
        else:
            controller_input_type = active_robot.part_controllers[arm].input_type

        if controller_input_type == "delta":
            action_dict[arm] = input_ac_dict[f"{arm}_delta"]
        elif controller_input_type == "absolute":
            action_dict[arm] = input_ac_dict[f"{arm}_abs"]
        else:
            raise ValueError(f"Unsupported controller input type: {controller_input_type}")

    env_action = [robot.create_action_vector(prev_gripper_actions[i]) for i, robot in enumerate(env.robots)]
    env_action[device.active_robot] = active_robot.create_action_vector(action_dict)
    env_action = np.concatenate(env_action)

    for gripper_key in prev_gripper_actions[device.active_robot]:
        prev_gripper_actions[device.active_robot][gripper_key] = action_dict[gripper_key]

    return env_action, input_ac_dict


def make_episode_buffer():
    # step마다 필요한 저차원 데이터만 모으는 버퍼다.
    return {
        "obs": {},
        "actions": [],
        "raw_actions": {},
        "rewards": [],
        "dones": [],
        "task_success": [],
        "partial_success": [],
        "gripper_ball_contact": [],
        "step_time": [],
    }


def append_array_dict(store, values):
    # observation / raw action처럼 dict 형태인 값은 key별 리스트로 누적한다.
    for key, value in values.items():
        array_value = np.asarray(value)
        store.setdefault(key, []).append(array_value.copy())


def record_step(buffer, obs, env_action, raw_action_dict, reward, done, info, step_elapsed):
    # imitation learning에 필요한 저차원 observation과 action, success 신호를 step 단위로 기록한다.
    append_array_dict(buffer["obs"], obs)
    append_array_dict(buffer["raw_actions"], raw_action_dict)
    buffer["actions"].append(np.asarray(env_action).copy())
    buffer["rewards"].append(float(reward))
    buffer["dones"].append(bool(done))
    buffer["task_success"].append(bool(info["task_success"]))
    buffer["partial_success"].append(bool(info["partial_success"]))
    buffer["gripper_ball_contact"].append(bool(info["gripper_ball_contact"]))
    buffer["step_time"].append(float(step_elapsed))


def stack_episode_buffer(buffer):
    # 저장 직전에 list를 numpy 배열로 바꿔 HDF5에 넣기 쉽게 만든다.
    stacked = {
        "obs": {key: np.asarray(values) for key, values in buffer["obs"].items()},
        "raw_actions": {key: np.asarray(values) for key, values in buffer["raw_actions"].items()},
        "actions": np.asarray(buffer["actions"]),
        "rewards": np.asarray(buffer["rewards"], dtype=np.float32),
        "dones": np.asarray(buffer["dones"], dtype=np.bool_),
        "task_success": np.asarray(buffer["task_success"], dtype=np.bool_),
        "partial_success": np.asarray(buffer["partial_success"], dtype=np.bool_),
        "gripper_ball_contact": np.asarray(buffer["gripper_ball_contact"], dtype=np.bool_),
        "step_time": np.asarray(buffer["step_time"], dtype=np.float32),
    }
    return stacked


def save_success_episode(buffer, env, controller_config, episode_idx):
    # 객체 1개라도 성공한 episode를 HDF5로 저장한다.
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    stacked = stack_episode_buffer(buffer)
    success_step = int(np.argmax(stacked["partial_success"]))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = SAVE_DIR / f"demo_{episode_idx:04d}_{timestamp}.hdf5"

    with h5py.File(save_path, "w") as f:
        meta = f.create_group("metadata")
        meta.attrs["timestamp"] = timestamp
        meta.attrs["robot"] = ROBOT_NAME
        meta.attrs["control_freq"] = env.control_freq
        meta.attrs["num_steps"] = len(stacked["actions"])
        meta.attrs["success_step"] = success_step
        meta.attrs["partial_success"] = True
        meta.attrs["task_success"] = bool(stacked["task_success"][-1])
        meta.attrs["env_name"] = env.unwrapped.__class__.__name__
        meta.attrs["controller_config"] = json.dumps(controller_config)

        obs_group = f.create_group("obs")
        for key, value in stacked["obs"].items():
            obs_group.create_dataset(key, data=value)

        raw_action_group = f.create_group("raw_actions")
        for key, value in stacked["raw_actions"].items():
            raw_action_group.create_dataset(key, data=value)

        f.create_dataset("actions", data=stacked["actions"])
        f.create_dataset("rewards", data=stacked["rewards"])
        f.create_dataset("dones", data=stacked["dones"])
        f.create_dataset("task_success", data=stacked["task_success"])
        f.create_dataset("partial_success", data=stacked["partial_success"])
        f.create_dataset("gripper_ball_contact", data=stacked["gripper_ball_contact"])
        f.create_dataset("step_time", data=stacked["step_time"])

    print(f"[saved] {save_path}")

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--object-type", type=str, default=None, choices=["milk", "bread", "cereal", "can"], help="지정하면 해당 물체 1개만 사용")
    parser.add_argument("--wide-obstacle", action="store_true", help="장애물이 픽 영역까지 넓게 이동")
    parser.add_argument("--obstacle-speed", type=float, default=None, help="장애물 이동 속도 배율 (기본값: 1.1)")
    return parser.parse_args()


def main():
    args = parse_args()
    single_object_mode = 2 if args.object_type else 0
    env, controller_config = make_env(
        single_object_mode=single_object_mode,
        object_type=args.object_type,
        wide_obstacle=args.wide_obstacle,
        obstacle_speed=args.obstacle_speed,
    )
    device = make_keyboard(env)
    np.set_printoptions(formatter={"float": lambda x: f"{x:0.3f}"})

    saved_episode_count = 0

    try:
        while True:
            # reset할 때마다 새 episode 버퍼를 만든다.
            obs = env.reset()
            env.render()
            device.start_control()
            episode_buffer = make_episode_buffer()

            prev_gripper_actions = [
                {
                    f"{robot_arm}_gripper": np.repeat([0], robot.gripper[robot_arm].dof)
                    for robot_arm in robot.arms
                    if robot.gripper[robot_arm].dof > 0
                }
                for robot in env.robots
            ]

            while True:
                start = time.time()
                env_action, raw_action_dict = build_env_action(env, device, prev_gripper_actions)

                # 사용자가 reset하면 현재 episode는 저장하지 않고 버린다.
                if env_action is None:
                    print("[discarded] reset before success")
                    break

                next_obs, reward, done, info = env.step(env_action)
                step_elapsed = time.time() - start
                record_step(
                    episode_buffer,
                    obs,
                    env_action,
                    raw_action_dict,
                    reward,
                    done,
                    info,
                    step_elapsed,
                )
                env.render()

                # 객체 1개라도 올바른 칸에 들어가면 partial_success로 저장한다.
                if info["partial_success"]:
                    saved_episode_count += 1
                    save_success_episode(episode_buffer, env, controller_config, saved_episode_count)
                    break

                obs = next_obs

                # 너무 빠르게 도는 것을 막아 사람이 조작하기 쉬운 속도로 유지한다.
                sleep_time = max(0.0, 1.0 / env.control_freq - step_elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
    finally:
        env.close()


if __name__ == "__main__":
    main()

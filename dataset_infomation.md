# Dataset Information

이 문서는 `run.py`가 성공 episode를 저장할 때 만들어지는 HDF5 데이터의 구조와 각 변수 의미를 정리한 메모다.

## 저장 조건

- 저장 트리거는 `task_success`가 아니라 `info["partial_success"] == True` 이다.
- 즉, 현재 설정에서는 물체가 1개 이상 목표 bin에 들어간 순간 현재 episode를 저장하고 종료한다.
- `task_success`는 함께 저장되지만, 저장 조건 자체는 아니다.

관련 코드:

- [run.py](/home/sub/workspace/RL_project/pseudo-lab/run.py:247)
- [custom_env.py](/home/sub/workspace/RL_project/pseudo-lab/custom_env.py:108)

## 저장 흐름

1. episode 시작 시 `make_episode_buffer()`로 빈 버퍼를 만든다.
2. 매 step마다 `env.step(env_action)`을 호출한다.
3. `record_step(...)`가 현재 step 데이터를 버퍼에 누적한다.
4. `info["partial_success"]`가 `True`가 되면 `save_success_episode(...)`를 호출한다.
5. 버퍼 안 리스트들을 numpy 배열로 바꾼 뒤 HDF5 파일로 저장한다.

## 저장 경로와 파일명

- 저장 폴더: `/home/sub/workspace/RL_project/pseudo-lab/data/teleop_demos`
- 파일명 형식: `demo_0001_YYYYMMDD_HHMMSS.hdf5`

## HDF5 구조

```text
demo_XXXX_YYYYMMDD_HHMMSS.hdf5
├── metadata (group, attrs)
├── obs/
│   ├── <observation_key_1>
│   ├── <observation_key_2>
│   └── ...
├── raw_actions/
│   ├── <raw_action_key_1>
│   ├── <raw_action_key_2>
│   └── ...
├── actions
├── rewards
├── dones
├── task_success
├── partial_success
├── gripper_ball_contact
└── step_time
```

## metadata attribute 의미

- `timestamp`: 저장 시각 문자열
- `robot`: 로봇 이름. 현재는 `Panda`
- `control_freq`: 제어 주파수
- `num_steps`: 저장된 총 step 수
- `success_step`: `partial_success`가 처음 `True`가 된 step index
- `partial_success`: 이 파일이 partial success 기준으로 저장되었음을 나타내는 값
- `task_success`: 마지막 저장 step에서의 전체 task 성공 여부
- `env_name`: 환경 클래스 이름
- `controller_config`: controller 설정을 JSON 문자열로 직렬화한 값

## Episode buffer 변수 의미

`make_episode_buffer()`가 만드는 버퍼는 아래 구조를 가진다.

- `buffer["obs"]`: observation dict를 key별로 모아둔 저장소
- `buffer["actions"]`: 실제 `env.step()`에 넣은 최종 1차원 action vector 목록
- `buffer["raw_actions"]`: 키보드 입력에서 직접 나온 원본 action dict
- `buffer["rewards"]`: step별 reward
- `buffer["dones"]`: step별 done
- `buffer["task_success"]`: step별 전체 task 성공 여부
- `buffer["partial_success"]`: step별 부분 성공 여부
- `buffer["gripper_ball_contact"]`: step별 gripper와 공 접촉 여부
- `buffer["step_time"]`: step 처리 시간

## 저장 dataset 의미

### `obs`

- 각 step의 observation을 key별 dataset으로 저장한다.
- 저장되는 것은 `env.step()` 실행 전의 `obs_t` 이다.
- 즉, 한 step은 대략 `(obs_t, action_t, reward_t, info_t)` 형태로 기록된다.
- robosuite 기본 observation key들과 커스텀 observation key들이 함께 들어간다.

주요 커스텀 observation key:

- `dynamic_obs_pos`: 움직이는 공의 현재 world 좌표
- `dynamic_obs_vel`: 공의 속도 추정값
- `gripper_ball_contact`: gripper와 공의 접촉 여부를 float 배열로 표현한 값
- `objects_in_bins`: 각 물체가 자기 목표 bin에 들어갔는지 나타내는 배열
- `target_bin_placements`: 각 물체의 목표 위치 좌표
- `partial_success`: 물체 1개 이상 성공했는지 나타내는 float 배열

### `raw_actions`

- 키보드 입력 장치가 만든 원본 action dict를 key별 dataset으로 저장한다.
- 로봇 제어기용 최종 vector로 변환되기 전 값이다.
- 예를 들어 arm 이동 명령, gripper 명령 등이 포함된다.

### `actions`

- 실제로 `env.step()`에 들어간 최종 action vector다.
- `build_env_action()`에서 robosuite 형식으로 조합한 1차원 numpy 배열이다.

### `rewards`

- 각 step의 reward 값이다.

### `dones`

- 각 step의 done 값이다.
- 현재 환경 설정에서는 `ignore_done=True` 이므로 일반적인 episode 종료 기준으로 크게 쓰이지 않을 수 있다.

### `task_success`

- 각 step에서의 전체 task 성공 여부다.
- 현재 `PickPlace` 기본 판정을 사용한다.
- 현재 설정에서는 보통 모든 객체가 올바른 목표 위치에 들어가야 `True`가 된다.

### `partial_success`

- 각 step에서 물체 1개 이상이 목표 bin에 들어갔는지 나타낸다.
- 현재 저장 트리거로 사용되는 신호다.

### `gripper_ball_contact`

- 각 step에서 gripper와 동적 장애물 공이 실제 contact를 일으켰는지 나타낸다.

### `step_time`

- 각 step에서 action 생성과 `env.step()` 처리에 걸린 시간이다.

## `task_success` 와 `partial_success` 차이

- `task_success`: 전체 task 완료 여부
- `partial_success`: 일부 객체라도 성공했는지 여부

현재 코드는 `partial_success`가 발생하면 바로 저장하므로, 저장된 파일의 마지막 step에서:

- `partial_success`는 항상 `True`
- `task_success`는 `True`일 수도 있고 `False`일 수도 있다

## 저장되지 않는 값

- `info["object_goal_status"]`는 runtime에서는 계산되지만 현재 HDF5에는 저장하지 않는다.
- `next_obs`는 별도 이름으로 저장하지 않고, 다음 loop에서 다음 step의 `obs`로 기록된다.

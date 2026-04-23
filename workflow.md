# Workflow

이 문서는 현재 `pseudo-lab` 폴더에서 진행한 작업 내용을 순서대로 정리한 메모다.
다음에 다시 이어서 작업할 때 이 파일을 먼저 읽으면 현재 상태를 빠르게 복원할 수 있다.

## Current Status

- 메인 실행 스크립트는 [run.py](/home/sub/workspace/RL_project/pseudo-lab/run.py) 이다.
- 커스텀 환경 정의는 [custom_env.py](/home/sub/workspace/RL_project/pseudo-lab/custom_env.py) 이다.
- 베이스 환경은 `robosuite 1.5.2`의 `PickPlace`를 상속한다.
- 로봇은 `Panda` 하나를 사용한다.
- 키보드 teleop 조작이 가능하다.
- free camera를 사용하므로 마우스로 시점 조작이 가능하다.
- `VisualizationWrapper`를 사용하므로 gripper 방향 가이드가 표시된다.
- 객체 1개 이상 성공한 teleop episode만 `HDF5`로 저장하도록 구현되어 있다.
- 저장 경로는 `pseudo-lab/data/teleop_demos` 이다.

## Work Log

### 1. robosuite 버전 확인 및 환경 구조 재정리

- 초기에 `table_top` 기반 코드가 있었지만, 현재 설치된 `robosuite 1.5.x` 구조와 맞지 않는 부분이 있었다.
- 그래서 존재하지 않는 `table_top` 기반 접근 대신, `PickPlace` 기반 커스텀 환경으로 방향을 정리했다.
- 실행용 코드와 환경 정의 코드를 분리했다.

### 2. 커스텀 환경을 `PickPlace` 기반으로 수정

- [custom_env.py](/home/sub/workspace/RL_project/pseudo-lab/custom_env.py) 에서 `DynamicObstacleEnv(PickPlace)` 구조를 만들었다.
- `BallObject`를 사용해 빨간 공 장애물을 추가했다.
- 공은 worldbody에 직접 append 되도록 구성했다.
- 공은 슬라이드 조인트를 사용해 코드에서 위치를 직접 갱신할 수 있게 만들었다.

### 3. Panda 시작 위치 조정

- `PickPlace` 기본 Panda 위치는 그대로 두지 않고, 약간 왼쪽으로 이동시켰다.
- 현재는 `robot_base_shift = [0.0, -0.08, 0.0]` 이 적용되어 있다.
- 이 값은 [custom_env.py](/home/sub/workspace/RL_project/pseudo-lab/custom_env.py) 안에서 수정 가능하다.

### 4. 공 이동 방식 변경

- 처음에는 단순 x축 운동으로 시작했다.
- 이후 x-z 운동, 오른쪽 테이블 전용 이동, x-y 평면 이동 순서로 변경했다.
- 현재는 오른쪽 테이블 위에서만 움직인다.
- 현재 공은 고정된 z 높이를 유지하고, x-y 평면에서 지그재그로 움직인다.
- 지그재그는 삼각파 기반이라서 sin 파형보다 더 각진 움직임을 만든다.
- 현재 관련 파라미터는 아래와 같다.
  - `obstacle_x_center`
  - `obstacle_y_center`
  - `obstacle_x_amplitude`
  - `obstacle_y_amplitude`
  - `obstacle_speed`

### 5. 키보드 teleop 조작 추가

- [run.py](/home/sub/workspace/RL_project/pseudo-lab/run.py) 에 실행 루프를 만들었다.
- `load_composite_controller_config()`로 Panda 제어 설정을 로드한다.
- `Keyboard`를 그대로 쓰지 않고 `SimpleKeyboard` 클래스를 만들어 키 매핑을 단순화했다.
- 현재 키 매핑은 아래와 같다.
  - `left / right`: x축 이동
  - `up / down`: y축 이동
  - `z / x`: z축 이동
  - `space`: gripper open / close
  - `q`: reset
  - `e r y h o p`: gripper orientation 회전

### 6. 시각화 개선

- `render_camera=None` 으로 설정해서 free camera를 사용한다.
- 그래서 마우스로 카메라 시점 변경이 가능하다.
- `VisualizationWrapper`를 붙여서 demo 스타일의 gripper 방향 가이드를 표시하도록 했다.

### 7. 충돌 체크 추가

- Panda gripper와 공이 실제로 닿았는지 확인하는 기능을 추가했다.
- MuJoCo `contact` 데이터를 직접 읽어서 판단한다.
- 단순 거리 기반이 아니라 실제 collision geom 접촉 여부를 사용한다.
- 현재 결과는 아래 위치에서 확인 가능하다.
  - `obs["gripper_ball_contact"]`
  - `info["gripper_ball_contact"]`

### 8. 오른쪽 목표 위치 판정 추가

- 현재 환경은 왼쪽 테이블 물체를 오른쪽 테이블의 목표 위치로 옮기는 `PickPlace` 구조를 그대로 사용한다.
- 오른쪽 테이블에 보이는 그림자 위치는 `target_bin_placements`로 관리된다.
- 현재 각 물체가 올바른 오른쪽 위치에 들어갔는지 판단하는 정보도 추가했다.
- 성공 판정은 "정확한 한 점 좌표"가 아니라 "각 물체 전용 bin 칸 내부에 들어왔는지" 기준이다.
- 즉, 오른쪽 테이블의 해당 칸 안에만 들어오면 되고, 칸 내부의 정확한 한 점에 둘 필요는 없다.
- 추가로 gripper가 아직 물체에 너무 가까이 있으면 성공으로 보지 않는다.
- 현재 결과는 아래 위치에서 확인 가능하다.
  - `obs["objects_in_bins"]`
  - `obs["target_bin_placements"]`
  - `info["object_goal_status"]`
  - `info["task_success"]`
  - `info["partial_success"]`

### 9. task_success 기준 확인

- 현재 환경은 `PickPlace`의 기본 성공 판정을 그대로 쓴다.
- 즉, `single_object_mode == 0`인 현재 설정에서는 `1개 물체만 성공`해서는 `task_success`가 되지 않는다.
- 현재는 `모든 객체가 올바른 오른쪽 위치에 들어가야` `task_success == True` 가 된다.
- 반대로 `single_object_mode`를 `1` 또는 `2`로 바꾸면, `1개 객체 성공`만으로도 `task_success == True` 가 된다.
- 별도로 `partial_success`를 추가해서, 현재는 `objects_in_bins` 합이 1 이상이면 저장 조건을 만족하게 해두었다.

### 10. Teleop 성공 episode 저장 구현

- [run.py](/home/sub/workspace/RL_project/pseudo-lab/run.py) 에 episode 버퍼를 추가했다.
- 매 step마다 저차원 observation, action, raw keyboard action, reward, success 신호를 기록한다.
- `info["partial_success"] == True`가 되는 순간 현재 episode를 성공 episode로 간주하고 저장한다.
- 저장 포맷은 `HDF5`이고, imitation learning 재사용을 위해 step별 observation / action / reward / success를 함께 저장한다.
- 사용자가 `q`로 중간 reset한 실패 episode는 저장하지 않고 버린다.
- 저장 파일 안에는 `task_success`와 `partial_success`가 둘 다 들어간다.

## Runtime Signals

실행 중 유용한 값은 다음과 같다.

- `obs["dynamic_obs_pos"]`: 공의 현재 위치
- `obs["dynamic_obs_vel"]`: 공의 현재 속도 추정값
- `obs["gripper_ball_contact"]`: 집게와 공의 접촉 여부
- `obs["objects_in_bins"]`: 각 물체의 목표 위치 도달 여부
- `obs["target_bin_placements"]`: 각 물체의 정답 목표 좌표
- `obs["partial_success"]`: 물체 1개 이상 성공 여부
- `info["object_goal_status"]`: 물체 이름별 성공 여부
- `info["task_success"]`: 현재 task 성공 여부
- `info["partial_success"]`: 현재 partial success 여부

## Run Command

현재 실행은 아래 명령으로 한다.

```bash
python run.py
```

## TODO

- `workflow.md`에 저장되는 HDF5 내부 구조 예시를 더 구체적으로 적기
- `object_goal_status`를 HDF5 안에도 명시적으로 저장할지 결정하기
- 필요하면 `partial_success`를 "특정 객체만 성공" 조건으로 더 좁게 바꾸기

# pseudo-lab

## 주요 파일

- [run.py](/home/sub/workspace/RL_project/pseudo-lab/run.py): 메인 실행 스크립트. 환경 생성, 키보드 teleop, episode 기록, 성공 episode 저장을 담당한다.
- [custom_env.py](/home/sub/workspace/RL_project/pseudo-lab/custom_env.py): `PickPlace`를 상속한 커스텀 환경 정의 파일. 움직이는 공 장애물, 충돌 체크, success 관련 signal을 추가한다.
- [workflow.md](/home/sub/workspace/RL_project/pseudo-lab/workflow.md): 작업 진행 기록 문서. 지금까지 어떤 변경을 했는지와 실행 흐름을 빠르게 복원할 때 본다.
- [dataset_infomation.md](/home/sub/workspace/RL_project/pseudo-lab/dataset_infomation.md): 저장되는 HDF5 데이터 구조와 각 변수 의미를 설명한 문서다.

## 데이터 저장

- 성공 기준은 현재 `task_success`가 아니라 `partial_success`다.
- 물체가 1개 이상 목표 bin에 들어가면 현재 episode를 저장한다.
- 저장 위치는 `data/teleop_demos` 폴더다.

## 실행

이 폴더는 `uv.lock`을 포함하고 있어서, 같은 플랫폼 기준으로 `uv`만으로 바로 환경을 맞출 수 있다.
현재 설정은 `conda activate RL` 환경과 맞추기 위해 Python `3.11` 기준으로 잠가뒀다.

```bash
uv sync --python 3.11
uv run python run.py
```

## 실행 옵션

| 옵션 | 설명 | 기본값 |
|---|---|---|
| `--object-type` | 물체 1개만 사용 (`milk`, `bread`, `cereal`, `can`) | 전체 물체 |
| `--wide-obstacle` | 장애물 이동 범위를 pick 영역까지 확장 | 비활성 (place 영역만) |
| `--obstacle-speed` | 장애물 이동 속도 배율 | `1.1` |

### 예시

```bash
# 기본 실행 (팀원 원본과 동일)
python run.py

# milk 물체 1개만 사용
python run.py --object-type milk

# 장애물이 pick/place 전체 영역을 이동
python run.py --wide-obstacle

# 장애물 속도를 2배로
python run.py --obstacle-speed 2.0

# 옵션 조합
python run.py --object-type milk --wide-obstacle --obstacle-speed 0.5
```

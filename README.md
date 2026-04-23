# pseudo-lab

## 주요 파일

- [run.py](/home/sub/workspace/RL_project/pseudo-lab/run.py): 메인 실행 스크립트. 환경 생성, 키보드 teleop, episode 기록, 성공 episode 저장을 담당한다.
- [custom_env.py](/home/sub/workspace/RL_project/pseudo-lab/custom_env.py): `PickPlace`를 상속한 커스텀 환경 정의 파일. 움직이는 공 장애물, 충돌 체크, success 관련 signal을 추가한다.
- [workflow.md](/home/sub/workspace/RL_project/pseudo-lab/workflow.md): 작업 진행 기록 문서. 지금까지 어떤 변경을 했는지와 실행 흐름을 빠르게 복원할 때 본다.
- [dataset_infomation.md](/home/sub/workspace/RL_project/pseudo-lab/dataset_infomation.md): 저장되는 HDF5 데이터 구조와 각 변수 의미를 설명한 문서다.

## 데이터 저장

- 성공 기준은 현재 `task_success`가 아니라 `partial_success`다.
- 물체가 1개 이상 목표 bin에 들어가면 현재 episode를 저장한다.
- 저장 위치는 [data](/home/sub/workspace/RL_project/pseudo-lab/data) 아래의 `teleop_demos` 폴더다.

## 실행

이 폴더는 `uv.lock`을 포함하고 있어서, 같은 플랫폼 기준으로 `uv`만으로 바로 환경을 맞출 수 있다.

```bash
uv sync
uv run python run.py
```

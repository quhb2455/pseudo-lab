import numpy as np
from robosuite.environments.manipulation.pick_place import PickPlace
from robosuite.models.objects import BallObject


class DynamicObstacleEnv(PickPlace):
    def __init__(self, **kwargs):
        # 장애물의 기본 크기와 기준 높이를 먼저 계산한다.
        # PickPlace는 bin 위치를 기준으로 테이블 높이가 정해지므로,
        # bin1_pos를 이용하면 장애물을 테이블 위 적절한 높이에 배치할 수 있다.
        self.obstacle_radius = 0.05
        bin1_pos = np.array(kwargs.get("bin1_pos", (0.1, -0.25, 0.8)))
        bin2_pos = np.array(kwargs.get("bin2_pos", (0.1, 0.28, 0.8)))
        self.table_top_z = float(bin1_pos[2] + 0.02)
        self.obstacle_center_z = self.table_top_z + self.obstacle_radius + 0.18

        # 로봇 시작 위치를 기본값보다 조금 왼쪽으로 옮기기 위한 보정값이다.
        # y를 음수 방향으로 조금 이동하면 화면 기준 왼쪽으로 비켜난 느낌이 난다.
        self.robot_base_shift = np.array([0.0, -0.08, 0.0])

        # 장애물 이동 파라미터. kwargs로 받으면 기본값을 덮어쓸 수 있어 외부에서 모드를 전환하기 쉽다.
        # pop을 쓰는 이유: PickPlace가 모르는 키를 super().__init__에 넘기면 오류가 나므로 미리 꺼낸다.
        self.obstacle_x_center = float(kwargs.pop("obstacle_x_center", bin2_pos[0] + 0.02))
        self.obstacle_y_center = float(kwargs.pop("obstacle_y_center", bin2_pos[1]))
        self.obstacle_x_amplitude = float(kwargs.pop("obstacle_x_amplitude", 0.16))
        self.obstacle_y_amplitude = float(kwargs.pop("obstacle_y_amplitude", 0.09))
        self.obstacle_speed = float(kwargs.pop("obstacle_speed", 1.1))

        # 장애물을 직접 이동시키기 위해 x / y 슬라이드 조인트를 가진 구체를 추가한다.
        self.obstacle = BallObject(
            name="dynamic_obs",
            size=[self.obstacle_radius],
            rgba=[1, 0, 0, 1],
            friction=[0.0001, 0.005, 0.0001],
            obj_type="all",
            joints=[
                {"type": "slide", "name": "obs_x", "axis": "1 0 0", "damping": "1e-4"},
                {"type": "slide", "name": "obs_y", "axis": "0 1 0", "damping": "1e-4"},
            ],
        )

        # 부모 PickPlace 초기화가 실행되면서 _load_model(), _reset_internal() 같은
        # 내부 함수도 이어서 호출된다. 따라서 obstacle 관련 설정은 super() 전에 끝내야 한다.
        super().__init__(**kwargs)
        self.obstacle_body_id = None
        self.prev_pos = np.array([0.0, 0.0, self.obstacle_center_z], dtype=float)

    def _load_model(self):
        # 먼저 PickPlace 기본 장면(로봇, 테이블, bin, 물체 등)을 구성한다.
        super()._load_model()

        # PickPlace가 잡아둔 Panda 기본 위치에서 y축으로 조금 더 왼쪽으로 이동시킨다.
        robot_model = self.robots[0].robot_model
        default_base_pos = np.array(robot_model.base_xpos_offset["bins"], dtype=float)
        robot_model.set_base_xpos(default_base_pos + self.robot_base_shift)

        # BallObject는 바로 시뮬레이터에 들어가는 것이 아니라 XML body 형태로 변환한 뒤
        # worldbody에 붙여야 실제 MuJoCo 모델 안에 포함된다.
        obstacle_body = self.obstacle.get_obj()
        obstacle_body.set("pos", f"0 0 {self.obstacle_center_z}")
        self.model.worldbody.append(obstacle_body)

    def _reset_internal(self):
        # 환경 reset 시 로봇과 기존 물체 배치도 함께 초기화되므로 부모 reset을 먼저 호출한다.
        super()._reset_internal()

        # 모델이 생성된 뒤에야 body 이름 -> id 매핑을 찾을 수 있다.
        # 이 id를 저장해두면 step에서 장애물의 실제 world 좌표를 빠르게 읽어올 수 있다.
        self.obstacle_body_id = self.sim.model.body_name2id("dynamic_obs_main")

        # reset 직후 장애물을 항상 동일한 시작점으로 되돌린다.
        start_pos = np.array([self.obstacle_x_center, self.obstacle_y_center, self.obstacle_center_z], dtype=float)
        self.set_obstacle_pos(start_pos)

        # 속도는 위치 변화량으로 계산하므로, reset 시점의 이전 위치도 함께 맞춰둔다.
        self.prev_pos = start_pos.copy()

        # 로봇팔 초기 자세 조정
        # joint 1 (shoulder lift): 기본값에서 0.35 감소 → 팔이 위로 올라가 장애물과의 초기 충돌 방지
        # joint 5 (wrist): 2.5로 고정 → 그리퍼가 연직 방향에 가깝게 시작
        joint_idxs = self.robots[0]._ref_joint_pos_indexes
        self.sim.data.qpos[joint_idxs[1]] -= 0.35
        self.sim.data.qpos[joint_idxs[5]] = 2.5
        self.sim.forward()

    def _get_gripper_geom_names(self):
        # Panda gripper의 finger / fingerpad collision geom 이름을 모두 모은다.
        gripper = self.robots[0].gripper["right"]
        geom_groups = gripper.important_geoms
        geom_names = []
        for group_names in geom_groups.values():
            geom_names.extend(group_names)
        return set(geom_names)

    def check_gripper_ball_contact(self):
        # MuJoCo contact 목록을 훑으면서
        # gripper geom과 공 geom이 직접 접촉했는지 확인한다.
        gripper_geom_names = self._get_gripper_geom_names()
        ball_geom_names = set(self.obstacle.contact_geoms)

        for i in range(self.sim.data.ncon):
            contact = self.sim.data.contact[i]
            geom1 = self.sim.model.geom_id2name(contact.geom1)
            geom2 = self.sim.model.geom_id2name(contact.geom2)

            if geom1 is None or geom2 is None:
                continue

            gripper_hit = geom1 in gripper_geom_names or geom2 in gripper_geom_names
            ball_hit = geom1 in ball_geom_names or geom2 in ball_geom_names
            if gripper_hit and ball_hit:
                return True

        return False

    def get_object_goal_status(self):
        # PickPlace는 각 물체가 오른쪽 bin 안의 어느 목표 위치로 가야 하는지
        # target_bin_placements에 이미 저장해둔다.
        # _check_success()를 호출하면 objects_in_bins도 같이 최신 상태로 갱신된다.
        task_success = self._check_success()
        object_goal_status = {obj.name: bool(self.objects_in_bins[i]) for i, obj in enumerate(self.objects)}
        partial_success = bool(np.sum(self.objects_in_bins) > 0)
        return task_success, partial_success, object_goal_status

    # 조인트 qpos를 직접 갱신해서 장애물을 원하는 위치로 이동시킨다.
    def set_obstacle_pos(self, pos):
        # obstacle에 x축, y축 slide joint를 달아뒀기 때문에
        # 원하는 위치로 옮기려면 해당 joint의 qpos 인덱스를 찾아 값을 써야 한다.
        joint_x_id = self.sim.model.joint_name2id("dynamic_obs_obs_x")
        joint_y_id = self.sim.model.joint_name2id("dynamic_obs_obs_y")

        qpos_x_idx = self.sim.model.jnt_qposadr[joint_x_id]
        qpos_y_idx = self.sim.model.jnt_qposadr[joint_y_id]
        qvel_x_idx = self.sim.model.jnt_dofadr[joint_x_id]
        qvel_y_idx = self.sim.model.jnt_dofadr[joint_y_id]

        # z는 고정 높이로 두고, x / y만 슬라이드 조인트 값으로 직접 넣는다.
        self.sim.data.qpos[qpos_x_idx] = pos[0]
        self.sim.data.qpos[qpos_y_idx] = pos[1]

        # 위치를 강제로 바꿨기 때문에 이전 속도를 남겨두면 물리적으로 튀는 현상이 생길 수 있다.
        # 그래서 해당 joint 속도는 0으로 초기화한다.
        self.sim.data.qvel[qvel_x_idx] = 0.0
        self.sim.data.qvel[qvel_y_idx] = 0.0

        # qpos / qvel 수정 후 forward()를 호출해야 MuJoCo 내부 상태와 body 좌표가 갱신된다.
        self.sim.forward()

    def _triangle_wave(self, t):
        # 0~1 구간을 반복하는 값을 만든 뒤, 이를 -1~1 삼각파로 바꾼다.
        # 삼각파는 sin보다 꺾이는 모서리가 분명해서 더 각진 움직임을 만든다.
        phase = (t * self.obstacle_speed) % 1.0
        return 4.0 * abs(phase - 0.5) - 1.0

    # 장애물은 오른쪽 bin 위에서 지그재그로 움직인다.
    def step(self, action):
        # x는 빠르게 좌우로 크게 왕복하고,
        # y는 더 느리게 바뀌게 해서 선이 꺾이는 넓은 지그재그 모양이 나오게 만든다.
        x_wave = self._triangle_wave(self.cur_time)
        y_wave = self._triangle_wave(self.cur_time * 0.3)
        obstacle_pos = np.array(
            [
                self.obstacle_x_center + self.obstacle_x_amplitude * x_wave,
                self.obstacle_y_center + self.obstacle_y_amplitude * y_wave,
                self.obstacle_center_z,
            ],
            dtype=float,
        )

        # 로봇 action을 적용하기 전에 장애물 위치를 먼저 업데이트해서
        # 같은 스텝 안에서 로봇이 최신 장애물 상태를 보게 한다.
        self.set_obstacle_pos(obstacle_pos)

        # 그 다음 부모 환경의 step을 호출해 실제 물리 시뮬레이션을 한 스텝 진행한다.
        obs, reward, done, info = super().step(action)

        # body_xpos는 MuJoCo가 계산한 실제 world 좌표다.
        # 이를 observation에 넣어주면 외부 코드에서 장애물 상태를 바로 사용할 수 있다.
        current_pos = self.sim.data.body_xpos[self.obstacle_body_id].copy()
        obs["dynamic_obs_pos"] = current_pos

        # 속도는 별도 센서를 쓰지 않고, 현재 위치 - 이전 위치를 control_freq로 스케일해서 근사한다.
        obs["dynamic_obs_vel"] = (current_pos - self.prev_pos) * self.control_freq
        self.prev_pos = current_pos

        # 공과 gripper의 실제 접촉 여부를 기록한다.
        gripper_ball_contact = self.check_gripper_ball_contact()
        obs["gripper_ball_contact"] = np.array([float(gripper_ball_contact)])

        # 왼쪽 물체가 오른쪽 테이블의 올바른 자리(그림자 위치)에 들어갔는지도 기록한다.
        task_success, partial_success, object_goal_status = self.get_object_goal_status()
        obs["objects_in_bins"] = self.objects_in_bins.copy()
        obs["target_bin_placements"] = self.target_bin_placements.copy()
        obs["partial_success"] = np.array([float(partial_success)])

        info["gripper_ball_contact"] = gripper_ball_contact
        info["object_goal_status"] = object_goal_status
        info["task_success"] = bool(task_success)
        info["partial_success"] = partial_success

        return obs, reward, done, info

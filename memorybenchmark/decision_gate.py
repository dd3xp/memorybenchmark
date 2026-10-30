"""Optional experiment control: one game-action attempt per model response."""
from copy import deepcopy


ACTION_POLICIES = ("batch", "single")
SINGLE_ACTION_GUIDE = """
本次采用逐步交互：每次模型响应最多执行一次游戏动作（move、inspect、process、submit 或 abandon）。
每次 code_run 只执行一个游戏动作，收到实际反馈后再决定下一步；不要在脚本或同次响应的多个工具调用中批量执行游戏动作。
read 以及你原生的记忆、文件工具不受此限制。若收到 decision_boundary，停止当前脚本，依据其中的最新反馈在下一轮继续。
"""


class DecisionGate:
    def __init__(self, policy="batch"):
        if policy not in ACTION_POLICIES:
            raise ValueError("Unknown game action policy")
        self.policy = policy
        self.used = True
        self.model_response = 0
        self.rejections = 0
        self.last_feedback = None

    def begin_response(self, number):
        self.model_response = number
        self.used = False

    def claim(self, request):
        if self.policy == "batch" or request.get("command") != "action":
            return True
        if self.used:
            self.rejections += 1
            return False
        self.used = True
        return True

    def observe(self, result):
        if isinstance(result, dict) and "observation" in result:
            self.last_feedback = deepcopy(result)

    def rejected(self):
        return {"error": "decision_boundary", "model_response": self.model_response,
                "message": "本轮已执行一次游戏动作；停止脚本，收到下一次模型响应后再行动。额外动作未执行，不增加游戏操作或路程。",
                "last_game_response": deepcopy(self.last_feedback)}

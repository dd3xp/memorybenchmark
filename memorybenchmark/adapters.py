"""Human and agent transports share this public game interface."""
from uuid import uuid4

from .game import Game, ProtocolError


def render_text(observation):
    o = observation
    weather = {"rain": "下雨", "clear": "晴朗", "snow": "下雪"}[o["conditions"]["weather"]]
    period = {"day": "白天", "night": "夜间"}[o["conditions"]["period"]]
    routes = "；".join(f"{n['name']} {n['target']}（距离 {n['distance']}）" for n in o["neighbors"])
    carried = "、".join(f"{t['name']}（{t['id']}）" for t in o["inventory"]) or "无"
    stock = "；".join(f"{t['name']}（{t['id']}）：{t['description']}" for t in o["available_tools"]) or "无"
    return (f"任务：{o['instruction']}\n当前位置：{o['location']['name']} {o['location']['id']}\n"
            f"环境：{weather}，{period}；游戏时间 {o['world_time']}\n"
            f"可尝试的通路：{routes}\n已测量地点：{', '.join(o['map']['surveyed']) or '无'}\n"
            f"体力：{o['stamina']}/{o['initial_stamina']}；累计体力需求：{o['effort']}\n"
            f"携带工具：{carried}\n此处可取用：{stock}\n"
            f"操作：{o['steps']}/{o['max_steps']}；移动距离：{o['distance']}\n"
            f"任务结束：{o['done']}；成功：{o['success']}")


class GameAdapter:
    """Thin transport adapter. It makes no planning or memory decisions."""
    def __init__(self, game: Game):
        self.game = game

    def _public(self, response):
        return {**response, "text": response["feedback"] + "\n" + render_text(response["observation"])}

    def dispatch(self, request):
        if not isinstance(request, dict):
            raise ProtocolError("请求必须是 JSON 对象。")
        command = request.get("command")
        if command == "start":
            return self._public(self.game.start_task(request.get("task_id", "T1")))
        if command == "read":
            return self._public({"observation": self.game.observation(), "feedback": "当前观察。", "outcome": "read"})
        if command == "action":
            return self._public(self.game.step(request.get("action"),
                request_id=request.get("request_id"), expected_revision=request.get("expected_revision")))
        raise ProtocolError("command 应为 start、read 或 action。")

    def action(self, verb, target=None):
        """Convenience for a native tool bridge; not a new agent implementation."""
        action = {"type": verb}
        if target is not None:
            action["target"] = target
        return self.dispatch({"command": "action", "action": action,
                              "request_id": uuid4().hex, "expected_revision": self.game.revision})

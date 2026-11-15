"""Shared authored rules; no agent planning, memories or runtime sampling."""
from itertools import permutations

from scripts.build_easy20_reuse_map import ITINERARIES


MATERIAL_SLOTS = ('profile', 'shore', 'vegetation', 'lithology',
                  'bearing', 'elevation', 'contour', 'drainage')


def build_tasks(kinds):
    slots = dict(zip(MATERIAL_SLOTS, kinds))
    tasks = {}
    for index, itinerary in enumerate(ITINERARIES, 1):
        stages = [{'target': target, 'required_kind': slots[kind]} for target, kind in itinerary]
        tasks[f'T{index}'] = {'name': f'联程巡测 {index:02d}', 'start': 'C', 'submit_at': 'C',
                             **stages[0], 'stages': stages, 'max_steps': 88}
    return tasks


def game_rules(kinds):
    names = '、'.join(name.removesuffix('资料') for name in kinds.values())
    return [
        '每项测绘委托有两段行程。依次到当前目标点主动 survey 勘探，采集本段指定资料，再到支持该类资料的基站处理；两段完成后回 C 营地交付一次。',
        '目标是在操作预算内完成委托，优先减少道路总距离，距离相同时减少操作。全图从第一项起可自由探索，不设教学或解锁阶段。',
        'A 至 H 是八种公开站型，每型两座站。同型站支持相同资料；类型字母、站名和研究主题不代表具体处理能力。同一地图的能力配对跨委托、跨 session、跨 Agent 和重复实验保持固定。',
        '八种站型与八类资料一一对应，每种站型只处理其中一类资料；具体配对需交互获知。资料类别不限定候选站型。',
        f'本图的八类资料为：{names}。所有资料都在当前任务目标点通过 survey 取得。',
        '不提供独立查询。只有携带当前段资料，在基站主动执行 process 提交处理后，才反馈该站型的实际能力与本次处理结果；成功与失败都消耗一次操作，不匹配时原始资料保留，可以换站重试。仅到访或经过不会揭示处理能力。',
        '在任一同型站获得的能力经验可以用于另一座同型站。地理图始终可见，但不记录历史能力、处理反馈或替你保存经验。',
        '抵达或经过目标不会自动采集；只有在当前段指定目标主动 survey 一次才取得本段资料。勘探占一次操作，不增加路程，已有资料时不能重复勘探。处理成功后进入下一段，提前经过后续目标不算完成后续采集。只能沿公开道路逐点移动，不可跳过中间地点。',
        '已完成处理的资料不能再次 process；全部行程完成后回 C 营地主动 submit 交付。read 只返回当前公开地图与状态，不提供站点能力答案。',
        '每项从 C 开始，位置、资料、对话和工作记忆重置；只有 Agent 自主保存的持久记忆跨 session。失败后继续固定任务流，只能保留实际经历过的经验，不补发答案。',
        '一项最多八十八次操作，read 免费。',
    ]


def fixed_world(kinds, fixture):
    target = tuple(fixture[t] for t in 'ABCDEFGH')
    index = next(i for i, ordering in enumerate(permutations(kinds)) if ordering == target)
    return f'omega_{index:02d}'


def assemble(*, version, name, terrain, core, roads, surveys, stations,
             kinds, selection, fixture, provenance, regions, bounds=(0, 0, 2200, 1600)):
    locations = {key: {'name': label, 'kind': 'camp' if key == 'C' else 'junction', 'x': x, 'y': y}
                 for key, (label, x, y) in core.items()}
    edges = [list(edge) for edge in roads]
    for key, (label, fork, x, y) in surveys.items():
        if key in locations:
            raise ValueError('Duplicate survey location: ' + key)
        locations[key] = {'name': label, 'kind': 'survey', 'x': x, 'y': y}
        edges.append([fork, key, 1])
    for key, (fork, x, y, distance) in stations.items():
        origin = locations[fork]
        transit = key.lower() + 'p1'
        if key in locations or transit in locations:
            raise ValueError('Duplicate station location: ' + key)
        locations[transit] = {'name': f'{key} 支路', 'kind': 'junction', 'transit': True,
                              'x': round((origin['x'] + x) / 2), 'y': round((origin['y'] + y) / 2)}
        locations[key] = {'name': f'{key[0]} 型调查基站 · {key}', 'kind': 'station',
                          'station_type': key[0], 'x': x, 'y': y}
        edges.extend([[fork, transit, 1], [transit, key, distance - 1]])
    return {
        'design_id': version, 'status': 'formal_easy_candidate_pending_native_agent_calibration',
        'world_generator': 'station_type_permutations', 'fixed_world': fixed_world(kinds, fixture),
        'material_selection': selection,
        'public': {
            'version': version, 'name': name, 'difficulty': 'Easy', 'terrain': terrain,
            'station_query_enabled': False, 'manual_survey_required': True,
            'view_box': list(bounds), 'rules': game_rules(kinds), 'kinds': kinds,
            'vocabulary': {'survey': '测绘点', 'station': '基站', 'collect': '采集', 'process': '处理', 'item': '资料', 'submit': '交付'},
            'station_types': {t: {'name': f'{t} 型', 'stations': [t+'1', t+'2']} for t in 'ABCDEFGH'},
            'locations': locations, 'edges': edges,
        },
        'tasks': build_tasks(kinds), 'presentation': {'terrain': terrain, 'regions': regions},
        'evaluation': {
            'experience_protocol': 'station-experience-opportunity-1',
            'opportunity_basis': 'Only feedback actually delivered before the session; distinguish observation, type propagation and inference.',
            'failure_policy': 'Continue the fixed stream with actual feedback only; do not supply missing experiences.',
            'stream_policy': 'Twenty fixed ordinary commissions, forty stages. Independent original-memory baseline per map and condition.',
            'diagnostic_scope': 'Acquisition, delivered evidence, station choices and graph costs. No claim of large-capacity memory or controlled interference.',
        },
        'provenance': provenance,
    }

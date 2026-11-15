"""Balanced four-exposure task streams, authored without model outcomes."""
from collections import Counter
from random import Random


EXPOSURES = 4


def four_exposure_tasks(kinds, surveys, *, requirements=None, order_seed,
                        target_seed, max_steps, name, minimum_repeat_gap=0):
    contexts = [(k, r) for k in kinds for r in (requirements or (None,))]
    if len(contexts) % 2 or not contexts or len(set(contexts)) != len(contexts):
        raise ValueError('Task contexts must be distinct and pair into two stages')
    rng = Random(order_seed)
    stream, last = [], {}
    for block in range(EXPOSURES):
        remaining = contexts[:]
        while remaining:
            task_index = len(stream) // 2
            available = [c for c in remaining
                         if task_index - last.get(c, -10000) >= minimum_repeat_gap]
            if not available:
                raise ValueError('Repeat gap is infeasible for this context pool')
            context = rng.choice(available)
            stream.append(context)
            remaining.remove(context)
            last[context] = task_index
    if len(stream) % len(surveys):
        raise ValueError('Survey visits must remain balanced')
    targets = list(surveys) * (len(stream) // len(surveys))
    rng = Random(target_seed)
    for _ in range(10000):
        rng.shuffle(targets)
        if all(targets[i] != targets[i + 1] for i in range(0, len(targets), 2)):
            break
    else:
        raise ValueError('Cannot pair distinct survey targets')
    tasks = {}
    for i in range(len(stream) // 2):
        stages = []
        for j in range(2):
            kind, requirement = stream[2*i+j]
            stage = {'target': targets[2*i+j], 'required_kind': kind}
            if requirement is not None:
                stage['requirement'] = requirement
            stages.append(stage)
        tasks[f'T{i+1}'] = {'name': f'{name} {i+1:02d}', 'start': 'C',
                           'submit_at': 'C', **stages[0], 'stages': stages,
                           'max_steps': max_steps}
    assert set(Counter(stream).values()) == {EXPOSURES}
    return tasks


def exposure_diagnostics(tasks):
    counts, last, gaps = Counter(), {}, []
    for i, task in enumerate(tasks.values()):
        for stage in task['stages']:
            context = (stage['required_kind'], stage.get('requirement'))
            counts[context] += 1
            if context in last:
                gaps.append(i - last[context])
            last[context] = i
    return {'protocol': 'four-exposures-two-stages-v1', 'tasks': len(tasks),
            'stages': sum(counts.values()), 'contexts': len(counts),
            'context_exposures': {'|'.join(value or 'default' for value in context): n
                                 for context, n in counts.items()},
            'minimum_repeat_gap_tasks': min(gaps),
            'maximum_repeat_gap_tasks': max(gaps),
            'mean_repeat_gap_tasks': sum(gaps) / len(gaps)}


def regional_transfer_tasks(kinds, surveys, *, requirements, regions,
                            order_seed, target_seed, max_steps, name):
    """Four material/purpose exposures, moving their destination across regions."""
    tasks = four_exposure_tasks(kinds, surveys, requirements=requirements,
        order_seed=order_seed, target_seed=target_seed, max_steps=max_steps,
        name=name, minimum_repeat_gap=12)
    zones=list(regions);contexts=[(kind,r) for kind in kinds for r in requirements]
    if len(zones)!=3:raise ValueError('Regional transfer uses three public destination categories')
    rng=Random(order_seed+1);rng.shuffle(contexts)
    first={context:i%3 for i,context in enumerate(contexts)}
    directions={context:rng.choice((-1,1)) for context in contexts}
    seen=Counter()
    for task in tasks.values():
        for stage in task['stages']:
            context=(stage['required_kind'],stage['requirement'])
            stage['required_region']=zones[(first[context]+directions[context]*seen[context])%3]
            seen[context]+=1
        task.update(task['stages'][0])
    return tasks


def requirement_interference_tasks(kinds, surveys, *, requirements, order_seed,
                                   target_seed, max_steps, name):
    """Four exact exposures; an opposite-purpose case separates every repeat.

    Each four-task group handles four materials. Their second purposes occur
    two tasks after their first purposes. Stable groups and within-group
    shuffling keep exact repeat gaps at 11..13 tasks for the twelve-kind case.
    """
    kinds, requirements = list(kinds), list(requirements)
    if len(kinds) % 4 or len(requirements) != 2:
        raise ValueError('Interference stream needs four-kind groups and two requirements')
    tasks = four_exposure_tasks(kinds, surveys, requirements=requirements,
        order_seed=order_seed, target_seed=target_seed, max_steps=max_steps, name=name)
    rng = Random(order_seed)
    rng.shuffle(kinds)
    first = {kind: rng.randrange(2) for kind in kinds}
    stream = []
    for _ in range(EXPOSURES):
        for offset in range(0, len(kinds), 4):
            group = kinds[offset:offset + 4]
            rng.shuffle(group)
            stream.extend((kind, requirements[first[kind]]) for kind in group)
            stream.extend((kind, requirements[1 - first[kind]]) for kind in group)
    stages = [stage for task in tasks.values() for stage in task['stages']]
    for stage, (kind, requirement) in zip(stages, stream):
        stage.update(required_kind=kind, requirement=requirement)
    for task in tasks.values():
        task.update(task['stages'][0])
    return tasks


def requirement_interference_diagnostics(tasks):
    stages = [(index, stage) for index, task in enumerate(tasks.values())
              for stage in task['stages']]
    last, rows = {}, []
    for index, (task_index, stage) in enumerate(stages):
        context = (stage['required_kind'], stage['requirement'])
        if context in last:
            earlier, earlier_task = last[context]
            opposite = [ti for ti, other in stages[earlier + 1:index]
                        if other['required_kind'] == context[0]
                        and other['requirement'] != context[1]]
            rows.append({'kind': context[0], 'requirement': context[1],
                         'repeat_gap_tasks': task_index - earlier_task,
                         'opposite_requirement_between': bool(opposite),
                         'latest_opposite_gap_tasks': task_index - opposite[-1] if opposite else None})
        last[context] = (index, task_index)
    return {'repeat_opportunities': len(rows),
            'with_opposite_requirement_between': sum(row['opposite_requirement_between'] for row in rows),
            'with_opposite_in_previous_three_tasks': sum(row['latest_opposite_gap_tasks'] is not None
                and 1 <= row['latest_opposite_gap_tasks'] <= 3 for row in rows),
            'rows': rows}

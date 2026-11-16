"""Delivered-evidence support for enumerated Easy and symbolic Normal maps.

Normal stores one fixed runtime fixture, not an enumerated hypothesis family.
Its fixture must never be interpreted as knowledge of unobserved stations.
No candidate counts, entropy or exact unknown-world references are fabricated.
"""

from dataclasses import dataclass
from itertools import combinations
from .station_capability import (
    compatible_worlds,
    conditional_capabilities,
    symbolic_capabilities,
)


def symbolic(design):
    return symbolic_capabilities(design)


def freeze_capability(value):
    if isinstance(value, dict):
        return tuple(sorted((k, freeze_capability(v)) for k, v in value.items()))
    return tuple(sorted(value)) if isinstance(value, (list, tuple)) else value


def capability_for(value, requirement=None):
    if isinstance(value, dict):
        if requirement not in value:
            raise ValueError(
                "Conditional station capabilities require a valid processing requirement"
            )
        return value[requirement]
    return value


def supports(value, kind, requirement=None):
    value = capability_for(value, requirement)
    return kind in value if isinstance(value, (list, tuple)) else value == kind


@dataclass(frozen=True)
class DeliveredSupport:
    facts: tuple


def evidence_support(design, events):
    from . import station_interfaces as interfaces

    if interfaces.enabled(design):
        facts = {}
        for event in events:
            feedback = event.get("delivered", {}).get("feedback", {})
            if feedback.get("kind") != "processing_outcome":
                continue
            key = (
                feedback["station_type"],
                feedback["required_kind"],
                feedback["requirement"],
                feedback["input_format"] or "",
            )
            value = (feedback["result"], feedback["output_format"] or "")
            if key in facts and facts[key] != value:
                raise ValueError(
                    "Delivered fixed-interface outcomes contradict each other"
                )
            facts[key] = value
        return DeliveredSupport(tuple(sorted(facts.items())))
    if not symbolic(design):
        return compatible_worlds(design, events)
    locations = design["public"]["locations"]
    facts = {}
    for event in events:
        feedback = event.get("delivered", {}).get("feedback", {})
        if feedback.get("kind") != "station_information":
            continue
        station = feedback["station"]
        type_id = locations[station]["station_type"]
        if conditional_capabilities(design):
            requirement = feedback.get("requirement")
            if requirement not in design["public"]["requirements"]:
                raise ValueError(
                    "Delivered conditional feedback must identify its processing requirement"
                )
            type_id = (type_id, requirement)
        value = freeze_capability(feedback["capability"])
        if type_id in facts and facts[type_id] != value:
            raise ValueError("Delivered same-type capabilities contradict each other")
        facts[type_id] = value
    return DeliveredSupport(tuple(sorted(facts.items())))


def support_count(support):
    return None if isinstance(support, DeliveredSupport) else len(support)


def information_gain(before, after):
    from math import log2

    return (
        None if isinstance(before, DeliveredSupport) else log2(len(before) / len(after))
    )


def capability_options(design, support, station, requirement=None):
    if not isinstance(support, DeliveredSupport):
        return {design["private_worlds"][w][station] for w in support}
    type_id = design["public"]["locations"][station]["station_type"]
    if conditional_capabilities(design):
        if requirement not in design["public"]["requirements"]:
            raise ValueError(
                "Conditional knowledge lookup requires a processing requirement"
            )
        type_id = (type_id, requirement)
    facts = dict(support.facts)
    if type_id in facts:
        return {facts[type_id]}
    kinds = sorted(design["public"]["kinds"])
    return {tuple(c) for size in (1, 2) for c in combinations(kinds, size)}


def historical_status(design, support, station, kind, requirement=None):
    if isinstance(support, DeliveredSupport):
        key = design["public"]["locations"][station]["station_type"]
        if conditional_capabilities(design):
            if requirement not in design["public"]["requirements"]:
                raise ValueError(
                    "Conditional knowledge lookup requires a processing requirement"
                )
            key = (key, requirement)
        value = dict(support.facts).get(key)
        return (
            ("known_match" if supports(value, kind) else "known_nonmatch")
            if value is not None
            else "unresolved"
        )
    values = {
        supports(v, kind)
        for v in capability_options(design, support, station, requirement)
    }
    return (
        "known_match"
        if values == {True}
        else "known_nonmatch" if values == {False} else "unresolved"
    )


def matching_stations(design, support, kind, requirement=None):
    return [
        s
        for s, p in design["public"]["locations"].items()
        if p["kind"] == "station"
        and historical_status(design, support, s, kind, requirement) == "known_match"
    ]


def report_world_ids(support):
    return None if isinstance(support, DeliveredSupport) else list(support)

"""Multiple matches, proximity controls and evidence-conditioned route choices."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from memorybenchmark.prototypes.field_service import FieldService
from memorybenchmark.prototypes.station_capability import StationGame, compatible_worlds, load_design
from memorybenchmark.prototypes.station_choice import choice_context, station_decisions
from memorybenchmark.prototypes.station_routes import feedback_policy, station_options, walk
from memorybenchmark.prototypes.station_session import EASY20_CHOICE_DESIGN, StationSession


class StationChoiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = load_design(EASY20_CHOICE_DESIGN)

    def test_full_balanced_family_keeps_geography_uninformative(self):
        d = self.design
        self.assertEqual((len(d['public']['locations']), len(d['public']['edges']), len(d['private_worlds'])), (38, 45, 1296))
        self.assertEqual(len(d['public']['edges']) - len(d['public']['locations']) + 1, 8)
        for task in d['tasks']:
            options = station_options(d, task)
            self.assertEqual(len({r['completion_distance'] for r in options}), 4)
            nearest = min(options, key=lambda r:r['distance_from_target'])['station']
            kind = d['tasks'][task]['required_kind']
            self.assertEqual(sum(w[nearest] == kind for w in d['private_worlds'].values()), 648)

    def test_one_observation_does_not_reveal_the_other_three(self):
        g = StationGame('omega_2000', self.design);g.start_task('T1')
        walk(g, 'A');g.step({'type':'inspect'})
        possible = compatible_worlds(self.design, g.events)
        self.assertEqual(len(possible), 648)
        for station in ('B','N1','N2'):
            self.assertEqual({self.design['private_worlds'][w][station] for w in possible}, {'profile','shore'})

    def test_unknown_cheaper_match_is_not_scored_as_a_missed_known_route(self):
        g = StationGame('omega_2000', self.design);g.start_task('T1')
        walk(g, 'A');g.step({'type':'inspect'});g.step({'type':'abandon'})
        context = choice_context(self.design, 'T8', g.events, 'A')
        self.assertEqual(context['selected_historical_status'], 'known_match')
        self.assertFalse(context['best_matching_cost_provable_from_history'])
        self.assertIsNone(context['conditional_distance_reference'])
        g.start_task('T3');walk(g, 'N2');g.step({'type':'inspect'});g.step({'type':'abandon'})
        context = choice_context(self.design, 'T8', g.events, 'N2')
        self.assertTrue(context['best_matching_cost_provable_from_history'])
        self.assertEqual(context['lowest_cost_known_matching_stations'], ['N2'])
        self.assertEqual(context['conditional_distance_reference'], 14)

    def test_known_nonmatching_nearest_station_is_distinguishable_from_two_matches(self):
        g = StationGame('omega_5000', self.design);g.start_task('T1')
        for s in ('A','B'):
            walk(g,s);g.step({'type':'inspect'})
        g.step({'type':'abandon'})
        c = choice_context(self.design, 'T19', g.events, 'A')
        self.assertTrue(c['selected_is_geographically_nearest'])
        self.assertEqual(c['selected_historical_status'], 'known_nonmatch')
        self.assertEqual(c['lowest_cost_known_matching_stations'], ['N1'])
        self.assertEqual(c['conditional_distance_reference'],15)
        g.start_task('T19');feedback_policy(g)
        self.assertTrue(g.state.success);self.assertEqual(g.distance,15)
        from memorybenchmark.prototypes.station_analysis import analyze_trace
        row=analyze_trace(self.design,g.events,g.task_run_id,exact_references=False)
        self.assertEqual(row['first_station_choice']['selected_station'],'N1')
        self.assertFalse(row['first_station_choice']['selected_is_geographically_nearest'])
        with self.assertRaises(ValueError):analyze_trace(self.design,g.events,g.task_run_id)

    def test_count_contradictions_are_rejected(self):
        bad = deepcopy(self.design);bad['private_worlds']['omega_0000']['A'] = 'shore'
        with tempfile.TemporaryDirectory() as directory:
            import json
            p=Path(directory)/'invalid.json';p.write_text(json.dumps(bad),encoding='utf-8')
            with self.assertRaises(ValueError):load_design(p)

    def test_prior_feedback_is_not_current_session_knowledge(self):
        g = StationGame('omega_5000', self.design);g.start_task('T1')
        walk(g, 'A');g.step({'type':'inspect'});g.step({'type':'abandon'})
        g.start_task('T19');walk(g, 'P');walk(g, 'A')
        row = station_decisions(self.design, g.events, g.task_run_id)
        first = row['first_postcollection_station']
        self.assertEqual(first['pre_task_history']['selected_historical_status'], 'known_nonmatch')
        self.assertEqual(first['current_session_only']['selected_historical_status'], 'unresolved')
        self.assertEqual(row['postcollection_entries_known_nonmatch_by_history'], 1)
        self.assertEqual(row['postcollection_entries_known_nonmatch_in_current_session'], 0)

    def test_precollection_inspection_stays_within_session_evidence(self):
        g = StationGame('omega_5000', self.design);g.start_task('T1')
        walk(g, 'A');g.step({'type':'inspect'});walk(g, 'P');walk(g, 'A')
        row = station_decisions(self.design, g.events, g.task_run_id)
        self.assertEqual(len(row['precollection_station_entries']), 1)
        self.assertEqual(len(row['postcollection_station_entries']), 1)
        first = row['first_postcollection_station']
        self.assertEqual(first['pre_task_history']['selected_historical_status'], 'unresolved')
        self.assertEqual(first['current_session_only']['selected_historical_status'], 'known_nonmatch')
        self.assertEqual(row['postcollection_entries_known_nonmatch_in_current_session'], 1)

    def test_prior_exclusion_fact_counts_even_without_a_known_match(self):
        from memorybenchmark.prototypes.station_analysis import analyze_trace
        g = StationGame('omega_0010', self.design);g.start_task('T4')
        walk(g, 'F');g.step({'type':'inspect'});g.step({'type':'abandon'})
        g.start_task('T7');g.step({'type':'abandon'})
        row = analyze_trace(self.design, g.events, g.task_run_id, exact_references=False)
        self.assertTrue(row['prior_related_station_feedback_received'])
        self.assertFalse(row['prior_relevant_exposure'])
        self.assertEqual(row['historically_determined_matching_stations'], [])

    def test_choice_human_view_and_native_observation_keep_answer_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            service = FieldService(Path(directory), self.design)
            data = service.start({});token=data['instance_id'];game=service.instances[token]['game']
            self.assertEqual(data['observation']['environment']['version'], 'lanting-easy20-choice-v2')
            self.assertIn('各两站',data['text'])
            self.assertNotIn('capabilities',data)
            before=deepcopy(game.events);view=service.design_view(token)
            self.assertEqual(game.events,before)
            for row in view['tasks']:
                self.assertEqual(len(row['matching_stations']),2)
                self.assertEqual(row['known_world_distance'], min(r['completion_distance'] for r in row['station_options'] if r['matches']))
            native=StationSession(StationGame('omega_5000',self.design),'T1').initial
            import json
            self.assertNotIn('private_worlds',json.dumps(native))
            self.assertEqual(native['feedback'],{'kind':'started'})


if __name__=='__main__':unittest.main()

"""No-model checks against the pinned native log format and the scoped fixture criterion."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from listener_pilot import performance_counters, speech_fixture_assessment


class PilotEvidenceTests(unittest.TestCase):
    def test_real_padded_native_counter_format(self):
        log = """0.04.512.571 I llama_perf_context_print: prompt eval time =     701.39 ms /   942 tokens (    0.74 ms per token,  1343.05 tokens per second)
0.04.512.585 I llama_perf_context_print:        eval time =      71.88 ms /     4 runs   (   17.97 ms per token,    55.65 tokens per second)"""
        self.assertEqual(performance_counters(log), {
            'prompt_eval': {'milliseconds': 701.39, 'tokens': 942, 'tokens_per_second': 1343.05},
            'generation_eval': {'milliseconds': 71.88, 'runs': 4, 'tokens_per_second': 55.65}})

    def test_missing_counters_remain_missing(self):
        self.assertEqual(performance_counters('speech, no music'), {})

    def test_speech_synonyms_are_accepted_with_scoped_evidence(self):
        for tags in ('speech, no music', 'spoken word, no music, no instruments', ' Spoken voice , NO MUSIC '):
            with self.subTest(tags=tags):
                result = speech_fixture_assessment(tags)
                self.assertTrue(result['passed'])
                self.assertFalse(result['general_music_tagging_verified'])
                self.assertFalse(result['long_audio_verified'])

    def test_music_hallucination_and_incomplete_answer_fail(self):
        for tags in ('electronic, synth-pop, female vocal, electric guitar',
                     'speech, no music, guitar', 'speech', 'no music'):
            with self.subTest(tags=tags):
                self.assertFalse(speech_fixture_assessment(tags)['passed'])


if __name__ == '__main__':
    unittest.main(verbosity=2)

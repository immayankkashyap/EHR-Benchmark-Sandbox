import importlib.util
import json
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('benchmark_wrapper', ROOT/'scripts/benchmark.py')
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)


class Checkpoints(unittest.TestCase):
    def test_missing_key_stops_before_inference(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(wrapper, 'execute') as execute:
            argv = ['benchmark.py', 'run', '--provider', 'gemini', '--model', 'test',
                    '--key', str(Path(directory)/'missing.json')]
            with patch.object(wrapper.sys, 'argv', argv), patch('sys.stderr', new_callable=io.StringIO) as stderr:
                with self.assertRaises(SystemExit) as caught:
                    wrapper.main()
            self.assertEqual(caught.exception.code, 2)
            self.assertIn('No model calls were made', stderr.getvalue())
            execute.assert_not_called()

    def test_scoring_failure_preserves_logs_and_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            def execute(command, check=True):
                if command[1] == 'benchmark-runner/run.py':
                    logs = Path(command[command.index('--logs')+1])
                    logs.mkdir(parents=True)
                    (logs/'case.jsonl').write_text('{}\n')
                    return Mock(returncode=0)
                self.assertIn('--key', command)
                return Mock(returncode=2)
            with patch.object(wrapper, 'execute', side_effect=execute) as mocked, patch('sys.stderr', new_callable=io.StringIO):
                self.assertEqual(wrapper.run_batches([wrapper.PYTHON, 'benchmark-runner/run.py'], [],
                                 [1, 2], output, 1, Path('custom-key.json')), 2)
            self.assertEqual(mocked.call_count, 2)
            self.assertTrue((output/'logs/batch-0001/case.jsonl').exists())

    def test_case_selection(self):
        self.assertEqual(wrapper.selected_cases('1-3,2,10'), [1, 2, 3, 10])
        for value in ('0', '501', '3-1', '1,', 'one'):
            with self.assertRaises(ValueError):
                wrapper.selected_cases(value)

    def test_cumulative_checkpoints_and_partial_final_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            batches, scores = [], []
            def execute(command, check=True):
                if command[1] == 'benchmark-runner/run.py':
                    logs = Path(command[command.index('--logs')+1])
                    selected = wrapper.selected_cases(command[command.index('--cases')+1])
                    batches.append(selected)
                    logs.mkdir(parents=True)
                    for case in selected:
                        (logs/f'{case}.jsonl').write_text('{}\n')
                else:
                    count = len(list((output/'logs').rglob('*.jsonl')))
                    scores.append(count)
                    (output/'report.json').write_text(json.dumps({'count': count}))
                    (output/'report.md').write_text(f'Cases: {count}')
                return Mock(returncode=0)
            with patch.object(wrapper, 'execute', side_effect=execute):
                self.assertEqual(wrapper.run_batches([wrapper.PYTHON, 'benchmark-runner/run.py'], ['--smoke'], list(range(1, 22)), output), 0)
            self.assertEqual([len(b) for b in batches], [10, 10, 1])
            self.assertEqual(scores, [10, 20, 21])
            for count in scores:
                self.assertEqual(json.loads((output/'scores'/f'after-{count:04d}.json').read_text())['count'], count)
            self.assertEqual(json.loads((output/'report.json').read_text())['count'], 21)

    def test_configuration_failure_stops_before_other_batches(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(wrapper, 'execute', return_value=Mock(returncode=2)) as execute:
            self.assertEqual(wrapper.run_batches([wrapper.PYTHON, 'benchmark-runner/run.py'], [], list(range(1, 22)), Path(directory)), 2)
            execute.assert_called_once()

    def test_failed_case_keeps_nonzero_exit_and_scores(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            def execute(command, check=True):
                if command[1] == 'benchmark-runner/run.py':
                    logs = Path(command[command.index('--logs')+1])
                    logs.mkdir(parents=True)
                    (logs/'failure.jsonl').write_text('{}\n')
                    return Mock(returncode=1)
                (output/'report.json').write_text('{}')
                (output/'report.md').write_text('Failed case')
                return Mock(returncode=0)
            with patch.object(wrapper, 'execute', side_effect=execute):
                self.assertEqual(wrapper.run_batches([wrapper.PYTHON, 'benchmark-runner/run.py'], [], [1], output), 1)
            self.assertTrue((output/'scores/after-0001.json').exists())

if __name__ == '__main__':
    unittest.main()

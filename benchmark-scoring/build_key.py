"""Build evaluator-only ground truth. Never mount the output into the EHR or agent."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from pypdf import PdfReader
from rubrics import task_rubric


def normalize(text):
    return ' '.join(text.split()).casefold()


def extract_key(text, expected=500):
    parts = re.split(r'(?m)^Question (\d+) \(Source: ([^\n]+)\)\n', text)
    cases = {}
    for i in range(1, len(parts), 3):
        number, _, block = parts[i:i+3]
        start = re.search(r'(?m)^Salted:[^\n]*\n', block)
        markers = list(re.finditer(r'(?m)^Answer:', block))
        if not start or len(markers) != 1:
            raise ValueError(f'Invalid question boundaries: {number}')
        question = block[start.end():markers[0].start()]
        answer = re.fullmatch(r'\s*([A-J])\.\s+([\s\S]+?)\s*', block[markers[0].end():])
        standalone = list(re.finditer(r'(?m)^\s*([A-J])\. ', question))
        if not answer or [m[1] for m in standalone] != list('ABCDEFGHIJ'):
            raise ValueError(f'Invalid key or choices: {number}')
        options = {m[1]: ' '.join(question[m.end():standalone[j+1].start() if j<9 else len(question)].split())
                   for j,m in enumerate(standalone)}
        if normalize(options[answer[1]]) != normalize(answer[2]):
            raise ValueError(f'Key text disagrees with key label: {number}')
        # Map the independently ordered inline list by option TEXT, never by letter.
        inline_text = question[:standalone[0].start()]
        inline_text = inline_text.split('Answer Choices:', 1)[-1]
        inline_markers = list(re.finditer(r'\(([A-J])\)\s*', inline_text))
        inline = {}
        if [m[1] for m in inline_markers] == list('ABCDEFGHIJ'):
            inline = {m[1]: ' '.join(inline_text[m.end():inline_markers[j+1].start() if j<9 else len(inline_text)].split())
                      for j,m in enumerate(inline_markers)}
        pid = f'mxq-{int(number):04d}'
        if pid in cases:
            raise ValueError('Duplicate question')
        category = re.search(r'Task: ([^|\n]+)\s*\|\s*Body system: ([^\n]+)', block[:start.start()])
        cases[pid] = {'task_type': category[1].strip() if category else 'unspecified',
                      'body_system': category[2].strip() if category else 'unspecified', 'correct_choice': answer[1], 'correct_text': options[answer[1]],
                      'options': options, 'inline_options': inline,
                      'question_sha256': hashlib.sha256(question.encode()).hexdigest()}
    if list(cases) != [f'mxq-{n:04d}' for n in range(1, expected+1)]:
        raise ValueError('Missing questions or unexpected count')
    return cases


def main():
    p = argparse.ArgumentParser()
    p.add_argument('pdf', type=Path)
    p.add_argument('--output', type=Path, default=Path('evaluation-private/answer-key.json'))
    args = p.parse_args()
    cases = extract_key('\n'.join(page.extract_text() for page in PdfReader(args.pdf).pages))
    payload = {'schema_version': 1, 'source_sha256': hashlib.sha256(args.pdf.read_bytes()).hexdigest(),
               'label_convention': 'standalone', 'cases': cases}
    args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Restrictive permissions apply even when overwriting an existing file.
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write('\n')
    rubric_path = args.output.parent / 'task-rubrics.json'
    fd = os.open(rubric_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump({pid: task_rubric(pid, key) for pid, key in cases.items()}, f, indent=2)
        f.write('\n')
    print(f'Validated {len(cases)} PDF answer keys; saved evaluator-only file: {args.output}')
    print(f"Inline choice mappings available: {sum(bool(c['inline_options']) for c in cases.values())}")

if __name__ == '__main__':
    main()

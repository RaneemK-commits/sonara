"""Read-only enrollment diagnosis; audio/templates never appear in the report.

Leave-one-out results are training diagnostics, never held-out accuracy.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sonara.models.classifier import PrototypeClassifier


def diagnose(path: Path) -> dict:
    clf = PrototypeClassifier.load(path)
    rows = []
    for i, (label, seq) in enumerate(zip(clf.labels, clf.seqs)):
        scores = clf.scores(seq, exclude=i)
        ranked = sorted(scores, key=scores.get)
        own = scores.get(label)
        other = min((v for c, v in scores.items() if c != label), default=float('inf'))
        rows.append({'label': label, 'frames': len(seq), 'best': ranked[0] if ranked else None,
                     'own_distance': own, 'nearest_other_distance': other if np.isfinite(other) else None,
                     'own_separation': other-own if own is not None and np.isfinite(other) else None})
    # Pair-specific confusion tells enrollment which words need attention. These
    # are independent-template comparisons, but still enrollment diagnostics.
    confusion = {label: {other: 0 for other in clf.classes} for label in clf.classes}
    for row in rows:
        if row['best'] is not None:
            confusion[row['label']][row['best']] += 1
    confused_pairs = [
        {'intents': [a, b], 'nearest_label_errors': confusion[a][b] + confusion[b][a]}
        for index, a in enumerate(clf.classes) for b in clf.classes[index + 1:]
        if confusion[a][b] + confusion[b][a]
    ]
    confused_pairs.sort(key=lambda pair: (-pair['nearest_label_errors'], pair['intents']))
    result = {'counts': clf.counts(), 'matching': {'k': clf.k, 'band': clf.band, 'margin': clf.margin},
              'enrollment_nearest_label_confusion': confusion,
              'confused_pairs': confused_pairs,
              'global_threshold': clf.threshold, 'calibration': clf.calibration,
              'loo_nearest_intent_correct_count': sum(r['label'] == r['best'] for r in rows),
              'loo_trials': len(rows), 'rows': rows,
              'warning': 'Enrollment-only leave-one-out diagnosis, not held-out recognition accuracy. No profile changes.'}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = diagnose(args.profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False))
    print(json.dumps({k: v for k, v in report.items() if k not in ('rows', 'calibration')}, indent=2))

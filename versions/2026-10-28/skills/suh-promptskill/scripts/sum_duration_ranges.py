#!/usr/bin/env python3
"""Add established non-overlapping planned ranges; never infer performance timing."""
import argparse
from decimal import Decimal, InvalidOperation
import json


def add_ranges(values):
    if not values:
        raise ValueError('at least one min:max range is required')
    low = high = Decimal('0')
    for value in values:
        parts = value.split(':')
        if len(parts) != 2:
            raise ValueError('use min:max seconds, without units')
        try:
            start, end = map(Decimal, parts)
        except InvalidOperation as exc:
            raise ValueError('invalid decimal range') from exc
        if not (start.is_finite() and end.is_finite() and Decimal('0') <= start <= end):
            raise ValueError('ranges must be finite, nonnegative and ordered')
        low += start
        high += end
    def plain(value):
        text = format(value, 'f')
        return text.rstrip('0').rstrip('.') if '.' in text else text
    return {'min_seconds': plain(low), 'max_seconds': plain(high), 'status': 'arithmetic_only',
            'not_checked': ['overlap_or_sequence', 'performance_duration', 'media', 'source_semantics']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ranges', nargs='+')
    args = parser.parse_args()
    try:
        result = add_ranges(args.ranges)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result))


if __name__ == '__main__':
    main()

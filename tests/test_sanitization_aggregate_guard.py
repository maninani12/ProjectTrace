"""Focused regression coverage for the unchanged aggregate sanitizer budget."""

import pytest

from analyzers.sanitization import metadata

MAX_NODES = 1_000_000


@pytest.mark.parametrize(
    ("logical_nodes", "accepted"),
    [
        (MAX_NODES - 1, True),
        (MAX_NODES, True),
        (MAX_NODES + 1, False),
    ],
)
def test_metadata_enforces_aggregate_nodes_in_one_logical_value(logical_nodes, accepted):
    # The list itself is one node; each scalar child is one more node.
    value = [0] * (logical_nodes - 1)

    if accepted:
        assert metadata(value) == value
    else:
        with pytest.raises(ValueError, match="Sanitization structure budget exceeded"):
            metadata(value)

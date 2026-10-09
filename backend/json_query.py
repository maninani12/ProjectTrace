"""Constant JSON paths matching portable expression indexes.

Values remain bound. Only developer-defined path keys are rendered literally;
bound SQLite JSON paths cannot match a stored expression index.
"""
import re

from sqlalchemy import String
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.visitors import InternalTraversal


class IndexedText(ColumnElement):
    type = String()
    inherit_cache = True
    _traverse_internals = [("column", InternalTraversal.dp_clauseelement), ("path", InternalTraversal.dp_string_list)]

    def __init__(self, column, path):
        if not path or any(not re.fullmatch(r"[a-z_]+", key) for key in path):
            raise ValueError("Expected a constant JSON field path.")
        self.column, self.path = column, tuple(path)

    @property
    def _from_objects(self):
        return self.column._from_objects


@compiles(IndexedText)
def compile_indexed_text(element, compiler, **kwargs):
    expression = element.column
    for key in element.path:
        expression = expression[key]
    return compiler.process(expression.as_string(), literal_binds=True)


def indexed_text(column, *path):
    return IndexedText(column, path)

#> Backend opcode tables must not drift apart over time.
from __future__ import annotations

from sb3conv.backends.c.exprs import EXPR_METHODS as C_EXPR
from sb3conv.backends.c.stmts import STMT_METHODS as C_STMT
from sb3conv.backends.godot.exprs import EXPR_METHODS as GD_EXPR
from sb3conv.backends.godot.stmts import STMT_METHODS as GD_STMT
from sb3conv.backends.javascript.exprs import EXPR_METHODS as JS_EXPR
from sb3conv.backends.javascript.stmts import STMT_METHODS as JS_STMT
from sb3conv.backends.lua.exprs import EXPR_METHODS as LUA_EXPR
from sb3conv.backends.lua.stmts import STMT_METHODS as LUA_STMT
from sb3conv.backends.python.exprs import EXPR_METHODS as PY_EXPR
from sb3conv.backends.python.stmts import STMT_METHODS as PY_STMT

# typescript reuses the javascript emitters verbatim, so it needs no entry
_TABLES: dict[str, tuple[dict, dict]] = {
    "python": (PY_STMT, PY_EXPR),
    "javascript": (JS_STMT, JS_EXPR),
    "lua": (LUA_STMT, LUA_EXPR),
    "c": (C_STMT, C_EXPR),
    "godot": (GD_STMT, GD_EXPR),
}


def test_opcode_tables_stay_in_sync():
    """A block supported anywhere must be supported (or knowingly absent) everywhere.

    The emitters are near-copies by design; this test turns silent drift
    (one backend gains a block the others never got) into a loud failure.
    """
    all_stmt = set().union(*(stmt for stmt, _ in _TABLES.values()))
    all_expr = set().union(*(expr for _, expr in _TABLES.values()))
    assert len(all_stmt) > 50 and len(all_expr) > 30  # sanity: tables loaded

    for name, (stmt, expr) in sorted(_TABLES.items()):
        missing_stmt = sorted(all_stmt - set(stmt))
        missing_expr = sorted(all_expr - set(expr))
        assert not missing_stmt, f"{name} is missing statements: {missing_stmt}"
        assert not missing_expr, f"{name} is missing reporters: {missing_expr}"

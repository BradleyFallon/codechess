# ChessFlow

ChessFlow keeps application-owned chess pieces and opening-flow rules while
delegating board state and move legality to
[`python-chess`](https://python-chess.readthedocs.io/).

```text
python-chess Board  -> legal state, attacks, pins, check, FEN, push/pop
FlowBoard           -> persistent piece identities and relationships
FlowDefinition      -> flags, conditions, actions, and immutable rules
FlowRuntime         -> activation, expiry, execution, and candidates
FlowRunner          -> source-order selection with ambiguity reporting
```

## Flow schema

Rules mirror the domain model directly:

```text
flow: small-london
version: 0.1
side: white

flags:
    center-claimed

conditions:
    d-played = played(d.develop.d4)

d:
    develop.d4:
        set: center-claimed
        why: claim the center

bq:
    develop.f4:
        when: d-played
        if: center-claimed
        why: develop outside the pawn chain
```

See [`examples/vertical-slice.flow`](examples/vertical-slice.flow) for an
executable four-move slice.

## Running it

```python
from pathlib import Path

from chessflow import FlowBoard, FlowRuntime, parse_flow
from chessflow.simulation import FlowRunner

board = FlowBoard()
definition = parse_flow(Path("examples/vertical-slice.flow").read_text())
runner = FlowRunner(FlowRuntime(definition, board), board)

report = runner.play_flow_turn()
print(report.selected.move.uci())  # d2d4
```

Install and test with:

```shell
python -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

When initialized from a raw FEN, `FlowBoard` infers the most likely standard
piece identities. Since FEN has no history, exact `move_count` values require a
`python-chess.Board` that retains its move stack.


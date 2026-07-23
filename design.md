# Chess Rule Language — Proposed Version 0.1

## Design principle

The executable guide should resemble the notes a player would memorize:

```text
d4 first
Bf4 after d4
e3 after Bf4
Nf3 after e3
c3 after Nf3

But:
- play c4 against an early ...Bf5
- play Nc3 and e4 against a kingside fianchetto
- play d5 against an immediate ...c5
```

The language should express exactly that level of reasoning.

It should not attempt to encode every tactical fact directly in the guide. Complex board recognition belongs in named conditions defined by the template.

---

# 1. The two files

## File 1: `accelerated_london.template`

The template defines:

* The condition vocabulary available to the guide
* Which conditions are calculated directly from the board
* Which conditions require a higher-level evaluator
* Strategic state names the guide may set
* Standard piece codes

It does **not** define move order.

## File 2: `accelerated_london.guide`

The guide defines:

* Moves
* Dependencies between moves
* Conditions under which moves apply
* Strategic states established by moves
* Human explanations
* Successful terminal points

It does **not** contain raw board queries such as `at(black.bq,f5)`.

This keeps the guide readable.

---

# 2. Execution model

On each White turn, the compiler performs these steps:

1. Find every unplayed rule whose `after` dependencies are satisfied.
2. Evaluate its `if` expression.
3. Check whether the move is legal.
4. Count the remaining candidates.

The result is:

```text
0 candidates:
    dead end

1 candidate:
    play that move

2 or more candidates:
    ambiguity

terminal rule reached:
    successful end of this guide branch
```

There are no implicit fallbacks.

There are no numeric priorities in version 0.1.

If two rules apply, the guide is ambiguous and the report should expose that. The author must improve the conditions rather than rely on hidden selection behavior.

---

# 3. Piece codes

The piece codes are fixed by the language:

```text
a   a-pawn
b   b-pawn
c   c-pawn
d   d-pawn
e   e-pawn
f   f-pawn
g   g-pawn
h   h-pawn

nq  queenside knight
nk  kingside knight

bq  queenside bishop
bk  kingside bishop

rq  queenside rook
rk  kingside rook

q   queen
k   king
```

Move references use:

```text
<piece>.<move-id>
```

Examples:

```text
d.d4
bq.Bf4
e.e3
nk.Nf3
c.c3
nq.Nd2
k.O-O
```

References should identify a move, not merely a piece.

Use:

```text
after:nk.Nf3
```

rather than:

```text
after:nk
```

The latter becomes ambiguous as soon as the knight has multiple possible moves.

---

# 4. Guide rule syntax

A move rule has this shape:

```text
piece:
    move-id{
        notation:SAN
        after:move-reference
        if:boolean-expression
        set:state-name
        why:human explanation
        terminal:terminal-name
    }
```

Only `notation` is required when the move ID is different from the displayed notation.

For ordinary development moves, the move ID may also serve as the notation:

```text
nk:
    Nf3{
        after:e.e3
        why:defend d4 and control e5
    }
```

---

# 5. Supported rule fields

## `open`

Marks the initial move of the guide.

```text
d:
    d4{
        open
    }
```

A guide must have exactly one applicable opening rule for its starting position.

---

## `after`

Defines a direct move dependency.

```text
e:
    e3{
        after:bq.Bf4
    }
```

This means:

```text
e3 is available only after Bf4 has been played.
```

The viewer infers:

```text
Bf4 before e3
```

The source language does not support a `before` field.

### Multiple dependencies

Multiple dependencies are separated by commas:

```text
k:
    O-O{
        after:nk.Nf3,bk.Bd3
    }
```

All listed dependencies are required.

### Minimal dependencies only

Authors should list only immediate dependencies.

Given:

```text
bq.Bf4 -> e.e3 -> nk.Nf3
```

this is redundant:

```text
nk:
    Nf3{
        after:bq.Bf4,e.e3
    }
```

The correct rule is:

```text
nk:
    Nf3{
        after:e.e3
    }
```

The compiler should detect transitive redundancy and report it.

---

## `if`

Defines when the rule applies.

```text
if:traditional-center
```

Boolean logic is supported:

```text
if:black-bishop-f5 || black-slav-center
```

```text
if:castle-queenside && center-closed
```

```text
if:black-fianchetto && !black-pawn-d5
```

```text
if:(black-bishop-f5 || black-slav-center) &&
   !b2-under-pressure
```

### Operators

```text
!       NOT
&&      AND
||      OR
()      grouping
```

### Precedence

```text
1. ()
2. !
3. &&
4. ||
```

Therefore:

```text
a || b && c
```

means:

```text
a || (b && c)
```

Parentheses should still be used whenever both `&&` and `||` appear in one expression.

---

## `set`

Sets a permanent guide state after the move is played.

```text
c:
    c4{
        if:active-c4-trigger
        set:active-c4
    }
```

Later rules can use that state:

```text
nq:
    Nc3{
        after:c.c4
        if:active-c4
    }
```

States are monotonic in version 0.1:

* They begin false.
* A move may set them true.
* They cannot be cleared.

This works well for opening choices such as:

```text
traditional
active-c4
benoni
castle-kingside
castle-queenside
plan-e4
plan-Ne5
kingside-attack
queenside-play
```

These choices normally do not reverse during development.

---

## `why`

Contains the human reason for the move.

```text
why:defend d4 and prepare e4
```

The compiler ignores it during rule evaluation.

The viewer uses it to generate the learning guide.

The explanation should be concise enough to memorize.

---

## `terminal`

Marks a successful stopping point.

```text
k:
    O-O{
        after:nk.Nf3,bk.Bd3
        terminal:development-complete
    }
```

Without `terminal`, running out of rules is a dead end.

A terminal does not mean that the chess game is over. It means that the current guide has reached its intended boundary.

Possible terminal names include:

```text
development-complete
enter-benoni-module
enter-englund-module
middlegame-reached
theory-complete
```

---

## `notation`

Used when the internal move ID differs from its displayed SAN.

This matters when the same notation can describe different pawn moves.

```text
c:
    c4-direct{
        notation:c4
    }

    c4-break{
        notation:c4
    }
```

The compiler distinguishes:

```text
c.c4-direct
c.c4-break
```

while the viewer displays both as:

```text
c4
```

For the first prototype, most move IDs can simply be their notation.

---

# 6. Template file syntax

The template has three important sections:

```text
states{
}

signals{
}

conditions{
}
```

---

# 7. States

States are strategic choices established by the guide.

```text
states{
    traditional
    active-c4
    benoni

    castle-kingside
    castle-queenside

    plan-e4
    plan-Ne5

    kingside-attack
    queenside-play
}
```

Every name used by `set` must be declared here.

Every state may also be used in an `if` expression.

Unknown state names are compiler errors.

---

# 8. Signals

Signals represent concepts that are useful to a human but not yet precisely defined by the basic board predicates.

```text
signals{
    center-closed
    center-stable

    e4-ready
    Ne5-safe
    Nb5-safe

    bishop-trap-threat

    king-safe-kingside
    king-safe-queenside
}
```

A signal may eventually be supplied by:

* A simple position classifier
* An engine-assisted evaluator
* A manually annotated test position
* A more advanced tactical analyzer

For version 0.1, it is acceptable for some signals to remain unsupported during fully automatic testing. The compiler should report:

```text
unknown signal value
```

rather than silently treating the signal as false.

---

# 9. Primitive board predicates

Raw board predicates are permitted in the template, but not in the guide.

## Piece location

```text
at(piece,square)
```

Examples:

```text
at(black.bq,f5)
at(black.q,b6)
at(black.c,c5)
```

---

## Initial-square state

```text
unmoved(piece)
moved(piece)
```

Examples:

```text
unmoved(black.d)
moved(nk)
```

---

## Move history

```text
played(move-reference)
```

Examples:

```text
played(bq.Bf4)
played(k.O-O)
```

For opponent moves, the compiler may use normalized move references:

```text
played(black.c.c5)
played(black.q.Qb6)
```

---

## Current legality

```text
legal(move-reference)
```

Example:

```text
legal(nq.Nb5)
```

Legality is automatically checked for candidate rules, so it should rarely be necessary inside a named condition.

---

## Attack state

```text
attacked(target,side)
defended(target,side)
```

Examples:

```text
attacked(b2,black)
attacked(d4,black)
defended(d4,white)
```

Targets may initially be limited to squares.

---

## Castling

```text
can-castle(side)
castled(side)
```

Examples:

```text
can-castle(kingside)
can-castle(queenside)

castled(black,kingside)
castled(white,queenside)
```

---

## Captures

```text
captured(piece)
```

Example:

```text
captured(bq)
```

This will eventually help the compiler avoid recommending plans that depend on a missing piece.

---

# 10. Named conditions

The template converts raw board facts into memorable condition names.

Example:

```text
conditions{
    black-pawn-d5 =
        at(black.d,d5)

    black-pawn-c5 =
        at(black.c,c5)

    black-c5-before-d5 =
        black-pawn-c5 &&
        unmoved(black.d)

    black-bishop-f5 =
        at(black.bq,f5)

    black-bishop-g4 =
        at(black.bq,g4)

    black-queen-b6 =
        at(black.q,b6)

    black-knight-c6 =
        at(black.nq,c6)

    black-pawn-c6 =
        at(black.c,c6)

    black-pawn-g6 =
        at(black.g,g6)

    black-bishop-g7 =
        at(black.bk,g7)

    black-fianchetto =
        black-pawn-g6 &&
        black-bishop-g7

    black-slav-center =
        black-pawn-c6 &&
        black-pawn-d5

    b2-under-pressure =
        attacked(b2,black)

    d4-under-pressure =
        attacked(d4,black) &&
        !defended(d4,white)

    active-c4-trigger =
        black-bishop-f5 ||
        black-slav-center

    traditional-center =
        black-pawn-d5 &&
        !active-c4-trigger &&
        !black-fianchetto

    early-benoni =
        black-c5-before-d5

    early-dutch =
        at(black.f,f5)

    englund =
        at(black.e,e5) &&
        at(white.d,d4)

    early-slav =
        black-pawn-c6 &&
        unmoved(black.d)

    standard-accelerated-start =
        !(early-benoni ||
          early-dutch ||
          early-slav ||
          englund)
}
```

The guide only needs to remember names such as:

```text
traditional-center
active-c4-trigger
black-fianchetto
early-benoni
```

The board-level implementation remains in the template.

---

# 11. Proposed template file

```text
template accelerated-london
version 0.1
side white

states{
    traditional
    active-c4
    benoni

    castle-kingside
    castle-queenside

    plan-e4
    plan-Ne5

    kingside-attack
    queenside-play
}

signals{
    center-closed
    center-stable

    e4-ready
    Ne5-safe
    Nb5-safe

    bishop-trap-threat

    king-safe-kingside
    king-safe-queenside
}

conditions{
    black-pawn-d5 =
        at(black.d,d5)

    black-pawn-c5 =
        at(black.c,c5)

    black-pawn-c6 =
        at(black.c,c6)

    black-pawn-g6 =
        at(black.g,g6)

    black-c5-before-d5 =
        black-pawn-c5 &&
        unmoved(black.d)

    black-bishop-f5 =
        at(black.bq,f5)

    black-bishop-g4 =
        at(black.bq,g4)

    black-bishop-g7 =
        at(black.bk,g7)

    black-queen-b6 =
        at(black.q,b6)

    black-knight-c6 =
        at(black.nq,c6)

    black-fianchetto =
        black-pawn-g6 &&
        black-bishop-g7

    black-slav-center =
        black-pawn-c6 &&
        black-pawn-d5

    b2-under-pressure =
        attacked(b2,black)

    d4-under-pressure =
        attacked(d4,black) &&
        !defended(d4,white)

    active-c4-trigger =
        black-bishop-f5 ||
        black-slav-center

    traditional-center =
        black-pawn-d5 &&
        !active-c4-trigger &&
        !black-fianchetto

    early-benoni =
        black-c5-before-d5

    early-dutch =
        at(black.f,f5)

    early-slav =
        black-pawn-c6 &&
        unmoved(black.d)

    englund =
        at(black.e,e5) &&
        at(white.d,d4)

    standard-accelerated-start =
        !(early-benoni ||
          early-dutch ||
          early-slav ||
          englund)
}
```

---

# 12. Proposed guide file

This example intentionally covers only the beginnings of several branches. It demonstrates the language rather than claiming to be a completed repertoire.

```text
guide accelerated-london
version 0.1
use accelerated_london.template

# PAWNS

a:

b:

c:
    c3{
        after:nk.Nf3
        if:traditional-center
        set:traditional,plan-e4,plan-Ne5
        why:defend d4 and complete the pawn pyramid
    }

    c4{
        after:e.e3
        if:active-c4-trigger
        set:active-c4,queenside-play
        why:challenge d5 and prepare pressure on b7
    }

d:
    d4{
        open
        why:claim the center and open the queenside bishop
    }

    d5{
        after:d.d4
        if:early-benoni
        set:benoni
        why:gain space instead of allowing an easy exchange on d4
        terminal:enter-benoni-module
    }

    dxe5{
        after:d.d4
        if:englund
        why:accept the Englund pawn
        terminal:enter-englund-module
    }

e:
    e3{
        after:bq.Bf4
        if:traditional-center || active-c4-trigger
        why:defend d4 and open the kingside bishop
    }

    e4{
        after:nq.Nc3
        if:black-fianchetto && !black-pawn-d5
        set:castle-queenside,kingside-attack
        why:take the full center before Black establishes d5
    }

f:

g:

h:
    h3{
        after:nk.Nf3
        if:black-bishop-g4 || bishop-trap-threat
        why:protect the London bishop and prevent a pin
    }


# BISHOPS

bq:
    Bf4{
        after:d.d4
        if:standard-accelerated-start
        why:develop outside the pawn chain and control e5
    }

    Bg3{
        after:bq.Bf4
        if:bishop-trap-threat
        why:preserve the London bishop
    }

bk:
    Bd3{
        after:c.c3
        if:traditional
        why:support e4 and aim at h7
    }

    Be2{
        after:nk.Nf3
        if:active-c4 || castle-queenside
        why:develop safely without obstructing the attack
    }


# KNIGHTS

nq:
    Nd2{
        after:c.c3
        if:traditional
        why:support e4 while leaving the c-pawn structure intact
    }

    Nc3{
        after:c.c4
        if:active-c4
        why:increase pressure on d5
    }

    Nc3-fianchetto{
        notation:Nc3
        after:bq.Bf4
        if:black-fianchetto && !black-pawn-d5
        why:prepare e4
    }

nk:
    Nf3{
        after:e.e3
        if:traditional-center || active-c4-trigger
        why:defend d4 and control e5
    }

    Ne5{
        after:nk.Nf3
        if:traditional && Ne5-safe
        why:occupy the main London outpost
    }


# QUEEN

q:
    Qb3{
        after:nq.Nc3
        if:active-c4
        why:attack b7 and add pressure to d5
    }

    Qd2{
        after:e.e4
        if:castle-queenside
        why:prepare long castling and a kingside attack
    }


# KING

k:
    O-O{
        after:nk.Nf3,bk.Bd3
        if:traditional && king-safe-kingside
        set:castle-kingside
        terminal:development-complete
        why:secure the king before beginning the middlegame plan
    }

    O-O-active{
        notation:O-O
        after:nk.Nf3,bk.Be2
        if:active-c4 && king-safe-kingside
        set:castle-kingside
        terminal:development-complete
        why:secure the king and prepare queenside play
    }

    O-O-O{
        after:q.Qd2,bk.Be2
        if:castle-queenside && king-safe-queenside
        terminal:development-complete
        why:place the king away from the intended kingside pawn attack
    }


# ROOKS

rq:

rk:
```

---

# 13. Duplicate notation versus duplicate rules

The guide may need more than one rule that produces the same chess notation.

For example:

```text
nq:
    Nc3-c4{
        notation:Nc3
        after:c.c4
        if:active-c4
    }

    Nc3-fianchetto{
        notation:Nc3
        after:bq.Bf4
        if:black-fianchetto
    }
```

These are separate rules because:

* Their dependencies differ.
* Their conditions differ.
* Their explanations differ.
* They represent different human reasons for playing the same move.

The move IDs must be unique, but the displayed notation may match.

This is not undesirable duplication. It represents distinct rules that happen to choose the same move.

---

# 14. What should not be included in version 0.1

To preserve elegance, the initial language should not include:

```text
Numeric priorities
Engine evaluation thresholds
Loops
Variables containing numbers
Functions written inside the guide
Else branches
Implicit fallback rules
Mutable states
Automatic tactical sacrifices
Search depth directives
Move scoring
Probabilities
Opponent-style assumptions
Time-control logic
```

The guide should answer:

```text
What move do I play?
What must already have happened?
Under what recognizable condition?
What plan does the move establish?
Why should I remember it?
```

Everything else belongs in the compiler, evaluator, or generated report.

---

# 15. Validation rules

The compiler should fail loudly for:

```text
Unknown move references
Unknown condition names
Unknown state names
Duplicate rule IDs
Illegal candidate moves
Circular after dependencies
Redundant transitive after dependencies
States used but never declared
States declared but never set
Terminal names duplicated unintentionally
Boolean syntax errors
```

The compiler should distinguish these runtime outcomes:

```text
dead-end:no-rule-ready

dead-end:conditions-false

dead-end:applicable-rules-illegal

ambiguity:multiple-rules-ready

success:terminal-reached
```

This detail will make later reports much more useful.

---

# 16. Human-complexity principle

The language should make the human cost of a guide measurable.

Useful future metrics include:

```text
Total number of rules
Number of named conditions
Maximum conditions in one rule
Maximum Boolean nesting depth
Number of strategic states
Maximum development depth
Number of ambiguity points
Number of dead-end points
Number of distinct responses to one Black setup
```

A guide with slightly weaker engine performance may still be superior for rapid chess when it has:

* Fewer rules
* Shorter conditions
* Fewer branches
* More repeated structures
* Clearer reasons
* Fewer ambiguous positions

The language should expose this tradeoff rather than optimizing automatically for engine evaluation.

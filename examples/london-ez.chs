flow beginner-accelerated-london
version 0.1
side white

# LANGUAGE REFERENCE
#
# Boolean operators:
#   !   not
#   &&  and
#   ||  or
#
# Rule fields:
#   open
#   after
#   if
#   set
#   why
#   terminal
#
# These are comments only. They do not define language features.


states{
    traditional
    active-c4
    broad-center
    benoni
    b2-safe
}


conditions{
    black-pawn-d5 =
        at(black.d,d5)

    black-pawn-c5 =
        at(black.c,c5)

    black-bishop-f5 =
        at(black.bq,f5)

    black-queen-b6 =
        at(black.q,b6)

    black-fianchetto =
        at(black.g,g6) ||
        at(black.bk,g7)

    early-benoni =
        black-pawn-c5 &&
        unmoved(black.d)

    active-c4-trigger =
        black-pawn-d5 &&
        black-bishop-f5

    b2-under-pressure =
        black-queen-b6 &&
        attacked(b2,black)
}


# PAWNS

c:
    c3{
        when:after.nk.Nf3
        if:traditional

        why:complete the London pawn triangle
    }

    c4{
        after:bq.Bf4
        if:active-c4-trigger

        set:active-c4

        why:challenge d5 after Black develops the bishop early
    }

d:
    d4{
        when:open

        why:claim the center
    }

    d5{
        after:d.d4
        if:early-benoni

        set:benoni

        why:gain space against an immediate c5
    }

e:
    e3{
        after:bq.Bf4
        if:!active-c4-trigger && !early-benoni

        set:traditional

        why:defend d4 and open the kingside bishop
    }


# BISHOPS

bq:
    Bf4{
        after:d.d4
        if:!early-benoni

        why:develop outside the pawn chain
    }


# KNIGHTS

nk:
    Nf3{
        after:e.e3
        if:traditional

        why:defend d4 and control e5
    }


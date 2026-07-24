from __future__ import annotations

import chess

from chessflow.flow_language.ast import FlowDefinition
from chessflow.flow_runtime import (
    Candidate,
    GoalDeadEndError,
    GoalRuntime,
    GoalStatus,
)
from chessflow.learning.model import (
    GoalEventKind,
    GoalEventView,
    GoalView,
    LearnPhase,
    LearnView,
    MoveFeedbackKind,
    MoveFeedbackView,
    MoveView,
    RuleLessonView,
    TerminalExitView,
)
from chessflow.quiz import expand_lines
from chessflow.reporting import format_san_path
from chessflow.repertoire import RepertoireNode
from chessflow.session import FlowSession


class LearnSessionError(RuntimeError):
    pass


_GENERIC_TERMINAL_EXPLANATION = (
    "Opening preparation ends here. Continue the game from this position."
)


class LearnSession:
    def __init__(
        self,
        definition: FlowDefinition,
        repertoire: RepertoireNode,
    ) -> None:
        self.definition = definition
        self.repertoire = repertoire
        self.lines = tuple(expand_lines(repertoire))
        self.line_index = 0
        self.node_index = 0
        self.flow_session = FlowSession.fresh(definition)
        self.path_san: tuple[str, ...] = ()
        self.question_number = 0
        self.question_total = 0
        self.seen_rule_keys: set[str] = set()
        self.new_rules: list[RuleLessonView] = []
        self.review_count = 0
        self.phase = LearnPhase.AWAITING_MOVE
        self.feedback: MoveFeedbackView | None = None
        self.terminal: TerminalExitView | None = None
        self.current_goal_key: str | None = None
        self.fallback_goal_key: str | None = None
        self.goal_statuses: dict[str, GoalStatus] = {}
        self.goal_events: tuple[GoalEventView, ...] = ()
        self._candidate: Candidate | None = None
        self._expected_move: MoveView | None = None
        self._reference_node: RepertoireNode | None = None
        self._coach: tuple[str, ...] = ()
        self._had_incorrect_answer = False
        self._seen_rules_at_line_start: set[str] = set()

    @classmethod
    def start(
        cls,
        definition: FlowDefinition,
        repertoire: RepertoireNode,
    ) -> LearnSession:
        session = cls(definition, repertoire)
        if session.flow_session.board.fen != repertoire.fen:
            raise LearnSessionError(
                "Flow and repertoire must begin from the same position"
            )
        session._validate_lines()
        session._start_line(0)
        return session

    def view(self) -> LearnView:
        board = self.flow_session.board.chess_board
        legal_moves = (
            tuple(self._move_view(move) for move in board.legal_moves)
            if self.phase is LearnPhase.AWAITING_MOVE
            else ()
        )
        return LearnView(
            phase=self.phase,
            fen=self.flow_session.board.fen,
            path_san=self.path_san,
            line_number=min(self.line_index + 1, len(self.lines)),
            line_total=len(self.lines),
            question_number=self.question_number,
            question_total=self.question_total,
            current_goal=self._goal_view(
                self.flow_session.runtime.current_goal(
                    self.flow_session.board
                )
            ),
            fallback_goal=self._goal_view(
                self.flow_session.runtime.fallback_goal(
                    self.flow_session.board
                )
            ),
            goal_events=self.goal_events,
            coach=self._coach,
            legal_moves=legal_moves,
            expected_move=self._expected_move,
            feedback=self.feedback,
            terminal=self.terminal,
            new_rules=tuple(self.new_rules),
            review_count=self.review_count,
            rules_seen=len(self.seen_rule_keys),
        )

    def submit_san(self, san: str) -> LearnView:
        self._require_phase(LearnPhase.AWAITING_MOVE, "submit SAN")
        entered = san.strip()
        try:
            move = self.flow_session.board.chess_board.parse_san(entered)
        except ValueError:
            self._record_incorrect_feedback(
                MoveFeedbackKind.INVALID_SAN,
                entered,
            )
            return self.view()
        return self._submit_legal_move(move, entered)

    def submit_move(self, move: chess.Move) -> LearnView:
        self._require_phase(LearnPhase.AWAITING_MOVE, "submit a move")
        board = self.flow_session.board.chess_board
        if move not in board.legal_moves:
            raise LearnSessionError(f"Illegal move: {move.uci()}")
        return self._submit_legal_move(move, board.san(move))

    def continue_(self) -> LearnView:
        if self.phase is LearnPhase.AWAITING_MOVE:
            raise LearnSessionError(
                "Cannot continue while awaiting a move"
            )
        if self.phase is LearnPhase.COURSE_COMPLETE:
            raise LearnSessionError("Course is already complete")
        if self.phase is LearnPhase.SHOWING_FEEDBACK:
            self.feedback = None
            self.goal_events = ()
            self._coach = ()
            self._candidate = None
            self._expected_move = None
            self._reference_node = None
            if self.node_index >= len(self._current_line):
                self.phase = LearnPhase.LINE_COMPLETE
            else:
                self._prepare_question_or_complete()
            return self.view()

        if self.line_index + 1 >= len(self.lines):
            self.phase = LearnPhase.COURSE_COMPLETE
            self.goal_events = ()
            self._coach = ()
            return self.view()
        self._start_line(self.line_index + 1)
        return self.view()

    def restart_line(self) -> LearnView:
        if self.phase is LearnPhase.COURSE_COMPLETE:
            raise LearnSessionError(
                "Cannot restart a line after course completion"
            )
        self.seen_rule_keys = set(self._seen_rules_at_line_start)
        self._start_line(self.line_index)
        return self.view()

    def restart_course(self) -> LearnView:
        self.seen_rule_keys.clear()
        self._start_line(0)
        return self.view()

    @property
    def _current_line(self) -> tuple[RepertoireNode, ...]:
        return self.lines[self.line_index]

    def _validate_lines(self) -> None:
        learnable = tuple(
            self._line_has_flow_move(line) for line in self.lines
        )
        if not learnable or not any(learnable):
            raise LearnSessionError(
                "Repertoire contains no learnable lines"
            )
        for line_number, has_flow_move in enumerate(
            learnable,
            start=1,
        ):
            if not has_flow_move:
                raise LearnSessionError(
                    f"Repertoire line {line_number} contains no "
                    "decision for the flow side"
                )

    def _line_has_flow_move(
        self,
        line: tuple[RepertoireNode, ...],
    ) -> bool:
        board = chess.Board(self.repertoire.fen)
        for node in line:
            if board.turn == self.definition.side.chess_color:
                return True
            assert node.move is not None
            board.push(node.move)
        return False

    def _start_line(self, line_index: int) -> None:
        self.line_index = line_index
        self.node_index = 0
        self.flow_session = FlowSession.fresh(self.definition)
        self.path_san = ()
        self.question_number = 0
        self.question_total = (len(self._current_line) + 1) // 2
        self.new_rules = []
        self.review_count = 0
        self.feedback = None
        self.terminal = None
        self.goal_events = ()
        self._candidate = None
        self._expected_move = None
        self._reference_node = None
        self._coach = ()
        self._had_incorrect_answer = False
        self._seen_rules_at_line_start = set(self.seen_rule_keys)
        self._capture_initial_goal_state()
        self._prepare_question_or_complete()

    def _prepare_question_or_complete(self) -> None:
        while self.node_index < len(self._current_line):
            node = self._current_line[self.node_index]
            if (
                self.flow_session.board.chess_board.turn
                != self.definition.side.chess_color
            ):
                assert node.move is not None
                assert node.san is not None
                self.flow_session.runtime.push_opponent(
                    node.move,
                    self.flow_session.board,
                )
                self.path_san = (*self.path_san, node.san)
                self.node_index += 1
                continue
            self._prepare_question(node)
            return
        self.phase = LearnPhase.LINE_COMPLETE
        self._candidate = None
        self._expected_move = None
        self._reference_node = None
        self._coach = ()

    def _prepare_question(self, node: RepertoireNode) -> None:
        position = format_san_path(self.path_san)
        try:
            candidates = self.flow_session.runtime.evaluate_turn(
                self.flow_session.board
            )
        except GoalDeadEndError as exc:
            raise LearnSessionError(str(exc.at_path(position))) from exc
        if not candidates:
            raise LearnSessionError(f"Flow dead end at {position}")
        if len(candidates) > 1:
            actions = ", ".join(
                candidate.rule.definition.action.canonical_key
                for candidate in candidates
            )
            raise LearnSessionError(
                f"Flow ambiguity at {position}: {actions}"
            )
        selected = candidates[0]
        if selected.move != node.move:
            selected_san = self.flow_session.board.chess_board.san(
                selected.move
            )
            raise LearnSessionError(
                f"Flow disagreement at {position}: "
                f"expected {node.san}, selected {selected_san}"
            )

        self.question_number += 1
        if selected.rule.definition.terminal is not None:
            self.question_total = self.question_number
        self._candidate = selected
        self._expected_move = self._move_view(selected.move)
        self._reference_node = node
        self._had_incorrect_answer = False
        self.feedback = None
        self.terminal = None
        self.phase = LearnPhase.AWAITING_MOVE
        self._coach = self._question_coach()
        self._update_goal_events()

    def _submit_legal_move(
        self,
        move: chess.Move,
        entered: str,
    ) -> LearnView:
        assert self._candidate is not None
        if move != self._candidate.move:
            self._record_incorrect_feedback(
                MoveFeedbackKind.INCORRECT,
                entered,
            )
            return self.view()

        candidate = self._candidate
        reference = self._reference_node
        assert reference is not None
        rule = candidate.rule.definition
        rule_key = rule.action.canonical_key
        is_new_rule = rule_key not in self.seen_rule_keys
        if is_new_rule:
            self.seen_rule_keys.add(rule_key)
            self.new_rules.append(
                RuleLessonView(rule_key, rule.why)
            )
        else:
            self.review_count += 1

        expected = self._move_view(candidate.move)
        explanation: tuple[str, ...]
        if self._had_incorrect_answer:
            explanation = ()
        elif rule.terminal is not None:
            explanation = self._distinct_text(reference.comment)
        else:
            explanation = self._distinct_text(
                rule.why,
                reference.comment,
            )
        self.flow_session.runtime.execute(
            candidate,
            self.flow_session.board,
        )
        assert reference.san is not None
        self.path_san = (*self.path_san, reference.san)
        self.node_index += 1
        if self.flow_session.runtime.is_terminal:
            self.node_index = len(self._current_line)
            terminal_key = self.flow_session.runtime.reached_terminals[-1]
            self.terminal = TerminalExitView(
                terminal_key,
                rule.why or _GENERIC_TERMINAL_EXPLANATION,
            )
        self.feedback = MoveFeedbackView(
            kind=MoveFeedbackKind.CORRECT,
            entered=entered,
            expected=expected,
            rule_key=rule_key,
            explanation=explanation,
            is_new_rule=is_new_rule,
            was_correction=self._had_incorrect_answer,
        )
        self.phase = LearnPhase.SHOWING_FEEDBACK
        self._coach = ()
        self._update_goal_events()
        return self.view()

    def _record_incorrect_feedback(
        self,
        kind: MoveFeedbackKind,
        entered: str | None,
    ) -> None:
        assert self._candidate is not None
        reference = self._reference_node
        assert reference is not None
        rule = self._candidate.rule.definition
        self._had_incorrect_answer = True
        self.feedback = MoveFeedbackView(
            kind=kind,
            entered=entered,
            expected=self._move_view(self._candidate.move),
            rule_key=rule.action.canonical_key,
            explanation=self._distinct_text(
                rule.why,
                reference.comment,
            ),
            is_new_rule=(
                rule.action.canonical_key not in self.seen_rule_keys
            ),
            was_correction=False,
        )

    def _question_coach(self) -> tuple[str, ...]:
        if self.node_index:
            return self._distinct_text(
                self._current_line[self.node_index - 1].comment
            )
        if self.line_index == 0:
            return self._distinct_text(self.repertoire.comment)
        return ()

    def _capture_initial_goal_state(self) -> None:
        runtime = self.flow_session.runtime
        current = runtime.current_goal(self.flow_session.board)
        fallback = runtime.fallback_goal(self.flow_session.board)
        self.current_goal_key = self._goal_key(current)
        self.fallback_goal_key = self._goal_key(fallback)
        self.goal_statuses = {
            goal.key: runtime.goal_status(goal.key)
            for goal in self.definition.goals
        }

    def _update_goal_events(self) -> None:
        runtime = self.flow_session.runtime
        current = runtime.current_goal(self.flow_session.board)
        fallback = runtime.fallback_goal(self.flow_session.board)
        current_key = self._goal_key(current)
        fallback_key = self._goal_key(fallback)
        statuses = {
            goal.key: runtime.goal_status(goal.key)
            for goal in self.definition.goals
        }
        event: GoalEventView | None = None
        previous = self._goal_view_by_key(self.current_goal_key)
        if current_key != self.current_goal_key:
            previous_status = (
                None
                if self.current_goal_key is None
                else statuses[self.current_goal_key]
            )
            if previous_status is GoalStatus.COMPLETED:
                kind = GoalEventKind.GOAL_COMPLETE
                reason = None
            elif previous_status is GoalStatus.RETIRED:
                kind = GoalEventKind.GOAL_RETIRED
                reason = (
                    None
                    if previous is None
                    else next(
                        goal.abandoned
                        for goal in self.definition.goals
                        if goal.key == previous.key
                    )
                )
            else:
                kind = GoalEventKind.NEW_GOAL
                reason = None
            event = GoalEventView(
                kind=kind,
                goal=self._goal_view(current),
                previous_goal=previous,
                fallback=self._goal_view(fallback),
                reason=reason,
            )
        elif fallback_key != self.fallback_goal_key:
            event = GoalEventView(
                kind=GoalEventKind.FALLBACK_UPDATED,
                goal=self._goal_view(current),
                previous_goal=previous,
                fallback=self._goal_view(fallback),
                reason=None,
            )
        self.current_goal_key = current_key
        self.fallback_goal_key = fallback_key
        self.goal_statuses = statuses
        self.goal_events = () if event is None else (event,)

    def _goal_view_by_key(self, key: str | None) -> GoalView | None:
        if key is None:
            return None
        definition = next(
            goal for goal in self.definition.goals if goal.key == key
        )
        return GoalView(
            key=definition.key,
            title=definition.title,
            plan=definition.plan,
        )

    def _move_view(self, move: chess.Move) -> MoveView:
        board = self.flow_session.board.chess_board
        return MoveView(
            uci=move.uci(),
            san=board.san(move),
            from_square=chess.square_name(move.from_square),
            to_square=chess.square_name(move.to_square),
            promotion=(
                None
                if move.promotion is None
                else chess.piece_symbol(move.promotion)
            ),
        )

    @staticmethod
    def _goal_view(goal: GoalRuntime | None) -> GoalView | None:
        if goal is None:
            return None
        return GoalView(
            key=goal.definition.key,
            title=goal.definition.title,
            plan=goal.definition.plan,
        )

    @staticmethod
    def _goal_key(goal: GoalRuntime | None) -> str | None:
        return None if goal is None else goal.definition.key

    @staticmethod
    def _distinct_text(*values: str | None) -> tuple[str, ...]:
        result: list[str] = []
        for value in values:
            if value is None:
                continue
            normalized = " ".join(value.split())
            if normalized and normalized not in result:
                result.append(normalized)
        return tuple(result)

    def _require_phase(
        self,
        phase: LearnPhase,
        action: str,
    ) -> None:
        if self.phase is LearnPhase.COURSE_COMPLETE:
            raise LearnSessionError(
                f"Cannot {action}; course is already complete"
            )
        if self.phase is not phase:
            raise LearnSessionError(
                f"Cannot {action} during {self.phase.value}"
            )

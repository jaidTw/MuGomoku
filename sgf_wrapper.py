'''
Code to extract a series of positions + their next moves from an SGF.

Most of the complexity here is dealing with two features of SGF:
- Stones can be added via "play move" or "add move", the latter being used
  to configure L+D puzzles, but also for initial handicap placement.
- Plays don't necessarily alternate colors; they can be repeated B or W moves
  This feature is used to handle free handicap placement.
'''
from collections import namedtuple
import numpy as np

import gomoku
from gomoku import Position
from utils import parse_sgf_coords as pc
import sgf

class GameMetadata(namedtuple("GameMetadata", "result board_size")):
    pass

class PositionWithContext(namedtuple("SgfPosition", "position next_move metadata")):
    '''
    Wrapper around gomoku.Position.
    Stores a position, the move that came next, and the eventual result.
    '''
    def is_usable(self):
        return all([
            self.position is not None,
            self.next_move is not None,
            self.metadata.result != "Void",
        ])

    def __str__(self):
        return str(self.position) + '\nNext move: {} Result: {}'.format(self.next_move, self.result)

def sgf_prop(value_list):
    'Converts raw sgf library output to sensible value'
    if value_list is None:
        return None
    if len(value_list) == 1:
        return value_list[0]
    else:
        return value_list

def sgf_prop_get(props, key, default):
    return sgf_prop(props.get(key, default))

def handle_node(pos, node):
    'A node can either add B+W stones, play as B, or play as W.'
    props = node.properties
    black_stones_added = [pc(coords) for coords in props.get('AB', [])]
    white_stones_added = [pc(coords) for coords in props.get('AW', [])]
    if black_stones_added or white_stones_added:
        return add_stones(pos, black_stones_added, white_stones_added)
    # If B/W props are not present, then there is no move. But if it is present and equal to the empty string, then the move was a pass.
    elif 'B' in props:
        black_move = pc(props.get('B', [''])[0])
        return pos.play_move(black_move, color=gomoku.BLACK)
    elif 'W' in props:
        white_move = pc(props.get('W', [''])[0])
        return pos.play_move(white_move, color=gomoku.WHITE)
    else:
        return pos

def add_stones(pos, black_stones_added, white_stones_added):
    working_board = np.copy(pos.board)
    gomoku.place_stones(working_board, gomoku.BLACK, black_stones_added)
    gomoku.place_stones(working_board, gomoku.WHITE, white_stones_added)
    new_position = Position(board=working_board, n=pos.n, caps=pos.caps, ko=pos.ko, recent=pos.recent, to_play=pos.to_play)
    return new_position

def get_next_move(node):
    if not node.next:
        return None
    props = node.next.properties
    if 'W' in props:
        return pc(props['W'][0])
    else:
        return pc(props['B'][0])

def maybe_correct_next(pos, next_node):
    if next_node is None:
        return
    if (('B' in next_node.properties and not pos.to_play == gomoku.BLACK) or
        ('W' in next_node.properties and not pos.to_play == gomoku.WHITE)):
        pos.flip_playerturn(mutate=True)

def replay_sgf(sgf_contents):
    '''
    Wrapper for sgf files, exposing contents as position_w_context instances
    with open(filename) as f:
        for position_w_context in replay_sgf(f.read()):
            print(position_w_context.position)
    '''
    collection = sgf.parse(sgf_contents)
    game = collection.children[0]
    props = game.root.properties
    assert int(sgf_prop(props.get('GM', ['1']))) == 1, "Not a Go SGF!"

    metadata = GameMetadata(
        result=sgf_prop(props.get('RE')),
        board_size=int(sgf_prop(props.get('SZ'))))
    gomoku.set_board_size(metadata.board_size)

    pos = Position()
    current_node = game.root
    while pos is not None and current_node is not None:
        pos = handle_node(pos, current_node)
        maybe_correct_next(pos, current_node.next)
        next_move = get_next_move(current_node)
        yield PositionWithContext(pos, next_move, metadata)
        current_node = current_node.next

def replay_position(position):
    '''
    Wrapper for a gomoku.Position which replays its history.
    Assumes an empty start position! (i.e. no handicap, and history must be exhaustive.)

    for position_w_context in replay_position(position):
        print(position_w_context.position)
    '''
    assert position.n == len(position.recent), "Position history is incomplete"
    metadata = GameMetadata(
        result=position.result(),
        board_size=position.board.shape[0]
    )
    gomoku.set_board_size(metadata.board_size)

    pos = Position()
    for player_move in position.recent:
        color, next_move = player_move
        yield PositionWithContext(pos, next_move, metadata)
        pos = pos.play_move(next_move, color=color)
    # return the original position, with unknown next move
    yield PositionWithContext(pos, None, metadata)

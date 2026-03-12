def maybe_break(result):
    return "break" if result else None


def bulk_select_all(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.select_all_visible())


def bulk_clear_selection(app):
    if app.bulk_sheet:
        app.bulk_sheet.clear_selection()
        app._right_click_bulk_context = None
        return "break"
    return None


def bulk_copy_selection(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.copy_selection_to_clipboard())


def bulk_paste_selection(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.paste_from_clipboard())


def bulk_select_current_row(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.select_current_row())


def bulk_select_current_column(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.select_current_column())


def bulk_move_next_editable_cell(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.move_current_editable_cell(1))


def bulk_move_prev_editable_cell(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.move_current_editable_cell(-1))


def bulk_extend_selection_up(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.extend_selection(-1, 0))


def bulk_extend_selection_down(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.extend_selection(1, 0))


def bulk_extend_selection_left(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.extend_selection(0, -1))


def bulk_extend_selection_right(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.extend_selection(0, 1))


def bulk_jump_home(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.jump_current_cell("home", ctrl=False))


def bulk_jump_end(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.jump_current_cell("end", ctrl=False))


def bulk_jump_ctrl_left(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.jump_current_cell("left", ctrl=True))


def bulk_jump_ctrl_right(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.jump_current_cell("right", ctrl=True))


def bulk_jump_ctrl_up(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.jump_current_cell("up", ctrl=True))


def bulk_jump_ctrl_down(app):
    return maybe_break(app.bulk_sheet and app.bulk_sheet.jump_current_cell("down", ctrl=True))

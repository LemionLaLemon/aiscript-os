def render_grid(grid):
    """Render a char grid to a terminal string with a frame."""
    h = len(grid)
    w = len(grid[0])
    top = "+" + "-" * w + "+"
    out = [top]
    for row in grid:
        out.append("|" + "".join(row) + "|")
    out.append(top)
    return "\n".join(out) + "\n"


def clear_screen():
    print("\033[2J\033[H", end="", flush=True)

class FbNotAvailable(Exception):
    pass


def render_grid(grid, fb_path="/dev/fb0"):
    raise FbNotAvailable(
        "framebuffer backend arrives with the OS image (Phase 4). "
        "The terminal backend is used for now."
    )

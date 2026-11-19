"""Bounded native Tk pumping for GUI regression scripts (not production UI)."""
import sys


def native_events(app):
    if sys.platform!='darwin':
        app.update();return
    # Cocoa's update command can wait indefinitely for its event queue to drain
    # after a Canvas redraw. Exercise the real mainloop with a heartbeat instead.
    heartbeat=[]
    def finish():
        heartbeat.append(True);app.quit()
    app.after(50,finish)
    app.mainloop()
    assert heartbeat,'Tk stopped before its GUI heartbeat was processed'


def configure_test_events(app):
    if sys.platform=='darwin': app.update=lambda:native_events(app)
    return app

"""Hardware rendering smoke test. Requires Windows and a graphical desktop."""
import json
import tempfile
from pathlib import Path
from PIL import ImageCms
import numpy as np

def run_check(module=None):
    if module is None:
        import inspector as module
    m = module
    with tempfile.TemporaryDirectory() as directory:
        m.SETTINGS_PATH = Path(directory) / 'settings.json'
        profile = Path(directory) / 'sRGB.icc'
        profile.write_bytes(ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
        app = m.Inspector()
        app.update()
        app.load(str(profile))
        app.update()
        if app.render_mode.get() != 'High GPU' or app.gpu is None or not app.gpu.ready:
            reason = app.gpu_label.cget('text')
            app.destroy()
            raise RuntimeError(f'Hardware rendering not available for this smoke test: {reason}')
        from OpenGL import GL
        gpu = app.gpu
        gpu.tkMakeCurrent()
        gpu.request_draw()
        gpu.tkMakeCurrent()
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, gpu.target[0])
        width, height = gpu.target_size
        pixels = np.frombuffer(GL.glReadPixels(0,0,width,height,GL.GL_RGB,GL.GL_UNSIGNED_BYTE), dtype=np.uint8).reshape(height,width,3)
        colored = (pixels.max(axis=2).astype(int) - pixels.min(axis=2).astype(int)) > 40
        assert colored.sum() > 500, 'Gamut surface must render visible chromatic pixels'
        assert len(np.unique(pixels[colored], axis=0)) > 1000, 'Surface must have smoothly interpolated colors'
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
        assert width >= gpu.winfo_width() and height >= gpu.winfo_height()
        diagnostics = {'renderer':gpu.renderer, 'viewport':[gpu.winfo_width(),gpu.winfo_height()],
                       'render_target':[width,height], 'chromatic_pixels':int(colored.sum())}
        print(json.dumps(diagnostics), flush=True)
        for view in ('Points', 'Wireframe', 'Surface'):
            app.view.set(view)
            app.draw()
            app.update()
            assert not gpu.failed
        app.load(str(profile), True)
        app.update()
        app.main_tabs.select(app.list_tab)
        app.update()
        app.main_tabs.select(app.inspector_tab)
        app.update()
        app.geometry('1100x750')
        app.update()
        app.draw()
        app.render_mode.set('Basic CPU')
        app.select_renderer()
        app.update()
        assert app.canvas.winfo_ismapped()
        app.render_mode.set('High GPU')
        app.select_renderer()
        app.update()
        assert gpu.winfo_ismapped() and not gpu.failed
        gpu.tkMakeCurrent()
        GL.glFinish()
        assert GL.glGetError() == GL.GL_NO_ERROR
        app.destroy()
        print('PASS: real GPU pixels, smooth colors, supersampling, all views, comparison, resize, tab switching and CPU/GPU switching', flush=True)
        return diagnostics

if __name__ == '__main__':
    run_check()

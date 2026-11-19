"""Hardware rendering smoke test. Requires Windows and a graphical desktop."""
import json
import tempfile
import time
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
        app.load(str(profile), background=False)
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
        from send2trash.win.modern import send2trash
        diagnostics['recycle_backend']=send2trash.__module__
        print(json.dumps(diagnostics), flush=True)
        # Confirm an enclosed comparison remains visible only with X-ray enabled.
        original=app.primary
        def cube(scale):
            points=np.array([[a,b,z] for a in (-1,1) for b in (-1,1) for z in (-1,1)],dtype=float)*scale
            from scipy.spatial import ConvexHull
            return {'path':'test-cube','points':points,'lab':points[:,[2,0,1]],'rgb':np.tile([220,30,30],(8,1)),
                    'hull':ConvexHull(points),'samples':8,'intent':1}
        app.primary=cube(70); app.comparison=cube(30)
        def count_comparison():
            gpu.request_draw(); gpu.tkMakeCurrent()
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER,gpu.target[0])
            pixels=np.frombuffer(GL.glReadPixels(0,0,*gpu.target_size,GL.GL_RGB,GL.GL_UNSIGNED_BYTE),dtype=np.uint8).reshape(-1,3)
            color=np.array([int(app.colors['compare'][i:i+2],16) for i in (1,3,5)])
            count=int((np.max(np.abs(pixels.astype(int)-color),axis=1)<8).sum())
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER,0)
            return count
        app.xray.set(False); hidden=count_comparison()
        app.xray.set(True); visible=count_comparison()
        assert visible>100 and visible>hidden+100,(hidden,visible)
        assert GL.glIsEnabled(GL.GL_DEPTH_TEST), 'Primary depth testing must be restored'
        diagnostics['xray_comparison_pixels']=visible
        diagnostics['depth_tested_comparison_pixels']=hidden
        app.primary=original; app.comparison=None
        for view in ('Points', 'Wireframe', 'Surface'):
            app.view.set(view)
            app.draw()
            app.update()
            assert not gpu.failed
        app.load(str(profile), True, background=False)
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
        outer=cube(70)
        dense={key:np.tile(value,(25000,1)) if key in ('points','lab','rgb') else value for key,value in outer.items()}
        dense['hull']=None; dense['samples']=len(dense['points'])
        app.primary=dense; app.comparison=None; app.view.set('Points')
        start=time.perf_counter(); app.draw(); elapsed=time.perf_counter()-start
        assert len(app.canvas.find_all())<=4010 and len(dense['points'])==200000
        diagnostics['cpu_point_draw_seconds']=round(elapsed,3)
        diagnostics['cpu_display_items']=len(app.canvas.find_all())
        app.primary=original; app.view.set('Surface')
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

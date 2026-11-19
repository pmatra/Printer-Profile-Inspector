"""OpenGL gamut viewport with smooth vertex colors and supersampled rendering."""
import numpy as np
import sys
from OpenGL import GL
from pyopengltk import OpenGLFrame


class GamutGPU(OpenGLFrame):
    def __init__(self, parent, owner):
        self.owner = owner
        self.ready = False
        self.failed = False
        self.renderer = ''
        self.target = None
        self.target_size = (0, 0)
        self.mesh_cache = {}
        super().__init__(parent, width=800, height=600)
        self.bind('<ButtonPress-1>', lambda e: setattr(owner, 'drag', (e.x, e.y)))
        self.bind('<B1-Motion>', owner.rotate)
        self.bind('<MouseWheel>', owner.wheel)
        self.bind('<Motion>', owner.hover)
        self.bind('<Unmap>', lambda event: self.suspend_context())

    def tkCreateContext(self):
        super().tkCreateContext()
        if sys.platform == 'win32':
            from OpenGL import WGL
            self.native_context = WGL.wglGetCurrentContext()
            self.native_dc = WGL.wglGetCurrentDC()

    def tkMakeCurrent(self):
        if sys.platform == 'win32' and getattr(self, 'native_context', None):
            from OpenGL import WGL
            WGL.wglMakeCurrent(self.native_dc, self.native_context)
        else:
            super().tkMakeCurrent()

    def suspend_context(self):
        if sys.platform == 'win32':
            from OpenGL import WGL
            WGL.wglMakeCurrent(None, None)

    def tkMap(self, event):
        try:
            super().tkMap(event)
            self.request_draw()
        except Exception as exc:
            self.fail(exc)

    def tkResize(self, event):
        self.width, self.height = event.width, event.height
        self.request_draw()

    def initgl(self):
        if self.failed:
            return
        raw = GL.glGetString(GL.GL_RENDERER)
        if not raw:
            raise RuntimeError('No OpenGL context was created.')
        self.renderer = raw.decode('utf-8', 'replace')
        if any(name in self.renderer.lower() for name in ('gdi generic', 'llvmpipe', 'softpipe', 'software rasterizer')):
            raise RuntimeError(f'Hardware OpenGL is unavailable ({self.renderer}).')
        if not GL.glGenFramebuffers or not GL.glBlitFramebuffer:
            raise RuntimeError('The graphics driver does not support framebuffer supersampling.')
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)
        GL.glShadeModel(GL.GL_SMOOTH)
        self.ready = True

    def fail(self, exc):
        if not self.failed:
            self.failed = True
            self.ready = False
            self.after_idle(lambda reason=str(exc): self.owner.gpu_failed(reason))

    def _display(self):
        if self.ready and not self.failed and self.winfo_ismapped():
            try:
                self.tkMakeCurrent()
                self.redraw()
                self.tkSwapBuffers()
            except Exception as exc:
                self.fail(exc)
            finally:
                self.suspend_context()

    def request_draw(self):
        if self.ready and self.winfo_ismapped():
            self._display()

    def release_target(self):
        if self.target:
            framebuffer, color, depth = self.target
            GL.glDeleteFramebuffers(1, [framebuffer])
            GL.glDeleteRenderbuffers(2, [color, depth])
            self.target = None

    def allocate_target(self, width, height):
        # Two pixels per screen pixel in each direction, bounded by driver/VRAM limits.
        limit = min(int(GL.glGetIntegerv(GL.GL_MAX_RENDERBUFFER_SIZE)), 4096)
        factor = min(2.0, limit / max(width, height))
        if factor < 1:
            raise RuntimeError('Viewport exceeds the supported High GPU render target size.')
        size = (max(1, int(width * factor)), max(1, int(height * factor)))
        if self.target and size == self.target_size:
            return
        self.release_target()
        framebuffer = int(GL.glGenFramebuffers(1))
        color, depth = map(int, GL.glGenRenderbuffers(2))
        self.target = (framebuffer, color, depth)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, framebuffer)
        GL.glBindRenderbuffer(GL.GL_RENDERBUFFER, color)
        GL.glRenderbufferStorage(GL.GL_RENDERBUFFER, GL.GL_RGBA8, *size)
        GL.glFramebufferRenderbuffer(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0, GL.GL_RENDERBUFFER, color)
        GL.glBindRenderbuffer(GL.GL_RENDERBUFFER, depth)
        GL.glRenderbufferStorage(GL.GL_RENDERBUFFER, GL.GL_DEPTH_COMPONENT24, *size)
        GL.glFramebufferRenderbuffer(GL.GL_FRAMEBUFFER, GL.GL_DEPTH_ATTACHMENT, GL.GL_RENDERBUFFER, depth)
        if GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER) != GL.GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError('The graphics driver could not allocate a High GPU render target.')
        self.target_size = size

    def redraw(self):
        owner = self.owner
        if not hasattr(owner, 'colors'):
            return
        width, height = max(1, self.winfo_width()), max(1, self.winfo_height())
        self.allocate_target(width, height)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.target[0])
        GL.glViewport(0, 0, *self.target_size)
        color = owner.colors['plot']
        GL.glClearColor(*(int(color[i:i+2], 16) / 255 for i in (1, 3, 5)), 1)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        # Rotation preserves the vector norm. Size the depth range from actual
        # data, independently of zoom, so unusual profiles cannot be clipped.
        depth=500.0
        for result in (owner.primary,owner.comparison):
            if result is not None:
                if '_depth_extent' not in result:
                    result['_depth_extent']=float(np.linalg.norm(result['points'],axis=1).max(initial=0))*1.05+1
                depth=max(depth,result['_depth_extent'])
        self.depth_limit=depth
        GL.glOrtho(0, width, height, 0, -depth, depth)
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()
        GL.glDisable(GL.GL_LIGHTING)  # Preserve the ICC-derived sRGB vertex colors.
        GL.glEnableClientState(GL.GL_VERTEX_ARRAY)
        GL.glEnableClientState(GL.GL_COLOR_ARRAY)
        owner.hitpoints = []
        live_keys = set()
        for result, comparison in [(owner.primary, False), (owner.comparison, True)]:
            if result is None:
                continue
            key = id(result)
            live_keys.add(key)
            if key not in self.mesh_cache or self.mesh_cache[key][3] is not result:
                hull = result['hull']
                triangles = np.ascontiguousarray(hull.simplices, dtype=np.uint32) if hull is not None else None
                edges = None
                if triangles is not None:
                    edges = np.unique(np.sort(np.concatenate([triangles[:, [0,1]], triangles[:, [1,2]], triangles[:, [2,0]]]), axis=1), axis=0)
                    edges = np.ascontiguousarray(edges, dtype=np.uint32)
                self.mesh_cache[key] = (triangles, edges, np.ascontiguousarray(result['rgb'] / 255, dtype=np.float32),result)
            triangles, edges, colors, source = self.mesh_cache[key]
            xray = comparison and owner.xray.get()
            if xray:
                GL.glDisable(GL.GL_DEPTH_TEST); GL.glDepthMask(False)
            points = np.ascontiguousarray(owner.project(result['points']), dtype=np.float32)
            GL.glVertexPointer(3, GL.GL_FLOAT, 0, points)
            GL.glColorPointer(3, GL.GL_FLOAT, 0, colors)
            view = 'Wireframe' if comparison else owner.view.get()
            if triangles is not None and view == 'Surface':
                GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
                GL.glPolygonOffset(1, 1)
                GL.glDrawElements(GL.GL_TRIANGLES, triangles.size, GL.GL_UNSIGNED_INT, triangles)
                GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)
            elif edges is not None and view == 'Wireframe':
                GL.glDisableClientState(GL.GL_COLOR_ARRAY)
                wire = owner.colors['compare'] if comparison else owner.colors['wire']
                GL.glColor3f(*(int(wire[i:i+2],16)/255 for i in (1,3,5)))
                GL.glLineWidth(1.5)
                GL.glDrawElements(GL.GL_LINES, edges.size, GL.GL_UNSIGNED_INT, edges)
                GL.glEnableClientState(GL.GL_COLOR_ARRAY)
            else:
                GL.glPointSize(3 * self.target_size[0] / width)
                indices=np.ascontiguousarray(owner.point_indices(result,30000),dtype=np.uint32)
                GL.glDrawElements(GL.GL_POINTS,len(indices),GL.GL_UNSIGNED_INT,indices)
            if not comparison:
                indices = result['hull'].vertices if result['hull'] is not None and view != 'Points' else owner.point_indices(result,30000)
                indices=indices[::max(1,int(np.ceil(len(indices)/5000)))]
                owner.hitpoints = [(points[i,0], points[i,1], result['lab'][i]) for i in indices]
            if xray:
                GL.glDepthMask(True); GL.glEnable(GL.GL_DEPTH_TEST)
        self.mesh_cache = {k:v for k,v in self.mesh_cache.items() if k in live_keys}
        GL.glDisableClientState(GL.GL_COLOR_ARRAY)
        GL.glDisableClientState(GL.GL_VERTEX_ARRAY)
        axes = owner.project(np.array([[0,0,-50],[110,0,-50],[0,110,-50],[0,0,65]]))
        GL.glBegin(GL.GL_LINES)
        for i, axis_color in [(1,(.85,.25,.3)), (2,(.75,.6,.1)), (3,(.55,.55,.55))]:
            GL.glColor3f(*axis_color)
            GL.glVertex3f(*axes[0])
            GL.glVertex3f(*axes[i])
        GL.glEnd()
        GL.glBindFramebuffer(GL.GL_READ_FRAMEBUFFER, self.target[0])
        GL.glBindFramebuffer(GL.GL_DRAW_FRAMEBUFFER, 0)
        GL.glBlitFramebuffer(0,0,*self.target_size,0,0,width,height,GL.GL_COLOR_BUFFER_BIT,GL.GL_LINEAR)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)
        GL.glFlush()
        owner.gpu_label.configure(text=f'High GPU • {self.renderer} • {self.target_size[0]} × {self.target_size[1]} render target\nD50 CIELAB • a*: red / b*: gold / L*: gray • Drag to rotate; scroll to zoom')

    def destroy(self):
        if self.ready:
            try:
                self.tkMakeCurrent()
                self.release_target()
            except Exception:
                pass
        if sys.platform == 'win32' and getattr(self, 'native_context', None):
            from OpenGL import WGL
            import ctypes
            self.suspend_context()
            WGL.wglDeleteContext(self.native_context)
            release_dc = ctypes.windll.user32.ReleaseDC
            release_dc.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            release_dc.restype = ctypes.c_int
            release_dc(self.winfo_id(), self.native_dc)
            self.native_context = None
        super().destroy()
